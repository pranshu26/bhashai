#!/usr/bin/env bash
# Bootstrap the BhashAI translation backbone on an AWS GPU instance.
# Idempotent — safe to rerun on upgrade.
#
# Required env:
#   API_KEY     bearer token clients will send (any random string)
#   HF_TOKEN    HuggingFace read token (after accepting the model terms once)
# Optional env:
#   MODEL_TIER  "awq" (default, fits g6e.xlarge) | "bf16" (needs g5.12xlarge+ or g6e.2xlarge x2)
#   DOMAIN      DNS name pointing at this instance (for Let's Encrypt cert). Omit to serve plain HTTP on :80.
#   SARVAM_AWQ_MODEL    overrides the AWQ repo (default: try sarvamai/sarvam-m-awq then community fallback)
#   SARVAM_BF16_MODEL   bf16 repo (default: sarvamai/sarvam-m)
#   INDICTRANS_MODEL    NMT model id (default: ai4bharat/indictrans2-en-indic-1B)
#
# Tested AMI: NVIDIA Deep Learning OSS Ubuntu 22.04 (DLAMI; ships CUDA 12.x + nvidia-driver +
# docker + nvidia-container-toolkit). On a vanilla Ubuntu 22.04 you'd need to install those
# first — out of scope here.

set -euo pipefail

: "${API_KEY:?API_KEY env var required (e.g. export API_KEY=\"\$(openssl rand -hex 32)\")}"
: "${HF_TOKEN:?HF_TOKEN env var required (HuggingFace read token)}"
MODEL_TIER="${MODEL_TIER:-awq}"
DOMAIN="${DOMAIN:-}"
SARVAM_AWQ_MODEL="${SARVAM_AWQ_MODEL:-sarvamai/sarvam-m-awq}"
SARVAM_BF16_MODEL="${SARVAM_BF16_MODEL:-sarvamai/sarvam-m}"
INDICTRANS_MODEL="${INDICTRANS_MODEL:-ai4bharat/indictrans2-en-indic-1B}"

INSTALL_DIR="/opt/bhashai"
VENV="${INSTALL_DIR}/venv"
MODELS_DIR="${INSTALL_DIR}/models"
LOG_DIR="/var/log/bhashai"

echo "==> 0/8  Sanity checks"
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Are you on the NVIDIA Deep Learning AMI?" >&2
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

GPU_MEM_MIB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
if [[ "${MODEL_TIER}" == "awq" && "${GPU_MEM_MIB}" -lt 40000 ]]; then
  echo "WARN: GPU has <40 GiB VRAM (${GPU_MEM_MIB} MiB). AWQ Sarvam-M wants ≥40 GiB headroom; consider MODEL_TIER=bf16 with more VRAM." >&2
fi

echo "==> 1/8  System packages"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3.11 python3.11-venv python3.11-dev \
  build-essential pkg-config git curl jq \
  nginx ca-certificates

if [[ -n "${DOMAIN}" ]]; then
  sudo apt-get install -y --no-install-recommends certbot python3-certbot-nginx
fi

echo "==> 2/8  Python venv at ${VENV}"
sudo mkdir -p "${INSTALL_DIR}" "${MODELS_DIR}" "${LOG_DIR}"
sudo chown -R "$(whoami)":"$(whoami)" "${INSTALL_DIR}" "${LOG_DIR}"

if [[ ! -d "${VENV}" ]]; then
  python3.11 -m venv "${VENV}"
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
# vLLM ships CUDA wheels; transformers + IndicTransToolkit for the NMT side; autoawq optional.
pip install \
  "vllm==0.6.6" \
  "torch>=2.4,<2.6" \
  "transformers>=4.44,<5" \
  "sentencepiece" \
  "IndicTransToolkit" \
  "fastapi" "uvicorn[standard]" "pydantic"
if [[ "${MODEL_TIER}" == "awq" ]]; then
  pip install "autoawq>=0.2.6" || echo "autoawq install failed — only needed if you self-quantize"
fi

echo "==> 3/8  HuggingFace login (so model downloads work)"
mkdir -p "$HOME/.cache/huggingface"
export HF_HOME="${MODELS_DIR}/hf"
mkdir -p "${HF_HOME}"
echo "${HF_TOKEN}" > "${HF_HOME}/token"
chmod 600 "${HF_HOME}/token"

echo "==> 4/8  Pre-download models so first request is instant"
python - <<PY
import os
os.environ.setdefault("HF_HOME", "${HF_HOME}")
os.environ.setdefault("HF_TOKEN", "${HF_TOKEN}")
from huggingface_hub import snapshot_download

print("• IndicTrans2:", "${INDICTRANS_MODEL}")
snapshot_download("${INDICTRANS_MODEL}", token="${HF_TOKEN}")

tier = "${MODEL_TIER}"
sarvam = "${SARVAM_AWQ_MODEL}" if tier == "awq" else "${SARVAM_BF16_MODEL}"
print("• Sarvam-M (", tier, "):", sarvam)
try:
    snapshot_download(sarvam, token="${HF_TOKEN}")
except Exception as e:
    print("MODEL DOWNLOAD FAILED:", e)
    if tier == "awq":
        print("Hint: no AWQ build of Sarvam-M is published yet. Either:")
        print("  - set SARVAM_AWQ_MODEL=<community awq repo> and rerun, or")
        print("  - set MODEL_TIER=bf16 and rerun on an instance with ≥48 GiB VRAM, or")
        print("  - quantize yourself: python ${INSTALL_DIR}/scripts/quantize_sarvam.py")
    raise
