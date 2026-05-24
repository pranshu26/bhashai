# IndicTrans2 service (AI4Bharat)

Self-hosted English→Indian-language NMT. Implements the contract the
`@bhashai/engines` IndicTrans2 adapter calls.

## Endpoints
- `GET  /health` → `{status, device, model, loaded}`
- `POST /translate` `{text, source, target}` → `{translation}`
- `POST /translate_batch` `{texts, source, target}` → `{translations}`

`source`/`target` are BhashAI 2-letter codes (`en`, `hi`, …), mapped to FLORES codes
(`eng_Latn`, `hin_Deva`, …) in `langs.py`.

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### HuggingFace access (required — the model is gated)
1. Open https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M and click
   **"Agree and access repository"** (free; one-time).
2. Create a **read** token at https://huggingface.co/settings/tokens.
3. Export it before running: `export HF_TOKEN=hf_xxx` (or add to the service env).

## Run
```bash
export HF_TOKEN=hf_xxx
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8001
```
Then set `INDICTRANS_SERVICE_URL=http://localhost:8001` in the project `.env`.

## Model
- Default `INDICTRANS_MODEL=ai4bharat/indictrans2-en-indic-dist-200M` (distilled, CPU/MPS-practical).
- For the GPU EC2 box, swap to `ai4bharat/indictrans2-en-indic-1B` for best quality.
- Device auto-selects CUDA → MPS → CPU.
