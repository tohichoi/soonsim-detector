#!/usr/bin/env bash
set -e
echo "Starting Soonsim Detector Live Debug Viewer (Port 8080)..."
echo "Open your browser at: http://localhost:8080 or http://<SERVER_IP>:8080"
uv run python -m src.viewer.app
