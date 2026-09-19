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
    --exclude '.pytest_cache' \
    ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "=== 4. Building Base Image and Starting Multi-Service Containers on NAS ==="
ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker build --network=host -t soonsim-detector:latest . && docker compose down --remove-orphans 2>/dev/null || true; docker rm -f soonsim-detector soonsim-viewer soonsim-tunnel 2>/dev/null || true; docker network prune -f 2>/dev/null || true; docker compose up -d"

echo "=== 5. Checking Remote Containers Status ==="
ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker compose ps"

echo "=== 6. Extracting Cloudflare Tunnel External URL ==="
sleep 6
TUNNEL_URL=$(ssh "${REMOTE_HOST}" "export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker compose logs cloudflared 2>&1" | grep -o 'https://.*\.trycloudflare\.com' | head -n 1 || true)

echo ""
echo "=================================================================="
echo " Deploy to Synology NAS (${REMOTE_HOST}) completed successfully!"
if [ -n "${TUNNEL_URL}" ]; then
    echo " Cloudflare External HTTPS URL: ${TUNNEL_URL}"
else
    echo " Tunnel URL is initializing. Run this command to check:"
    echo " ssh ${REMOTE_HOST} 'export PATH=\$PATH:/var/packages/ContainerManager/target/usr/bin:/usr/syno/bin; cd ${REMOTE_DIR} && docker compose logs cloudflared'"
fi
echo " Local LAN Viewer URL:          http://192.168.45.63:8080"
echo "=================================================================="
