#!/usr/bin/env bash
set -e

REMOTE_HOST="soonsim"
REMOTE_DIR="~/soonsim-detector"

echo "=== 1. Checking SSH Connection to ${REMOTE_HOST} ==="
ssh -q -o BatchMode=yes -o ConnectTimeout=5 "${REMOTE_HOST}" "echo 'SSH Connection OK'" || {
    echo "Error: Cannot connect to ${REMOTE_HOST}. Please verify SSH credentials."
    exit 1
}

echo "=== 2. Creating Remote Project Directory ==="
ssh "${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}/config ${REMOTE_DIR}/records"

echo "=== 3. Syncing Files to Remote NAS ==="
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' --exclude 'records/*.mp4' \
    ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "=== 4. Building and Starting Docker Container on NAS ==="
ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker compose down && docker compose up -d --build"

echo "=== 5. Checking Remote Container Status ==="
ssh "${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker compose ps && docker compose logs --tail=20"

echo "Deploy to Synology NAS (${REMOTE_HOST}) completed successfully."
