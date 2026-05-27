# BhashAI translation backbone on AWS GPU

A single GPU box that serves both translation engines behind one nginx endpoint:

```
                                ┌── :8001  IndicTrans2-1B  (FastAPI + transformers)
nginx :443 ──[bearer auth]──────┤
                                └── :8002  Sarvam-M-24B    (vLLM, OpenAI-compatible at /v1)
```

The parser-service points at the same nginx for both NMT (`INDICTRANS_SERVICE_URL`) and
LLM refine (`LLM_BASE_URL`). One API key, one TLS cert, one box to mind.

## What you get

- **Production engine**: `TRANSLATE_ENGINE=indictrans+llm` — IndicTrans2 NMT draft +
  Sarvam-M-24B refine. Indian-language-tuned at both layers. Apache 2.0 + MIT licenses,
  commercial-OK.
- **No rate limits, no per-token cost** — you pay for the GPU you rent, period.
- **No vendor lock-in** — drop-in replacement for OpenRouter/Anthropic/etc via the
  OpenAI-compatible shape.

## Instance choice

| Instance | GPU | VRAM | On-demand | Spot (typical) | Use |
| --- | --- | --- | --- | --- | --- |
| `g6e.xlarge`  | 1× L40S       | 48 GB  | ~$1.86/hr | ~$0.55/hr | **Default**: AWQ-quantized Sarvam-M + IndicTrans2 |
| `g6e.2xlarge` | 1× L40S (more vCPU) | 48 GB | ~$2.24/hr | ~$0.70/hr | Same VRAM, more CPU for nginx + transformers preprocessing |
| `g5.12xlarge` | 4× A10G       | 96 GB  | ~$5.67/hr | ~$2.00/hr | bf16 Sarvam-M (no quantization) — fallback if AWQ doesn't fit your quality bar |

Pick `g6e.xlarge` first. Spot saves ~70%; pair with `--instance-interruption-behavior stop`
so the EBS volume survives reclaim.

## Launch (eu-north-1)

1. **AMI**: NVIDIA Deep Learning OSS Ubuntu 22.04 (latest). Search "Deep Learning OSS Nvidia"
   in the AMI catalog. This gives you CUDA 12.x + Docker + nvidia-container-toolkit out of
   the box.
2. **Disk**: 200 GB gp3 (models + cache).
3. **Security Group**: inbound 443 (your IPs only at first), 22 (your IP only),
   outbound all.
4. **IAM role**: `AmazonSSMManagedInstanceCore` so you don't need SSH keys for ops.

## One-time bootstrap (run on the instance, as ubuntu user)

```bash
# clone the repo
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/<your>/bhashai.git
cd bhashai/infra/aws-gpu

# set required env vars
export API_KEY="$(openssl rand -hex 32)"          # the bearer token clients will send
export HF_TOKEN="hf_xxxxx"                         # your HuggingFace token (read scope)
export MODEL_TIER="awq"                            # awq (default, fits g6e.xlarge) | bf16 (g5.12xlarge+)
export DOMAIN="bhashai-backbone.your-domain.com"   # optional — for Let's Encrypt cert

# go
sudo -E bash bootstrap.sh
```

Bootstrap is idempotent — safe to rerun on upgrade.

When it finishes it prints:

```
✓ IndicTrans2  http://127.0.0.1:8001/health
✓ Sarvam-M     http://127.0.0.1:8002/v1/models
✓ Public API   https://<domain>/v1/models    (auth: Bearer $API_KEY)
✓ Public NMT   https://<domain>/translate_batch
```

## Point BhashAI at the new backbone

Edit your **parser-service `.env`** (on the EC2 box running the BhashAI app):

```bash
TRANSLATE_ENGINE=indictrans+llm
INDICTRANS_SERVICE_URL=https://bhashai-backbone.your-domain.com
LLM_BASE_URL=https://bhashai-backbone.your-domain.com/v1
LLM_API_KEY=<API_KEY from bootstrap>
LLM_MODEL=sarvam-m
```

Then `pm2 restart bhashai-parser bhashai-worker`.

## Auto-shutoff on idle (optional, recommended for spot)

```bash
sudo systemctl enable --now bhashai-idle-shutdown.timer
```

Shuts down the instance if no request hits nginx for 30 min. With Spot + stop interruption
behavior, EBS persists; relaunch is a single `aws ec2 start-instances` (~60 seconds to
back-online once vLLM warms).

## Cost shape

| Scenario | Monthly |
| --- | --- |
| g6e.xlarge spot 24/7 | ~$400 |
| g6e.xlarge spot, idle-shutdown 8h/day | ~$130 |
| g6e.xlarge on-demand 24/7 | ~$1340 |
| g5.12xlarge spot 24/7 (bf16 fallback) | ~$1440 |

Compare to OpenRouter Qwen-2.5-72B at ~$0.08/doc with no rate-limit guarantee: AWS pays
back at roughly 1600 docs/mo (steady) or fewer if you keep idle-shutoff on.

## Health & verification

After bootstrap finishes, run from your laptop:

```bash
# Sarvam-M
curl -s "https://$DOMAIN/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"sarvam-m","messages":[{"role":"user","content":"Translate to Hindi: The student opens the laptop."}],"max_tokens":80}'

# IndicTrans2
curl -s "https://$DOMAIN/translate_batch" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"texts":["The student opens the laptop."],"source":"en","target":"hi"}'
```

Both should return Hindi within a few seconds (warm). Cold start (vLLM model load) is
60-90s after instance start.

## Logs

```bash
journalctl -u bhashai-sarvam     -f      # vLLM
journalctl -u bhashai-indictrans -f      # NMT
sudo tail -f /var/log/nginx/access.log   # request log
```
