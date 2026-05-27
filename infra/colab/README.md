# BhashAI translation backbone — Colab fallback

A self-installing launcher that boots **IndicTrans2-1B + an Indian-tuned LLM** on a
Colab GPU runtime, behind a single tunneled endpoint your BhashAI parser-service can
hit. Same API shape as `infra/aws-gpu/` — so the parser `.env` looks identical and you
can swap the URL between Colab and AWS without changing code.

> Use this **only as a temporary backbone** while AWS GPU quota is pending or for
> quality A/B testing. Colab sessions die in 12-24h; production runs on AWS GPU.

## When to use this

- AWS G/VT quota request is still pending (the first request from a fresh account
  usually takes 30 min – 4 hours).
- You want to validate the IndicTrans2 + Sarvam-M two-pass quality on the real
  saathi doc tonight before committing to a GPU instance.
- You're prototyping a different model and don't want to redeploy AWS each time.

## Setup (~5 min)

1. Open https://colab.new in a new tab.
2. **Runtime → Change runtime type → A100 GPU** (Colab Pro+) or **L4 GPU** (Colab Pro).
   - Free T4 will work with a fallback model (Qwen-2.5-7B AWQ) but Sarvam-M-24B
     needs ≥18 GB VRAM (AWQ) or ≥48 GB (bf16).
3. Accept the model terms once on HuggingFace:
   - https://huggingface.co/sarvamai/sarvam-m (and `…-awq` if it exists)
   - https://huggingface.co/ai4bharat/indictrans2-en-indic-1B
4. Create an HF read token: https://huggingface.co/settings/tokens
5. Paste this into the first Colab cell and run:

```python
import os
os.environ["HF_TOKEN"] = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # your HF read token

# Optional overrides:
# os.environ["BHASHAI_LLM_MODEL"] = "sarvamai/sarvam-m-awq"     # AWQ if it exists; else "sarvamai/sarvam-m"
# os.environ["BHASHAI_LLM_QUANT"] = "awq_marlin"                # or "" for bf16
# os.environ["BHASHAI_API_KEY"]   = "pick-anything-long-and-random"
# os.environ["BHASHAI_TUNNEL"]    = "cloudflared"               # or "ngrok" (needs NGROK_AUTH_TOKEN)

!wget -qO - https://raw.githubusercontent.com/pranshu26/bhashai/main/infra/colab/start_backbone.py | python3 -
```

The script:
1. Detects the GPU and picks a model that fits (auto-tier by VRAM)
2. Pip-installs vLLM + transformers + IndicTransToolkit + FastAPI in one shot
3. Pre-downloads both models in parallel (~5-10 min depending on the model size)
4. Starts IndicTrans2 on :8001, vLLM on :8002, an auth proxy on :8080
5. Opens a cloudflared quick tunnel and prints the public URL

When it's up the final output gives you the exact env block to paste into your
BhashAI parser-service `.env`:

```bash
TRANSLATE_ENGINE=indictrans+llm
INDICTRANS_SERVICE_URL=https://<random>.trycloudflare.com
LLM_BASE_URL=https://<random>.trycloudflare.com/v1
LLM_API_KEY=<the auto-generated API key>
LLM_MODEL=sarvam-m
```

Then on your EC2 box (16.171.29.33):
```bash
pm2 restart bhashai-parser bhashai-worker
```

## VRAM tiers (auto-picked)

| VRAM      | GPU examples                | LLM                   | Quality |
|-----------|-----------------------------|-----------------------|---------|
| ≥ 48 GiB | A100-80GB, H100             | Sarvam-M-24B  bf16    | Best    |
| ≥ 18 GiB | A100-40GB, L4-24GB          | Sarvam-M-24B  AWQ     | Strong  |
| ≥ 14 GiB | T4-16GB, V100-16GB          | Qwen-2.5-7B  AWQ      | OK (Hindi/Marathi/Bengali decent; Tamil/Telugu/Kannada/Malayalam noticeably weaker) |

Override with `BHASHAI_LLM_MODEL` + `BHASHAI_LLM_QUANT` env vars if you want a
specific repo.

## Caveats

- **Cloudflared quick-tunnel URLs change** every time the tunnel restarts. If you
  cycle the Colab cell, you must repaste the new URL into the EC2 `.env`. Use
  a named tunnel (cloudflared with a Cloudflare account) if you want a stable URL.
- **Cold start** for vLLM on a 24B model is 60-120s after model download finishes.
- **Colab session limits**: 12h on Pro, 24h on Pro+. Free tier disconnects
  much sooner under load.
- **Sarvam-M AWQ may not be on the HF Hub yet**. If the download in step 4 fails
  with 404, either set `BHASHAI_LLM_MODEL=sarvamai/sarvam-m` and request
  Colab Pro+ for the A100-80GB option, or wait for a community AWQ build.

## A/B the saathi doc against the new backbone

Once the tunnel is up and the EC2 `.env` is updated, run from your laptop:

```bash
cd ~/personal/bhashai/services/parser && source .venv/bin/activate

# Current (Qwen via OpenRouter)
TRANSLATE_ENGINE=llm LLM_BASE_URL=https://openrouter.ai/api/v1 LLM_API_KEY=sk-or-v1-... \
  LLM_MODEL=qwen/qwen-2.5-72b-instruct \
  python scripts/translate_doc.py ~/Downloads/saathi.docx hi -o /tmp/saathi-qwen.docx

# New (Sarvam-M + IndicTrans2 via the Colab tunnel)
TRANSLATE_ENGINE=indictrans+llm INDICTRANS_SERVICE_URL=https://<tunnel>.trycloudflare.com \
  LLM_BASE_URL=https://<tunnel>.trycloudflare.com/v1 LLM_API_KEY=<key> LLM_MODEL=sarvam-m \
  python scripts/translate_doc.py ~/Downloads/saathi.docx hi -o /tmp/saathi-new.docx

# Compare
python scripts/diff_translations.py ~/Downloads/saathi.docx /tmp/saathi-qwen.docx /tmp/saathi-new.docx \
  --target hi -o /tmp/saathi-diff.md
open /tmp/saathi-diff.md
```
