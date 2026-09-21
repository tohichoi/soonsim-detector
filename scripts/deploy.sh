#!/usr/bin/env bash
set -e

REMOTE_HOST="soonsim"
REMOTE_DIR="~/soonsim-detector"

echo "=== 1. Checking SSH Connection to ${REMOTE_HOST} ==="
ssh -q -o BatchMode=yes -o ConnectTimeout=5 "${REMOTE_HOST}" "echo 'SSH Connection OK'" || {
    echo "Error: Cannot connect to ${REMOTE_HOST}. Please verify SSH credentials."
    exit 1
}

echo "=== 2. Creating Remote Project Directory on Synology NAS ==="
ssh "${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}/config ${REMOTE_DIR}/records"

echo "=== 3. Syncing Files to Remote NAS ==="
rsync -avz --delete -e "ssh" --rsync-path="/bin/rsync" \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude 'records/*.mp4' \
    --exclude 'records/*.jpg' \
    --exclude 'records/*.log' \
    --exclude 'records/*.jsonl' \
    --exclude '.pytest_cache' \
    ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "=== 4. Building Base Image and Starting Multi-Service Containers on NAS ==="
ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker build --network=host -t soonsim-detector:latest . && docker compose down --remove-orphans 2>/dev/null || true; docker rm -f soonsim-detector soonsim-viewer soonsim-tunnel soonsim-ngrok 2>/dev/null || true; docker network prune -f 2>/dev/null || true; docker compose up -d --force-recreate"

echo "=== 5. Checking Remote Containers Status ==="
ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker compose ps"

echo ""
echo "=================================================================="
echo " Deploy to Synology NAS (${REMOTE_HOST}) completed successfully!"
echo " Permanent External HTTPS URL:  https://blend-replay-canary.ngrok-free.dev"
echo " Local LAN Viewer URL:          http://192.168.45.63:8080"
echo "=================================================================="
