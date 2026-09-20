"""Unit and integration tests for unified ViewerStateStore and ViewerServer."""

import time
from fastapi.testclient import TestClient
import numpy as np
from src.config import AppConfig
from src.viewer.app import compute_auth_token, create_viewer_app
from src.viewer.server import ViewerServer, find_available_port
from src.viewer.state import ViewerStateStore


def test_viewer_state_store_live_and_events():
    store = ViewerStateStore(retention_sec=2.0)
    fake_img = b"\xff\xd8\xff\xe0"

    store.update_live(
        status_title="테스트 상태",
        status_desc="테스트 설명",
        status_type="motion",
        detected_objects=["dog"],
        dog_in_zone=True,
        change_score=5.5,
        image_bytes=fake_img,
    )

    state = store.get_live_state()
    assert state.status_title == "테스트 상태"
    assert state.dog_in_zone is True
    assert state.change_score == 5.5
    assert state.latest_image_bytes == fake_img

    rec_id = store.push_event(
        event_type="DOG_ON_PAD",
        detected_objects=["dog"],
        dog_in_zone=True,
        change_score=5.5,
        image_bytes=fake_img,
    )
    assert rec_id == 1

    history = store.get_history()
    assert len(history) == 1
    assert history[0].event_type == "DOG_ON_PAD"

    snapshot = store.get_snapshot(1)
    assert snapshot is not None
    assert snapshot.image_bytes == fake_img


def test_viewer_state_store_retention_pruning():
    store = ViewerStateStore(retention_sec=0.1)
    fake_img = b"test"

    store.push_event("MOTION_CHANGE", ["dog"], False, 1.0, fake_img)
    assert len(store.get_history()) == 1

    time.sleep(0.15)
    store.update_live("Title", "Desc", "idle", [], False, 0.0, fake_img)
    assert len(store.get_history()) == 0


def test_create_viewer_app_with_custom_store():
    store = ViewerStateStore()
    config = AppConfig()
    app = create_viewer_app(state_store=store, config=config)
    client = TestClient(app)

    token = compute_auth_token(config.viewer.pin, config.viewer.session_secret)
    client.cookies.set("soonsim_auth", token)

    store.update_live("배변판 진입", "진입함", "dog_on_pad", ["dog"], True, 10.0, b"jpegdata")
    res = client.get("/api/live")
    assert res.status_code == 200
    assert res.json()["status_title"] == "배변판 진입"

    snap_res = client.get("/api/snapshot/latest")
    assert snap_res.status_code == 200
    assert snap_res.content == b"jpegdata"


def test_find_available_port():
    port = find_available_port(host="127.0.0.1", start_port=18080)
    assert port >= 18080


def test_viewer_server_start_stop():
    store = ViewerStateStore()
    config = AppConfig()
    config.viewer.port = 19090

    server = ViewerServer(state_store=store, config=config)
    server.start()
    assert server.thread is not None
    assert server.thread.is_alive()

    server.stop()
    assert not server.thread.is_alive()
