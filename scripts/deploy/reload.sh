#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/generative-ai-vdos"
cd "$APP_DIR"

echo "==> Pulling latest code"
git pull

echo "==> Python deps"
uv sync

echo "==> Frontend deps + build"
cd "$APP_DIR/webapp"
npm ci
npm run build
cd "$APP_DIR"

echo "==> Django migrate"
.venv/bin/python backend/manage.py migrate

echo "==> Restarting services"
sudo systemctl restart generative-ai-vdos-celery-worker generative-ai-vdos-celery-images generative-ai-vdos-backend generative-ai-vdos-frontend

echo "==> Done — service status:"
sudo systemctl --no-pager status generative-ai-vdos-backend generative-ai-vdos-frontend generative-ai-vdos-celery-worker generative-ai-vdos-celery-images || true
