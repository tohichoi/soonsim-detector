"""Tests for the H.264 transcode helper. No real ffmpeg runs here."""

import os
import time
from pathlib import Path
from typing import Optional

import pytest

from src.recorder import transcode
from src.recorder.transcode import backfill, is_h264, is_transcoding, to_h264

CLIP = "soonsim_20260922_235935.mp4"


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_fake_run(
    codecs: dict[str, str],
    fail_ffmpeg: Optional[str] = None,
    tmp_content: bytes = b"H264",
):
    """Route fake ffprobe/ffmpeg calls, writing output only when it succeeds.

    The transcode temp file probes as H.264, which is what the caller checks
    before replacing the original.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            if "transcode.tmp" in Path(cmd[-1]).name:
                # Probe the output the way real ffprobe would: only the marker
                # content is a readable H.264 file.
                if not Path(cmd[-1]).read_bytes().startswith(b"H264"):
                    return FakeResult(returncode=1, stderr="Invalid data found")
                return FakeResult(stdout="h264\n")
            return FakeResult(stdout=codecs.get(Path(cmd[-1]).name, "mp4v") + "\n")
        if cmd[0] == "nice":
            tmp = Path(cmd[-1])
            if fail_ffmpeg is not None and fail_ffmpeg in tmp.name:
                return FakeResult(returncode=1, stderr="boom")
            tmp.write_bytes(tmp_content)
            return FakeResult()
        raise AssertionError(f"unexpected command: {cmd}")

    return fake_run, calls


def test_is_h264_reads_the_probe_output(tmp_path, monkeypatch):
    _touch(tmp_path, CLIP)
    fake_run, _ = _make_fake_run({CLIP: "h264"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    assert is_h264(tmp_path / CLIP) is True

    fake_run, _ = _make_fake_run({CLIP: "mp4v"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    assert is_h264(tmp_path / CLIP) is False


def test_to_h264_returns_false_and_touches_nothing_when_the_source_is_missing(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("no subprocess for a missing file")

    monkeypatch.setattr(transcode.subprocess, "run", explode)
    missing = tmp_path / CLIP
    assert to_h264(missing) is False
    assert list(tmp_path.iterdir()) == []


def test_a_failed_transcode_leaves_the_original_intact(tmp_path, monkeypatch):
    original = _touch(tmp_path, CLIP, b"MP4V-ORIGINAL")
    fake_run, calls = _make_fake_run({CLIP: "mp4v"}, fail_ffmpeg="transcode")
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert to_h264(original) is False
    assert original.read_bytes() == b"MP4V-ORIGINAL"
    assert [p.name for p in tmp_path.iterdir()] == [CLIP]
    assert is_transcoding(original) is False

    ffmpeg_cmd = next(c for c in calls if c[0] == "nice")
    assert ffmpeg_cmd[1:3] == ["-n", "19"]
    assert ffmpeg_cmd[ffmpeg_cmd.index("-threads") + 1] == "1"


def test_a_successful_transcode_replaces_the_file_in_place(tmp_path, monkeypatch):
    original = _touch(tmp_path, CLIP, b"MP4V-ORIGINAL")
    fake_run, _ = _make_fake_run({CLIP: "h264"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert to_h264(original) is True
    assert original.read_bytes() == b"H264"
    assert [p.name for p in tmp_path.iterdir()] == [CLIP]


@pytest.mark.parametrize("tmp_content", [b"", b"not-a-video"])
def test_output_is_verified_before_the_original_is_replaced(tmp_path, monkeypatch, tmp_content):
    """ffmpeg exiting 0 on a truncated file must not cost us the clip.

    A clip is the source data for labelling, so the original only goes once the
    replacement has been confirmed to be a non-empty H.264 file.
    """
    original = _touch(tmp_path, CLIP, b"MP4V-ORIGINAL")
    fake_run, _ = _make_fake_run({CLIP: "mp4v"}, tmp_content=tmp_content)
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert to_h264(original) is False
    assert original.read_bytes() == b"MP4V-ORIGINAL"
    assert [p.name for p in tmp_path.iterdir()] == [CLIP]


def test_the_temp_name_is_unique_per_process(tmp_path, monkeypatch):
    """Two processes (the service and the backfill CLI) must not share a temp file."""
    original = _touch(tmp_path, CLIP, b"MP4V-ORIGINAL")
    fake_run, calls = _make_fake_run({CLIP: "mp4v"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert to_h264(original) is True
    ffmpeg_cmd = next(c for c in calls if c[0] == "nice")
    assert f".{os.getpid()}." in Path(ffmpeg_cmd[-1]).name


def test_to_h264_skips_a_path_that_is_already_being_converted(tmp_path, monkeypatch):
    original = _touch(tmp_path, CLIP, b"MP4V-ORIGINAL")

    def explode(*args, **kwargs):
        raise AssertionError("must not start a second transcode")

    monkeypatch.setattr(transcode.subprocess, "run", explode)
    assert transcode._claim(original) is True
    try:
        assert is_transcoding(original) is True
        assert to_h264(original) is False
    finally:
        transcode._release(original)
    assert original.read_bytes() == b"MP4V-ORIGINAL"


def test_backfill_converts_only_the_clips_that_are_not_h264(tmp_path, monkeypatch):
    already = _touch(tmp_path, "signal_20260923_010000.mp4", age_sec=120)
    pending = _touch(tmp_path, CLIP, age_sec=120)
    _touch(tmp_path, "detection.log", age_sec=120)
    _touch(tmp_path, "note.mp4", age_sec=120)

    fake_run, _ = _make_fake_run({already.name: "h264", pending.name: "mp4v"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert backfill(tmp_path) == (1, 0)
    assert pending.read_bytes() == b"H264"
    assert already.read_bytes() == b"x"
    assert (tmp_path / "note.mp4").read_bytes() == b"x"


def test_backfill_leaves_a_clip_that_is_still_being_written(tmp_path, monkeypatch):
    """The exporter writes into the final name, so a fresh file may be half-written.

    Converting it would produce a truncated H.264 and then overwrite the
    original clip with it.
    """
    fresh = _touch(tmp_path, CLIP)
    fake_run, _ = _make_fake_run({CLIP: "mp4v"})
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert backfill(tmp_path) == (0, 0)
    assert fresh.read_bytes() == b"x"

    # Once it has settled, the same clip is converted on the next pass.
    assert backfill(tmp_path, recent_sec=0.0) == (1, 0)
    assert fresh.read_bytes() == b"H264"


def test_backfill_counts_a_failed_clip(tmp_path, monkeypatch):
    pending = _touch(tmp_path, CLIP, age_sec=120)
    fake_run, _ = _make_fake_run({pending.name: "mp4v"}, fail_ffmpeg="transcode")
    monkeypatch.setattr(transcode.subprocess, "run", fake_run)

    assert backfill(tmp_path) == (0, 1)
    assert pending.read_bytes() == b"x"


def _touch(directory: Path, name: str, content: bytes = b"x", age_sec: float = 0.0) -> Path:
    path = directory / name
    path.write_bytes(content)
    if age_sec:
        settled = time.time() - age_sec
        os.utime(path, (settled, settled))
    return path
