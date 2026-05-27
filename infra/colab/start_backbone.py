"""BhashAI translation backbone — Colab launcher (one file, no manual steps).

Boots IndicTrans2-1B + an Indian-tuned LLM behind a single tunneled endpoint that
BhashAI's parser-service can hit as both LLM_BASE_URL and INDICTRANS_SERVICE_URL.

Auto-tiers the LLM by detected VRAM:

  ≥48 GB (A100-80GB / H100)   → Sarvam-M-24B  bf16   (best quality)
  ≥18 GB (A100-40GB / L4-24)  → Sarvam-M-24B  AWQ    (good quality, ~14 GB)
  ≥14 GB (T4-16GB / V100-16)  → Qwen-2.5-7B   AWQ    (fallback, smaller but solid)

Override at the top of the cell:
  os.environ['BHASHAI_LLM_MODEL']     = 'sarvamai/sarvam-m'           # bf16 repo
  os.environ['BHASHAI_LLM_QUANT']     = 'awq_marlin'                  # or '' for bf16
  os.environ['BHASHAI_API_KEY']       = 'pick-something-random'
  os.environ['HF_TOKEN']              = 'hf_xxxx'                     # required
  os.environ['BHASHAI_TUNNEL']        = 'cloudflared'                 # or 'ngrok' if you set NGROK_AUTH_TOKEN

Usage from a Colab cell:
  !wget -qO - https://raw.githubusercontent.com/pranshu26/bhashai/main/infra/colab/start_backbone.py | python3 -
or:
  !git clone https://github.com/pranshu26/bhashai.git
  !cd bhashai && HF_TOKEN=$HF_TOKEN python3 infra/colab/start_backbone.py

The script blocks once everything's up. When it prints the env block, paste it into
your BhashAI parser-service .env and restart pm2.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _run(cmd, **kw):
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.run(cmd, check=True, **kw)


def _pip_install(*pkgs):
    _run([sys.executable, "-m", "pip", "install", "-q", *pkgs])


def _ensure_repo() -> Path:
    """Return the bhashai repo root — clone it if we're not already inside it."""
    here = Path.cwd()
    for p in [here, *here.parents]:
        if (p / "services" / "indictrans" / "app.py").exists():
            return p
    print("==> Cloning bhashai repo (we need services/indictrans/app.py + langs.py)")
    _run(["git", "clone", "--depth", "1", "https://github.com/pranshu26/bhashai.git"])
    return Path("bhashai").resolve()


