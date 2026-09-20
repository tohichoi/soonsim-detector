"""Configuration management using TOML and Pydantic."""

from pathlib import Path
import sys
from typing import List, Tuple
from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class CameraConfig(BaseModel):
    source: str = Field(default="rtsp://admin:password@192.168.0.100:554/stream2")
    fps: int = Field(default=15, ge=1, le=60)
    reconnect_interval_sec: float = Field(default=3.0, ge=0.5)


class ZoneConfig(BaseModel):
    polygon: List[Tuple[int, int]] = Field(
        default=[[180, 140], [460, 140], [460, 330], [180, 330]]
    )


class DetectorConfig(BaseModel):
    model_name: str = Field(default="yolov8n.pt")
    confidence_threshold: float = Field(default=0.30, ge=0.1, le=1.0)
    animal_class_ids: List[int] = Field(default=[15, 16])
    track_thresh: float = Field(default=0.20, ge=0.1, le=1.0)
    match_thresh: float = Field(default=0.8, ge=0.1, le=1.0)
    inference_interval_frames: int = Field(default=5, ge=1, le=30)
    motion_gate_enabled: bool = Field(default=True)
    motion_threshold: float = Field(default=4.0, ge=0.5, le=50.0)
    failsafe_interval_sec: float = Field(default=30.0, ge=1.0, le=300.0)
    max_threads: int = Field(default=2, ge=1, le=16)


class RecorderConfig(BaseModel):
    pre_buffer_sec: int = Field(default=5, ge=1, le=30)
    post_buffer_sec: int = Field(default=5, ge=1, le=30)
    output_dir: Path = Field(default=Path("./records"))
    min_stay_duration_sec: float = Field(default=1.0, ge=0.1)


class TelegramConfig(BaseModel):
    enabled: bool = Field(default=False)
    bot_token: str = Field(default="")
    chat_id: str = Field(default="")


class ViewerConfig(BaseModel):
    enabled: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1, le=65535)
    pin: str = Field(default="1290")
    session_secret: str = Field(default="soonsim-viewer-auth-token-salt")
    retention_sec: float = Field(default=1800.0, ge=60.0)


class LoggingConfig(BaseModel):
    level: str = Field(default="INFO")


class AppConfig(BaseModel):
    camera: CameraConfig = Field(default_factory=CameraConfig)
    zone: ZoneConfig = Field(default_factory=ZoneConfig)
    detector: DetectorConfig = Field(default_factory=DetectorConfig)
    recorder: RecorderConfig = Field(default_factory=RecorderConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    viewer: ViewerConfig = Field(default_factory=ViewerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: str | Path = "config/config.toml") -> AppConfig:
    """Load and validate configuration from TOML file."""
    path = Path(config_path)
    if not path.exists():
        example_path = Path("config/config.example.toml")
        if example_path.exists():
            path = example_path
        else:
            return AppConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return AppConfig.model_validate(data)