PY

echo "==> 5/8  Vendor the IndicTrans2 FastAPI service (from the repo)"
REPO_ROOT="$(git rev-parse --show-toplevel)"
mkdir -p "${INSTALL_DIR}/indictrans"
cp "${REPO_ROOT}/services/indictrans/app.py" "${INSTALL_DIR}/indictrans/app.py"
cp "${REPO_ROOT}/services/indictrans/langs.py" "${INSTALL_DIR}/indictrans/langs.py"

echo "==> 6/8  systemd units"
SARVAM_MODEL_ARG="${SARVAM_AWQ_MODEL}"
SARVAM_EXTRA_ARGS="--quantization awq_marlin"
if [[ "${MODEL_TIER}" == "bf16" ]]; then
  SARVAM_MODEL_ARG="${SARVAM_BF16_MODEL}"
  SARVAM_EXTRA_ARGS=""
fi

sudo tee /etc/systemd/system/bhashai-indictrans.service >/dev/null <<UNIT
[Unit]
Description=BhashAI IndicTrans2 NMT service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}/indictrans
Environment=HF_HOME=${HF_HOME}
Environment=HF_TOKEN=${HF_TOKEN}
Environment=INDICTRANS_MODEL=${INDICTRANS_MODEL}
Environment=INDICTRANS_NUM_BEAMS=1
Environment=INDICTRANS_BATCH=64
Environment=CUDA_VISIBLE_DEVICES=0
ExecStart=${VENV}/bin/uvicorn app:app --host 127.0.0.1 --port 8001
Restart=always
RestartSec=5
StandardOutput=append:${LOG_DIR}/indictrans.log
StandardError=append:${LOG_DIR}/indictrans.log

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/bhashai-sarvam.service >/dev/null <<UNIT
[Unit]
Description=BhashAI Sarvam-M-24B (vLLM, OpenAI-compatible)
After=network-online.target bhashai-indictrans.service
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${INSTALL_DIR}
Environment=HF_HOME=${HF_HOME}
Environment=HF_TOKEN=${HF_TOKEN}
Environment=CUDA_VISIBLE_DEVICES=0
# vLLM with paged attention + (optional) AWQ Marlin kernels. served-model-name sticks even
# if SARVAM_MODEL_ARG points at a community repo — clients always send "sarvam-m".
ExecStart=${VENV}/bin/vllm serve ${SARVAM_MODEL_ARG} \\
  --served-model-name sarvam-m \\
  --host 127.0.0.1 --port 8002 \\
  --max-model-len 8192 \\
  --gpu-memory-utilization 0.80 \\
  --enforce-eager \\
  --disable-log-requests \\
  ${SARVAM_EXTRA_ARGS}
Restart=always
RestartSec=10
StandardOutput=append:${LOG_DIR}/sarvam.log
StandardError=append:${LOG_DIR}/sarvam.log

[Install]
WantedBy=multi-user.target
UNIT

echo "==> 7/8  nginx reverse-proxy (bearer-token auth)"
sudo tee /etc/nginx/sites-available/bhashai-backbone >/dev/null <<NGINX
# Map keeps the secret out of the request log + makes rotation a one-line edit.
map \$http_authorization \$auth_ok {
    "Bearer ${API_KEY}"  1;
    default              0;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${DOMAIN:-_};

    client_max_body_size 16M;
    # Long-running translations: vLLM can take >60s on cold start / large batches.
    proxy_read_timeout 1200s;
    proxy_send_timeout 60s;
    proxy_connect_timeout 30s;
    proxy_buffering off;

    if (\$auth_ok = 0) { return 401; }

    location /health {
        # aggregate health: both services must be up
        proxy_pass http://127.0.0.1:8001/health;
    }

    location /v1/ {
        proxy_pass http://127.0.0.1:8002/v1/;
        proxy_set_header Host \$host;
    }

    location /translate {
        proxy_pass http://127.0.0.1:8001/translate;
    }

    location /translate_batch {
        proxy_pass http://127.0.0.1:8001/translate_batch;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/bhashai-backbone /etc/nginx/sites-enabled/bhashai-backbone
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

if [[ -n "${DOMAIN}" ]]; then
  echo "==> 7b/8  Let's Encrypt cert for ${DOMAIN}"
  sudo certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos --register-unsafely-without-email --redirect || \
    echo "WARN: certbot failed — falling back to plain HTTP on :80"
fi

echo "==> 8/8  Start services"
sudo systemctl daemon-reload
sudo systemctl enable --now bhashai-indictrans.service bhashai-sarvam.service

sleep 5
echo
echo "✓ IndicTrans2  http://127.0.0.1:8001/health  -> $(curl -fsS http://127.0.0.1:8001/health 2>/dev/null || echo 'starting...')"
echo "✓ Sarvam-M     http://127.0.0.1:8002/v1/models  (cold start ~60-90s — check journalctl -u bhashai-sarvam -f)"
if [[ -n "${DOMAIN}" ]]; then
  echo "✓ Public API   https://${DOMAIN}/v1/models    (auth: Bearer \$API_KEY)"
  echo "✓ Public NMT   https://${DOMAIN}/translate_batch"
else
  PUBIP=$(curl -fsS http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "<your-instance-ip>")
  echo "✓ Public API   http://${PUBIP}/v1/models    (auth: Bearer \$API_KEY)"
  echo "✓ Public NMT   http://${PUBIP}/translate_batch"
fi
echo
echo "API_KEY (save this): ${API_KEY}"
