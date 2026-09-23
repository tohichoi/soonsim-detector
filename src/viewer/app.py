"""FastAPI web viewer application for Soonsim Detector."""

import secrets
import threading
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from src.config import AppConfig, load_config
from src.viewer.clips import list_clips, resolve_clip
from src.viewer.labels import set_label
from src.viewer.state import ViewerStateStore
from src.viewer.templates import HTML_TEMPLATE, LOGIN_HTML_TEMPLATE

AUTH_COOKIE = "soonsim_auth"
SESSION_TTL_SEC = 86400 * 30
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SEC = 300.0

default_state_store = ViewerStateStore()


class LoginRequest(BaseModel):
    pin: str


class ClipLabelRequest(BaseModel):
    """A verdict on one clip; null clears it."""

    label: Optional[str] = None


class SessionStore:
    """Opaque session tokens held in memory.

    Tokens are random, so unlike the previous sha256(pin:secret) cookie nobody
    who learns the PIN can derive them. The trade-off is that restarting the
    process drops every session and clients must log in again.
    """

    def __init__(self, ttl_sec: float = SESSION_TTL_SEC):
        self.ttl_sec = ttl_sec
        self._sessions: dict[str, float] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        """Issue a new token and return it."""
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._prune(now)
            self._sessions[token] = now + self.ttl_sec
        return token

    def is_valid(self, token: Optional[str]) -> bool:
        """True when the token exists and has not expired."""
        if not token:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            return token in self._sessions

    def revoke(self, token: Optional[str]) -> None:
        """Drop a token so it can no longer authenticate."""
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _prune(self, now: float) -> None:
        for token in [t for t, expiry in self._sessions.items() if expiry <= now]:
            del self._sessions[token]


class LoginThrottle:
    """Global failed-attempt throttle for the PIN endpoint.

    The viewer serves a single household, so one global counter is both simpler
    and stricter than per-IP tracking: an attacker cannot spread attempts over
    many addresses to stay under the limit. Locking out is a nuisance for the
    owner, but it is bounded and the attacker never gets through.
    """

    def __init__(self, max_attempts: int = MAX_LOGIN_ATTEMPTS, lockout_sec: float = LOCKOUT_SEC):
        self.max_attempts = max_attempts
        self.lockout_sec = lockout_sec
        self._failures = 0
        self._locked_until = 0.0
        self._lock = threading.Lock()

    def locked_for(self) -> float:
        """Seconds until another attempt is accepted; 0 when allowed."""
        with self._lock:
            return max(0.0, self._locked_until - time.time())

    def record_failure(self) -> None:
        """Count a failed attempt, locking out once the limit is reached."""
        with self._lock:
            self._failures += 1
            if self._failures >= self.max_attempts:
                self._locked_until = time.time() + self.lockout_sec
                self._failures = 0

    def reset(self) -> None:
        """Clear counters after a successful login."""
        with self._lock:
            self._failures = 0
            self._locked_until = 0.0


def check_auth(request: Request, sessions: SessionStore) -> bool:
    """Check if request carries a live session cookie."""
    return sessions.is_valid(request.cookies.get(AUTH_COOKIE))


def _register_auth_routes(
    app: FastAPI,
    cfg: AppConfig,
    sessions: SessionStore,
    throttle: LoginThrottle,
) -> None:
    """Register index, login, and logout endpoints."""
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if check_auth(request, sessions):
            return HTMLResponse(content=HTML_TEMPLATE)
        return HTMLResponse(content=LOGIN_HTML_TEMPLATE)

    @app.post("/api/auth/login")
    async def login(req: LoginRequest, response: Response):
        wait = throttle.locked_for()
        if wait > 0:
            raise HTTPException(
                status_code=429,
                detail=f"로그인 시도가 너무 많습니다. {int(wait) + 1}초 후 다시 시도해주세요.",
            )
        # compare_digest on bytes keeps the comparison constant-time for any PIN,
        # including non-ASCII ones, which the str form rejects.
        if not secrets.compare_digest(req.pin.encode("utf-8"), cfg.viewer.pin.encode("utf-8")):
            throttle.record_failure()
            raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")
        throttle.reset()
        response.set_cookie(
            key=AUTH_COOKIE,
            value=sessions.create(),
            max_age=SESSION_TTL_SEC,
            httponly=True,
            samesite="lax",
        )
        return {"success": True, "detail": "인증 성공"}

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        sessions.revoke(request.cookies.get(AUTH_COOKIE))
        response.delete_cookie(key=AUTH_COOKIE)
        return {"success": True, "detail": "로그아웃 성공"}


def _register_telemetry_routes(app: FastAPI, store: ViewerStateStore, sessions: SessionStore) -> None:
    """Register telemetry and history endpoints."""
    def require_auth(request: Request) -> None:
        if not check_auth(request, sessions):
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


def _register_snapshot_routes(app: FastAPI, store: ViewerStateStore, sessions: SessionStore) -> None:
    """Register snapshot image endpoints."""
    def require_auth(request: Request) -> None:
        if not check_auth(request, sessions):
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


def _register_clip_routes(app: FastAPI, cfg: AppConfig, sessions: SessionStore) -> None:
    """Register recorded clip browsing, playback, and labelling endpoints."""
    def require_auth(request: Request) -> None:
        if not check_auth(request, sessions):
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")

    output_dir = Path(cfg.recorder.output_dir)

    @app.get("/api/clips")
    async def get_clips(request: Request, kind: str = "all"):
        require_auth(request)
        try:
            clips = list_clips(output_dir, kind=kind)
        except ValueError:
            raise HTTPException(status_code=400, detail="알 수 없는 클립 종류입니다.")
        return {"clips": clips}

    @app.get("/api/clips/{name}")
    async def get_clip(name: str, request: Request):
        require_auth(request)
        path = resolve_clip(output_dir, name)
        if path is None:
            raise HTTPException(status_code=404, detail="클립을 찾을 수 없습니다.")
        # FileResponse handles Range requests, which seeking a clip needs.
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/clips/{name}/label")
    async def label_clip(name: str, req: ClipLabelRequest, request: Request):
        require_auth(request)
        if resolve_clip(output_dir, name) is None:
            raise HTTPException(status_code=404, detail="클립을 찾을 수 없습니다.")
        try:
            set_label(output_dir, name, req.label)
        except ValueError:
            raise HTTPException(status_code=400, detail="허용되지 않는 라벨입니다.")
        return {"name": name, "label": req.label}


def create_viewer_app(
    state_store: Optional[ViewerStateStore] = None,
    config: Optional[AppConfig] = None,
) -> FastAPI:
    """Factory creating FastAPI application attached to a ViewerStateStore."""
    cfg = config or load_config()
    store = state_store or default_state_store
    sessions = SessionStore()
    throttle = LoginThrottle()
    app_instance = FastAPI(title="Soonsim Detector - Web Viewer")
    _register_auth_routes(app_instance, cfg, sessions, throttle)
    _register_telemetry_routes(app_instance, store, sessions)
    _register_snapshot_routes(app_instance, store, sessions)
    _register_clip_routes(app_instance, cfg, sessions)
    return app_instance


app = create_viewer_app()


def main() -> None:
    """Run unified detector and viewer daemon."""
    from src.main import main as run_detector
    run_detector()


if __name__ == "__main__":
    main()
