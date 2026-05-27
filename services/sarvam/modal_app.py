"""BhashAI · Sarvam-M (24B, Indic-specialised) on Modal — serverless GPU, scale-to-zero.

Status: experimental, not in the active deploy. Production currently uses an OpenAI-compatible
hosted LLM (OpenRouter Qwen-2.5-72B by default — see services/parser/llm_postedit.py). Kept as
the reference recipe for self-hosting an Indic-tuned LLM behind the same OpenAI-compatible
shape: swap LLM_BASE_URL to this Modal endpoint and the rest of the pipeline is unchanged.

Serves an OpenAI-compatible API (via vLLM) used by the parser's LLM post-edit layer to refine
IndicTrans2 drafts into fluent, correct Indian-language text. Replaces the Claude post-edit.

ONE-TIME SETUP (run locally; you already have `modal token new` + the `huggingface` secret):
  1. Accept the model terms once at https://huggingface.co/sarvamai/sarvam-m (if gated).
  2. modal deploy services/sarvam/modal_app.py        # first build bakes the 48GB weights (~10 min)
Then point BhashAI at it (parser env):
  LLM_PROVIDER=sarvam
  LLM_BASE_URL=https://<your>--bhashai-sarvam-serve.modal.run/v1
  LLM_MODEL=sarvam-m
Endpoints (standard OpenAI shape): GET /v1/models, POST /v1/chat/completions.

Cold start is kept low by (a) baking weights into the image (no runtime download) and
(b) --enforce-eager (skips CUDA-graph capture). A100-80GB billed per-second only while serving;
scales to zero ~5 min after the last request.
"""
import modal

MODEL = "sarvamai/sarvam-m"          # 24B, Mistral-Small arch, Indian-language post-trained
SERVED_NAME = "sarvam-m"             # the `model` name OpenAI clients send


def _download_model():
    """Runs at image-build time so the 48GB of weights are baked into the image (no cold-start
    download — the previous Volume-cache approach was re-downloading on every cold start)."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, ignore_patterns=["*.pt", "*.pth", "original/*", "consolidated*"])


vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.8.5", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})  # fast (multi-conn) download during build
    .run_function(_download_model, secrets=[modal.Secret.from_name("huggingface")])
)

app = modal.App("bhashai-sarvam")


@app.function(
    image=vllm_image,
    gpu="A100-80GB",             # 24B in bf16 (~48GB) + KV cache fits comfortably
    scaledown_window=300,        # stay warm 5 min after the last request, then scale to zero
    timeout=20 * 60,
    secrets=[modal.Secret.from_name("huggingface")],
)
@modal.concurrent(max_inputs=32)   # one container; vLLM continuous-batches concurrent post-edits
@modal.web_server(port=8000, startup_timeout=10 * 60)
def serve():
    import subprocess

    cmd = (
        f"vllm serve {MODEL} "
        f"--served-model-name {SERVED_NAME} "
        "--host 0.0.0.0 --port 8000 "
        "--max-model-len 8192 "          # post-edit inputs are short; keeps KV-cache small
        "--gpu-memory-utilization 0.92 "
        "--enforce-eager "               # skip CUDA-graph capture -> much faster cold start
        "--disable-log-requests"
    )
    subprocess.Popen(cmd, shell=True)