def _detect_gpu() -> tuple[str, int]:
    """Returns (gpu_name, vram_mib). vram_mib=0 if no GPU."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True,
        ).strip().splitlines()
        name, mem = out[0].split(",")
        return name.strip(), int(mem.strip())
    except Exception as e:
        print(f"WARN: nvidia-smi failed ({e}). Running in CPU mode — Sarvam-M won't work.")
        return "cpu", 0


def _pick_model(vram_mib: int) -> tuple[str, str, str]:
    """Returns (hf_repo, quant_arg, served_name)."""
    override_model = os.environ.get("BHASHAI_LLM_MODEL")
    override_quant = os.environ.get("BHASHAI_LLM_QUANT")
    if override_model:
        return override_model, override_quant or "", "sarvam-m"

    if vram_mib >= 48_000:
        return "sarvamai/sarvam-m", "", "sarvam-m"
    if vram_mib >= 18_000:
        return "sarvamai/sarvam-m-awq", "awq_marlin", "sarvam-m"
    if vram_mib >= 14_000:
        # T4/V100 fallback — smaller model but still solid for Hindi/Marathi/Bengali
        return "Qwen/Qwen2.5-7B-Instruct-AWQ", "awq_marlin", "qwen-7b"
    raise SystemExit(f"GPU VRAM {vram_mib} MiB is too small. Need ≥14 GiB.")


def _setup_tunnel(port: int) -> str:
    """Pick cloudflared (zero-config) by default; ngrok if NGROK_AUTH_TOKEN is set + chosen."""
    choice = os.environ.get("BHASHAI_TUNNEL", "cloudflared").lower()

    if choice == "ngrok":
        _pip_install("pyngrok")
        from pyngrok import conf, ngrok
        token = os.environ.get("NGROK_AUTH_TOKEN")
        if not token:
            raise SystemExit("BHASHAI_TUNNEL=ngrok needs NGROK_AUTH_TOKEN")
        conf.get_default().auth_token = token
        return ngrok.connect(port, "http").public_url

    # cloudflared — easier
    if not shutil.which("cloudflared"):
        print("==> Installing cloudflared")
        _run(
            "wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/"
            "cloudflared-linux-amd64 -O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared",
            shell=True,
        )
    print("==> Starting cloudflared quick tunnel")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url_re = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
    for _ in range(60):
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.5)
            continue
        sys.stdout.write(line)
        m = url_re.search(line)
        if m:
            return m.group(0)
    raise SystemExit("cloudflared tunnel didn't print a URL within 30s")


def _wait_http(url: str, label: str, timeout: int = 600) -> None:
    """Block until the URL responds with 2xx/4xx (so 401 from an auth-gated endpoint counts)."""
    print(f"==> Waiting for {label} at {url} (up to {timeout}s)…")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                print(f"   ✓ {label} responded {r.status}")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                print(f"   ✓ {label} responded {e.code} (good enough)")
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"timeout waiting for {label}")


def main() -> int:
    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN env required. Get one at https://huggingface.co/settings/tokens")

    api_key = os.environ.setdefault("BHASHAI_API_KEY", secrets.token_hex(16))

    print("==> Detecting GPU")
    gpu_name, vram = _detect_gpu()
    print(f"   GPU: {gpu_name}  VRAM: {vram} MiB")

    llm_repo, llm_quant, served = _pick_model(vram)
    print(f"   LLM: {llm_repo}  quant={llm_quant or 'bf16'}  served-as={served}")

    repo = _ensure_repo()
    indictrans_dir = repo / "services" / "indictrans"

    print("==> Installing Python deps (vLLM + transformers + IndicTransToolkit + FastAPI)")
    _pip_install(
        "vllm==0.6.6",
        "torch>=2.4,<2.6",
        "transformers>=4.44,<5",
        "sentencepiece",
        "IndicTransToolkit",
        "fastapi>=0.115",
        "uvicorn[standard]>=0.32",
        "httpx>=0.27",
        "pydantic>=2.9",
    )

    print("==> Pre-downloading models (parallel)")
    import concurrent.futures as cf
    from huggingface_hub import snapshot_download
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(snapshot_download, "ai4bharat/indictrans2-en-indic-1B", token=os.environ["HF_TOKEN"])
        f2 = ex.submit(snapshot_download, llm_repo, token=os.environ["HF_TOKEN"])
        for f, name in [(f1, "IndicTrans2-1B"), (f2, llm_repo)]:
            try:
                f.result()
                print(f"   ✓ {name}")
            except Exception as e:
                if name == llm_repo and "awq" in llm_repo.lower():
                    print(f"   ✗ {name} — repo not found.")
                    print("     Either set BHASHAI_LLM_MODEL=sarvamai/sarvam-m and BHASHAI_LLM_QUANT='' "
                          "(needs ≥48 GiB VRAM), or pick a different AWQ repo.")
                raise

    print("==> Starting IndicTrans2 server on :8001")
    env_it = {
        **os.environ,
        "INDICTRANS_MODEL": "ai4bharat/indictrans2-en-indic-1B",
        "INDICTRANS_NUM_BEAMS": "1",
        "INDICTRANS_BATCH": "32",
    }
    it_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8001"],
        cwd=str(indictrans_dir), env=env_it,
    )

    print(f"==> Starting vLLM on :8002 (model={llm_repo})")
    vllm_cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", llm_repo,
        "--served-model-name", served,
        "--host", "127.0.0.1", "--port", "8002",
        "--max-model-len", "8192",
        "--gpu-memory-utilization", "0.80",
        "--enforce-eager",
        "--disable-log-requests",
    ]
    if llm_quant:
        vllm_cmd += ["--quantization", llm_quant]
    vllm_proc = subprocess.Popen(vllm_cmd, env={**os.environ, "HF_TOKEN": os.environ["HF_TOKEN"]})

    _wait_http("http://127.0.0.1:8001/health", "IndicTrans2", timeout=300)
    _wait_http("http://127.0.0.1:8002/v1/models", "vLLM (Sarvam-M)", timeout=900)

    print("==> Starting auth/proxy on :8080")
    proxy_script = Path("/tmp/bhashai_proxy.py")
    proxy_script.write_text(_PROXY_SOURCE.format(api_key=api_key))
    proxy_proc = subprocess.Popen(
        [sys.executable, str(proxy_script)],
        env={**os.environ, "BHASHAI_API_KEY": api_key},
    )
    _wait_http("http://127.0.0.1:8080/health", "auth proxy", timeout=60)

    url = _setup_tunnel(8080)

    # Final env block — paste this into the parser-service .env
    print("\n" + "=" * 78)
    print("BACKBONE LIVE")
    print("=" * 78)
    print(f"  Public URL: {url}")
    print(f"  API key:    {api_key}")
    print()
    print("Paste into your BhashAI parser-service .env (then `pm2 restart bhashai-parser bhashai-worker`):")
    print()
    print(f"  TRANSLATE_ENGINE=indictrans+llm")
    print(f"  INDICTRANS_SERVICE_URL={url}")
    print(f"  LLM_BASE_URL={url}/v1")
    print(f"  LLM_API_KEY={api_key}")
    print(f"  LLM_MODEL={served}")
    print()
    print("Verify (from your laptop):")
    print(f"  curl -s {url}/v1/chat/completions -H 'Authorization: Bearer {api_key}' \\")
    print(f"       -H 'Content-Type: application/json' \\")
    print(f"       -d '{{\"model\":\"{served}\",\"messages\":[{{\"role\":\"user\",\"content\":\"Translate to Hindi: The student opens the laptop.\"}}],\"max_tokens\":80}}'")
    print()
    print(f"  curl -s {url}/translate_batch -H 'Authorization: Bearer {api_key}' \\")
    print(f"       -H 'Content-Type: application/json' \\")
    print(f"       -d '{{\"texts\":[\"The student opens the laptop.\"],\"source\":\"en\",\"target\":\"hi\"}}'")
    print()
    print("This Colab session will auto-die in 12-24h. For production, run infra/aws-gpu/bootstrap.sh.")
    print("Press Ctrl+C (or interrupt the cell) to tear everything down.")
    print("=" * 78)

    # Block forever; clean shutdown on signal
    def _cleanup(*_):
        print("\n==> Tearing down")
        for p in (proxy_proc, vllm_proc, it_proc):
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)
    signal.pause()
    return 0


_PROXY_SOURCE = '''\
"""Single-port reverse proxy in front of IndicTrans2 (:8001) + vLLM (:8002) with a bearer-token gate.
Matches what infra/aws-gpu/nginx.conf does — keeps the parser-service config identical between Colab and AWS."""
import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException

API_KEY = os.environ["BHASHAI_API_KEY"]
app = FastAPI()
client = httpx.AsyncClient(timeout=httpx.Timeout(1200.0))


def _check(auth: str | None) -> None:
    if auth != f"Bearer {{API_KEY}}":
        raise HTTPException(401, "unauthorized")


async def _forward(request: Request, target: str) -> Response:
    headers = {{k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}}
    body = await request.body()
    r = await client.request(request.method, target, content=body, headers=headers)
    out_headers = {{k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "transfer-encoding")}}
    return Response(content=r.content, status_code=r.status_code, headers=out_headers,
                    media_type=r.headers.get("content-type"))


@app.get("/health")
async def health() -> dict:
    return {{"ok": True}}


@app.api_route("/v1/{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def vllm_proxy(path: str, request: Request) -> Response:
    _check(request.headers.get("authorization"))
    return await _forward(request, f"http://127.0.0.1:8002/v1/{{path}}")


@app.post("/translate_batch")
async def indictrans_batch(request: Request) -> Response:
    _check(request.headers.get("authorization"))
    return await _forward(request, "http://127.0.0.1:8001/translate_batch")


@app.post("/translate")
async def indictrans_one(request: Request) -> Response:
    _check(request.headers.get("authorization"))
    return await _forward(request, "http://127.0.0.1:8001/translate")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
'''


if __name__ == "__main__":
    sys.exit(main())
