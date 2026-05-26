#!/usr/bin/env bash
# BhashAI single-box deploy for Ubuntu 22.04/24.04 (eu-north-1, IP + port 80).
# Run as the default sudo user (e.g. `ubuntu`). Idempotent-ish; safe to re-run.
#   GPU translation runs on Modal (INDICTRANS_SERVICE_URL); this box runs api/worker/web/parser.
#
#   curl -fsSL <repo>/infra/deploy-ec2.sh | bash      # or: bash infra/deploy-ec2.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/pranshu26/bhashai.git}"
APP_DIR="${APP_DIR:-$HOME/bhashai}"

echo "==> 1/8 system packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl git nginx \
  python3-venv python3-pip \
  tesseract-ocr tesseract-ocr-hin tesseract-ocr-eng \
  libraqm0 fonts-noto-core fonts-indic fonts-noto fontconfig \
  docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

echo "==> 2/8 node 22 + pnpm + pm2"
if ! command -v node >/dev/null || [ "$(node -v | cut -dv -f2 | cut -d. -f1)" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
sudo corepack enable && sudo corepack prepare pnpm@10.8.1 --activate
sudo npm i -g pm2 >/dev/null 2>&1 || true

echo "==> 3/8 fetch code"
if [ -f "$APP_DIR/package.json" ] && [ ! -d "$APP_DIR/.git" ]; then
  echo "using pre-synced code at $APP_DIR"
elif [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 4/8 .env (edit secrets if first run)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "!!! Created .env from template — set JWT_SECRET, ANTHROPIC_API_KEY, INDICTRANS_SERVICE_URL,"
  echo "    POSTGRES_PORT, REDIS_PORT, NEXT_PUBLIC_API_URL=http://<EC2-IP>/api, then re-run."
fi
set -a; . ./.env; set +a

echo "==> 5/8 postgres + redis (docker)"
sudo docker compose --env-file .env -f infra/docker-compose.yml up -d postgres redis
until sudo docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres pg_isready -U "${POSTGRES_USER:-bhashai}" >/dev/null 2>&1; do sleep 2; done

echo "==> 6/8 install + build (node) + parser venv (python)"
pnpm install
pnpm --filter @bhashai/db exec prisma generate
# Fresh build: drop dist/.next AND the tsc incremental cache (*.tsbuildinfo lives at the
# package root, not in dist). If it survives, tsc sees "already built" and emits nothing —
# leaving dependents unable to resolve @bhashai/shared.
pnpm -r exec -- sh -c 'rm -rf dist .next ./*.tsbuildinfo' 2>/dev/null || true
# Build one package at a time in explicit dependency order. pnpm -r / turbo don't reliably
# order these (web declares no internal deps), and sequential keeps peak RAM low on 8GB.
for pkg in shared db storage engines parsing api worker web; do
  echo "--- build @bhashai/$pkg ---"
  NODE_OPTIONS=--max-old-space-size=6144 pnpm --filter "@bhashai/$pkg" run build
done
pnpm --filter @bhashai/db exec prisma migrate deploy
python3 -m venv services/parser/.venv
services/parser/.venv/bin/pip install -q -r services/parser/requirements.txt
# Devanagari font for the shaped overlay (find an installed Hindi-capable font)
export BHASHAI_FONT="$(fc-list :lang=hi file 2>/dev/null | sort | head -1 | cut -d: -f1)"
echo "Devanagari font: ${BHASHAI_FONT:-NONE FOUND}"

echo "==> 7/8 start services (pm2 + parser)"
pm2 delete bhashai-parser >/dev/null 2>&1 || true
BHASHAI_FONT="$BHASHAI_FONT" ENABLE_OCR="${ENABLE_OCR:-local}" \
  pm2 start "$APP_DIR/services/parser/.venv/bin/python" \
  --name bhashai-parser --cwd "$APP_DIR/services/parser" --interpreter none \
  -- -m uvicorn app:app --host 127.0.0.1 --port 8000
pm2 delete bhashai-api bhashai-worker bhashai-web >/dev/null 2>&1 || true
pm2 start "node apps/api/dist/main.js"   --name bhashai-api    --cwd "$APP_DIR"
pm2 start "node apps/worker/dist/main.js" --name bhashai-worker --cwd "$APP_DIR"
pm2 start "pnpm --filter @bhashai/web start" --name bhashai-web --cwd "$APP_DIR"
pm2 save
sudo pm2 startup systemd -u "$USER" --hp "$HOME" >/dev/null 2>&1 || true

echo "==> 8/8 nginx (:80 -> web + /api)"
sudo cp infra/nginx/bhashai.conf /etc/nginx/sites-available/bhashai
sudo ln -sf /etc/nginx/sites-available/bhashai /etc/nginx/sites-enabled/bhashai
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo "==> DONE. App should be live at  http://<this-EC2-public-IP>/"
pm2 status
