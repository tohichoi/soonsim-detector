"""Tests for clip listing, clip resolution, and clip labels."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from src.config import AppConfig, RecorderConfig
from src.viewer.app import create_viewer_app
from src.viewer.clips import list_clips, resolve_clip
from src.viewer.labels import load_labels, set_label

CLIP = "soonsim_20260922_235935.mp4"
SIGNAL = "signal_20260923_010000.mp4"


def _touch(directory: Path, name: str, content: bytes = b"x") -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


def test_resolve_clip_rejects_everything_that_is_not_a_clip(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.toml").write_text("pin = 'x'")
    _touch(tmp_path, "detection.log")
    _touch(tmp_path, "zone_contact.jsonl")
    _touch(tmp_path, CLIP)

    for name in (
        "../config/config.toml",
        "detection.log",
        "zone_contact.jsonl",
        "sub/dir/" + CLIP,
        CLIP + "/",
        str(tmp_path / "config" / "config.toml"),
        "/etc/passwd",
        "soonsim_20260922_235935.mp4.bak",
        "..",
        "",
    ):
        assert resolve_clip(tmp_path, name) is None, name


def test_resolve_clip_accepts_a_real_clip_name(tmp_path):
    _touch(tmp_path, CLIP)
    assert resolve_clip(tmp_path, CLIP) == (tmp_path / CLIP).resolve()


def test_resolve_clip_rejects_a_symlink_escaping_the_directory(tmp_path):
    outside = tmp_path.parent / "outside_secret.mp4"
    outside.write_bytes(b"secret")
    (tmp_path / CLIP).symlink_to(outside)
    assert resolve_clip(tmp_path, CLIP) is None


def test_list_clips_is_newest_first_and_filters_by_kind(tmp_path):
    _touch(tmp_path, "soonsim_20260101_000000.mp4")
    _touch(tmp_path, CLIP)
    _touch(tmp_path, SIGNAL)
    _touch(tmp_path, "detection.log")

    everything = list_clips(tmp_path)
    assert [c["name"] for c in everything] == [SIGNAL, CLIP, "soonsim_20260101_000000.mp4"]

    events = list_clips(tmp_path, kind="event")
    assert [c["name"] for c in events] == [CLIP, "soonsim_20260101_000000.mp4"]
    assert all(c["kind"] == "event" for c in events)
    assert events[0]["time_str"] == "2026-09-22 23:59:35"
    assert events[0]["size_bytes"] == 1

    signals = list_clips(tmp_path, kind="signal")
    assert [c["name"] for c in signals] == [SIGNAL]
    assert signals[0]["kind"] == "signal"

    with pytest.raises(ValueError):
        list_clips(tmp_path, kind="nonsense")


def test_labels_round_trip_with_last_write_winning(tmp_path):
    _touch(tmp_path, CLIP)
    _touch(tmp_path, SIGNAL)
    assert load_labels(tmp_path) == {}
    set_label(tmp_path, CLIP, "real")
    set_label(tmp_path, SIGNAL, "false")
    set_label(tmp_path, CLIP, "unsure")
    assert load_labels(tmp_path) == {CLIP: "unsure", SIGNAL: "false"}

    set_label(tmp_path, CLIP, None)
    assert load_labels(tmp_path) == {SIGNAL: "false"}

    with pytest.raises(ValueError):
        set_label(tmp_path, CLIP, "maybe")

    listed = list_clips(tmp_path, kind="signal")
    assert listed[0]["label"] == "false"
    assert list_clips(tmp_path, kind="event")[0]["label"] is None


def test_list_clips_survives_a_corrupt_label_line(tmp_path):
    _touch(tmp_path, CLIP)
    set_label(tmp_path, CLIP, "real")
    with (tmp_path / "clip_labels.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"name": "soonsim_2026')
    assert list_clips(tmp_path)[0]["label"] == "real"


@pytest.fixture
def clip_client(tmp_path):
    config = AppConfig(recorder=RecorderConfig(output_dir=tmp_path))
    client = TestClient(create_viewer_app(config=config))
    client.post("/api/auth/login", json={"pin": config.viewer.pin})
    return client, tmp_path


def test_clip_routes_require_auth(tmp_path):
    config = AppConfig(recorder=RecorderConfig(output_dir=tmp_path))
    client = TestClient(create_viewer_app(config=config))
    assert client.get("/api/clips").status_code == 401
    assert client.get(f"/api/clips/{CLIP}").status_code == 401
    assert client.post(f"/api/clips/{CLIP}/label", json={"label": "real"}).status_code == 401


def test_clip_routes_serve_list_playback_and_label(clip_client):
    client, directory = clip_client
    _touch(directory, CLIP, b"\x00\x00\x00\x18ftypmp42")

    listed = client.get("/api/clips?kind=event").json()
    assert [c["name"] for c in listed["clips"]] == [CLIP]
    assert listed["clips"][0]["label"] is None

    video = client.get(f"/api/clips/{CLIP}")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"

    # Seeking a clip needs byte ranges, which is why this returns FileResponse.
    partial = client.get(f"/api/clips/{CLIP}", headers={"Range": "bytes=0-3"})
    assert partial.status_code == 206
    assert partial.content == b"\x00\x00\x00\x18"

    labelled = client.post(f"/api/clips/{CLIP}/label", json={"label": "real"})
    assert labelled.status_code == 200
    assert labelled.json() == {"name": CLIP, "label": "real"}
    assert client.get("/api/clips").json()["clips"][0]["label"] == "real"

    assert client.post(f"/api/clips/{CLIP}/label", json={"label": "maybe"}).status_code == 400
    assert client.post(f"/api/clips/{CLIP}/label", json={"label": None}).json()["label"] is None


def test_clip_routes_reject_unknown_and_out_of_bounds_names(clip_client):
    client, directory = clip_client
    _touch(directory, "detection.log")
    (directory / "config").mkdir()
    (directory / "config" / "config.toml").write_text("pin = 'x'")

    assert client.get("/api/clips/detection.log").status_code == 404
    assert client.get("/api/clips/zone_contact.jsonl").status_code == 404
    assert client.get("/api/clips/..%2Fconfig%2Fconfig.toml").status_code == 404
    assert client.post("/api/clips/zone_contact.jsonl/label", json={"label": "real"}).status_code == 404
    assert client.get("/api/clips?kind=nonsense").status_code == 400
