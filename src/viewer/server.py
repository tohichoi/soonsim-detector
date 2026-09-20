"""Background server runner for Soonsim Detector Web Viewer."""

import socket
import threading
import time
from loguru import logger
import uvicorn
from src.config import AppConfig
from src.viewer.app import create_viewer_app
from src.viewer.state import ViewerStateStore


def find_available_port(host: str = "0.0.0.0", start_port: int = 8080, max_attempts: int = 100) -> int:
    """Find the first available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find an available port in range {start_port} - {start_port + max_attempts}")


class ViewerServer:
    """Manages FastAPI/Uvicorn server running in a background thread."""

    def __init__(self, state_store: ViewerStateStore, config: AppConfig):
        self.state_store = state_store
        self.config = config
        self.app = create_viewer_app(state_store=self.state_store, config=self.config)
        self.server: uvicorn.Server | None = None
        self.thread: threading.Thread | None = None
        self.port = self.config.viewer.port

    def start(self) -> None:
        """Start Uvicorn server in background thread."""
        try:
            self.port = find_available_port(host=self.config.viewer.host, start_port=self.config.viewer.port)
        except RuntimeError as e:
            logger.error(f"Failed to bind viewer port: {e}")
            return

        uv_config = uvicorn.Config(
            app=self.app,
            host=self.config.viewer.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(uv_config)

        def run_uvicorn():
            logger.info(f"Soonsim Web Viewer running at http://localhost:{self.port}")
            self.server.run()

        self.thread = threading.Thread(target=run_uvicorn, daemon=True, name="ViewerServerThread")
        self.thread.start()

    def stop(self) -> None:
        """Gracefully stop background Uvicorn server."""
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.info("Soonsim Web Viewer stopped.")
