#!/usr/bin/env bash
set -e

echo "=== 1. Generating Mock Video ==="
uv run python scripts/create_mock_video.py

echo "=== 2. Running Pytest Suite ==="
uv run pytest -v

echo "=== 3. Running Local Service Test (16s) ==="
cat << 'CONFIG_EOF' > config/config.local.toml
[camera]
source = "sample.mp4"
fps = 15
reconnect_interval_sec = 1.0

[zone]
polygon = [
    [180, 140],
    [460, 140],
    [460, 330],
    [180, 330]
]

[detector]
model_name = "yolov8n.pt"
confidence_threshold = 0.3
animal_class_ids = [15, 16]
track_thresh = 0.25
match_thresh = 0.8

[recorder]
pre_buffer_sec = 3
post_buffer_sec = 3
output_dir = "./records"
min_stay_duration_sec = 1.0

[telegram]
enabled = false
bot_token = "MOCK_TOKEN"
chat_id = "MOCK_CHAT"

[logging]
level = "INFO"
CONFIG_EOF

timeout 20s uv run python -m src.main --config config/config.local.toml --no-dashboard || true

echo "=== 4. Checking Output Records ==="
ls -lh records/
echo "Local testing completed successfully."
