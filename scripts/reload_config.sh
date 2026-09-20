#!/usr/bin/env bash
set -e

REMOTE_HOST="soonsim"
REMOTE_DIR="~/soonsim-detector"

echo "=== 1. Syncing config.toml to ${REMOTE_HOST} ==="
rsync -avz -e "ssh" --rsync-path="/bin/rsync" ./config/config.toml "${REMOTE_HOST}:${REMOTE_DIR}/config/config.toml"

echo "=== 2. Restarting container on ${REMOTE_HOST} (no build required) ==="
ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker compose restart soonsim-detector"

echo ""
echo "=================================================================="
echo " Configuration updated and applied in ~2 seconds!"
echo " Local LAN Viewer:    http://192.168.45.63:8080"
echo " External HTTPS URL:  https://blend-replay-canary.ngrok-free.dev"
echo "=================================================================="
