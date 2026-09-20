"""Unit tests for viewer PIN authentication."""

import hashlib
from fastapi.testclient import TestClient
from src.config import AppConfig, load_config
from src.viewer.app import MAX_LOGIN_ATTEMPTS, app, create_viewer_app


def test_unauthenticated_access_returns_login_page():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "PIN 비밀번호를 입력해주세요" in response.text
    assert "pinDisplay" in response.text


def test_unauthenticated_api_live_returns_401():
    client = TestClient(app)
    response = client.get("/api/live")
    assert response.status_code == 401
    assert response.json()["detail"] == "인증이 필요합니다."


def test_login_with_incorrect_pin_returns_401():
    client = TestClient(app)
    response = client.post("/api/auth/login", json={"pin": "wrongpin"})
    assert response.status_code == 401
    assert response.json()["detail"] == "비밀번호가 일치하지 않습니다."


def test_login_with_correct_pin_sets_cookie_and_authenticates():
    client = TestClient(app)
    config = load_config()
    response = client.post("/api/auth/login", json={"pin": config.viewer.pin})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "soonsim_auth" in response.cookies

    # Authenticated access to root returns main viewer
    main_res = client.get("/")
    assert main_res.status_code == 200
    assert "순심이 상시 감시 뷰어" in main_res.text

    # Authenticated access to /api/live succeeds
    live_res = client.get("/api/live")
    assert live_res.status_code == 200
    live_data = live_res.json()
    assert "status_title" in live_data
    assert "last_poll_str" in live_data
    assert live_data["last_poll_str"] == "대기 중"


def test_session_tokens_are_random_and_not_derived_from_pin():
    """A cookie must not be computable from the PIN, which is what made the old scheme forgeable."""
    config = AppConfig()
    app_under_test = create_viewer_app(config=config)

    first = TestClient(app_under_test).post("/api/auth/login", json={"pin": config.viewer.pin})
    second = TestClient(app_under_test).post("/api/auth/login", json={"pin": config.viewer.pin})
    assert first.status_code == second.status_code == 200
    assert first.cookies["soonsim_auth"] != second.cookies["soonsim_auth"]

    # The exact cookie the old scheme minted must no longer authenticate. This is
    # the regression that matters: it was computable offline from the PIN plus
    # the session_secret default that shipped in the public source.
    legacy = hashlib.sha256(f"{config.viewer.pin}:soonsim-viewer-auth-token-salt".encode()).hexdigest()
    for guess in (config.viewer.pin, legacy):
        forged = TestClient(app_under_test)
        forged.cookies.set("soonsim_auth", guess)
        assert forged.get("/api/live").status_code == 401


def test_logout_revokes_the_session_server_side():
    """Replaying the cookie after logout must fail, not just clear it client-side."""
    config = AppConfig()
    app_under_test = create_viewer_app(config=config)
    client = TestClient(app_under_test)

    client.post("/api/auth/login", json={"pin": config.viewer.pin})
    token = client.cookies["soonsim_auth"]
    assert client.get("/api/live").status_code == 200

    client.post("/api/auth/logout")

    replay = TestClient(app_under_test)
    replay.cookies.set("soonsim_auth", token)
    assert replay.get("/api/live").status_code == 401


def test_repeated_failures_lock_out_login():
    """Brute-forcing a short PIN must stop being possible after the attempt limit."""
    config = AppConfig()
    app_under_test = create_viewer_app(config=config)
    client = TestClient(app_under_test)

    for _ in range(MAX_LOGIN_ATTEMPTS):
        assert client.post("/api/auth/login", json={"pin": "not-the-pin"}).status_code == 401

    locked_out = client.post("/api/auth/login", json={"pin": config.viewer.pin})
    assert locked_out.status_code == 429


def test_kst_timestamp_format():
    import datetime
    from src.viewer.app import KST
    now = datetime.datetime.fromtimestamp(1700000000, tz=KST)
    assert now.strftime("%Y-%m-%d %H:%M:%S") == "2023-11-15 07:13:20"
    assert now.tzinfo.key == "Asia/Seoul"
