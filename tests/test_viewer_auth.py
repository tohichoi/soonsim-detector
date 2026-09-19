"""Unit tests for viewer PIN authentication."""

from fastapi.testclient import TestClient
from src.config import load_config
from src.viewer.app import app


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


def test_kst_timestamp_format():
    import datetime
    from src.viewer.app import KST
    now = datetime.datetime.fromtimestamp(1700000000, tz=KST)
    assert now.strftime("%Y-%m-%d %H:%M:%S") == "2023-11-15 07:13:20"
    assert now.tzinfo.key == "Asia/Seoul"
