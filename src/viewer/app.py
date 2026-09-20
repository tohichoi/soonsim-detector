"""FastAPI web viewer application for Soonsim Detector."""

import hashlib
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from src.config import AppConfig, load_config
from src.viewer.state import KST, ViewerStateStore
from src.viewer.templates import HTML_TEMPLATE, LOGIN_HTML_TEMPLATE

default_state_store = ViewerStateStore()


class LoginRequest(BaseModel):
    pin: str


def compute_auth_token(pin: str, secret: str) -> str:
    """Compute SHA256 signature for session cookie."""
    return hashlib.sha256(f"{pin}:{secret}".encode("utf-8")).hexdigest()


def check_auth(request: Request, config: AppConfig) -> bool:
    """Check if request contains valid auth cookie."""
    cookie_token = request.cookies.get("soonsim_auth")
    expected_token = compute_auth_token(config.viewer.pin, config.viewer.session_secret)
    return cookie_token == expected_token


def _register_auth_routes(app: FastAPI, cfg: AppConfig) -> None:
    """Register index, login, and logout endpoints."""
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if check_auth(request, cfg):
            return HTMLResponse(content=HTML_TEMPLATE)
        return HTMLResponse(content=LOGIN_HTML_TEMPLATE)

    @app.post("/api/auth/login")
    async def login(req: LoginRequest, response: Response):
        if req.pin == cfg.viewer.pin:
            token = compute_auth_token(cfg.viewer.pin, cfg.viewer.session_secret)
            response.set_cookie(
                key="soonsim_auth",
                value=token,
                max_age=86400 * 30,
                httponly=True,
                samesite="lax",
            )
            return {"success": True, "detail": "인증 성공"}
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")

    @app.post("/api/auth/logout")
    async def logout(response: Response):
        response.delete_cookie(key="soonsim_auth")
        return {"success": True, "detail": "로그아웃 성공"}


def _register_telemetry_routes(app: FastAPI, store: ViewerStateStore, cfg: AppConfig) -> None:
    """Register telemetry and history endpoints."""
    def require_auth(request: Request) -> None:
        if not check_auth(request, cfg):
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    @app.get("/api/live")
    async def get_live(request: Request):
        require_auth(request)
        state = store.get_live_state()
        return {
            "last_poll_str": state.last_poll_str,
            "last_poll_epoch": state.last_poll_epoch,
            "status_title": state.status_title,
            "status_desc": state.status_desc,
            "status_type": state.status_type,
            "detected_objects": state.detected_objects,
            "dog_in_zone": state.dog_in_zone,
            "change_score": state.change_score,
            "total_events_30m": state.total_events_30m,
            "interval_sec": state.interval_sec,
        }

    @app.get("/api/history")
    async def get_history(request: Request):
        require_auth(request)
        return [
            {
                "id": r.id,
                "timestamp_str": r.timestamp_str,
                "timestamp_epoch": r.timestamp_epoch,
                "detected_objects": r.detected_objects,
                "dog_in_zone": r.dog_in_zone,
                "event_type": r.event_type,
                "change_score": r.change_score,
            }
            for r in store.get_history()
        ]


def _register_snapshot_routes(app: FastAPI, store: ViewerStateStore, cfg: AppConfig) -> None:
    """Register snapshot image endpoints."""
    def require_auth(request: Request) -> None:
        if not check_auth(request, cfg):
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    @app.get("/api/snapshot/latest")
    async def get_latest_snapshot(request: Request):
        require_auth(request)
        state = store.get_live_state()
        if not state.latest_image_bytes:
            raise HTTPException(status_code=404, detail="No frames captured yet.")
        return Response(content=state.latest_image_bytes, media_type="image/jpeg")

    @app.get("/api/snapshot/{record_id}")
    async def get_snapshot(record_id: int, request: Request):
        require_auth(request)
        record = store.get_snapshot(record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Snapshot not found.")
        return Response(content=record.image_bytes, media_type="image/jpeg")


def create_viewer_app(
    state_store: Optional[ViewerStateStore] = None,
    config: Optional[AppConfig] = None,
) -> FastAPI:
    """Factory creating FastAPI application attached to a ViewerStateStore."""
    cfg = config or load_config()
    store = state_store or default_state_store
    app_instance = FastAPI(title="Soonsim Detector - Web Viewer")
    _register_auth_routes(app_instance, cfg)
    _register_telemetry_routes(app_instance, store, cfg)
    _register_snapshot_routes(app_instance, store, cfg)
    return app_instance


app = create_viewer_app()


def main() -> None:
    """Run unified detector and viewer daemon."""
    from src.main import main as run_detector
    run_detector()


if __name__ == "__main__":
    main()
