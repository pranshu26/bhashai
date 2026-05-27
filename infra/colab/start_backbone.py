"""BhashAI translation backbone — Colab + Mac launcher (one file, no manual steps).

Boots IndicTrans2-1B + Sarvam-M-24B (GGUF, served by llama.cpp) behind a single
tunneled endpoint that BhashAI's parser-service can hit as both LLM_BASE_URL and
INDICTRANS_SERVICE_URL.

Auto-picks a GGUF quant by detected VRAM / unified-memory:

  ≥40 GB (A100-40/80, H100)   → Sarvam-M-24B  Q6_K     (~20 GB; best quality)
  ≥24 GB (L4-24, RTX-3090)    → Sarvam-M-24B  Q5_K_M   (~17 GB; close to lossless)
  ≥18 GB (A100-mig-20, …)     → Sarvam-M-24B  Q4_K_M   (~14 GB; the standard sweet spot)
  ≥14 GB (T4-16, V100-16,M4)  → Sarvam-M-24B  Q3_K_M   (~10 GB; some quality drop)
  < 14 GB                     → error (run a bigger GPU)

Override:
  os.environ['BHASHAI_GGUF_FILE']   = 'sarvamai_sarvam-m-Q4_K_M.gguf'   # any file in the repo
  os.environ['BHASHAI_GGUF_REPO']   = 'bartowski/sarvamai_sarvam-m-GGUF'
  os.environ['BHASHAI_API_KEY']     = 'pick-something-random'
  os.environ['HF_TOKEN']            = 'hf_xxxx'                          # required
  os.environ['BHASHAI_TUNNEL']      = 'cloudflared'                      # or 'ngrok' if NGROK_AUTH_TOKEN

Usage from a Colab cell (after making sarvam-m + indictrans2 model terms accepted on HF):
  !wget -qO - https://raw.githubusercontent.com/pranshu26/bhashai/main/infra/colab/start_backbone.py | python3 -

Locally (Mac M-series — uses Metal automatically):
  HF_TOKEN=hf_xxx python3 infra/colab/start_backbone.py

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


def _detect_compute() -> tuple[str, int]:
    """Returns (kind, vram_mib). kind ∈ {'cuda','metal','cpu'}; vram_mib=0 if no GPU.

    On Apple Silicon, unified-memory total is what matters — we report platform.mac()'s
    `sysctl hw.memsize` so the tier picker still works."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True,
        ).strip().splitlines()
        _name, mem = out[0].split(",")
        return "cuda", int(mem.strip())
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
            return "metal", mem_bytes // (1024 * 1024)
        except Exception:
            pass

    print("WARN: no GPU detected. CPU inference is too slow for Sarvam-M-24B — aborting.")
    return "cpu", 0


# (quant suffix, approx GiB on disk / VRAM at runtime)
_GGUF_TIERS = [
    ("Q6_K",   20),
    ("Q5_K_M", 17),
    ("Q4_K_M", 14),
    ("Q3_K_M", 10),
]


def _pick_gguf(kind: str, vram_mib: int) -> tuple[str, str]:
    """Returns (repo_id, file_name) — picks a quant tier with ≥ 4 GiB headroom for OS + IndicTrans2."""
    repo = os.environ.get("BHASHAI_GGUF_REPO", "bartowski/sarvamai_sarvam-m-GGUF")
    override = os.environ.get("BHASHAI_GGUF_FILE")
    if override:
        return repo, override

    # On Apple Silicon unified memory is shared with OS + IndicTrans2, so reserve more headroom.
    headroom = 6_000 if kind == "metal" else 4_000
    for quant, gib in _GGUF_TIERS:
        if vram_mib >= gib * 1024 + headroom:
            return repo, f"sarvamai_sarvam-m-{quant}.gguf"
    raise SystemExit(
        f"available memory {vram_mib} MiB is too small (need ≥{_GGUF_TIERS[-1][1] * 1024 + headroom} MiB). "
        f"Use a bigger GPU or override BHASHAI_GGUF_FILE with a smaller IQ2/Q2 variant."
    )


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

    # cloudflared — easier (no auth token, random URL on every restart)
    if not shutil.which("cloudflared"):
        print("==> Installing cloudflared")
        import platform
        sysname = platform.system().lower()
        machine = platform.machine().lower()
        asset = {
            ("linux",  "x86_64"):  "cloudflared-linux-amd64",
            ("linux",  "aarch64"): "cloudflared-linux-arm64",
            ("darwin", "arm64"):   "cloudflared-darwin-arm64.tgz",
            ("darwin", "x86_64"):  "cloudflared-darwin-amd64.tgz",
        }.get((sysname, machine))
        if not asset:
            raise SystemExit(f"unsupported platform for cloudflared: {sysname}/{machine}")
        dest = "/usr/local/bin/cloudflared"
        sudo = "" if os.geteuid() == 0 else "sudo "
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{asset}"
        if asset.endswith(".tgz"):
            _run(f"curl -sSL {url} -o /tmp/cf.tgz && tar -xzf /tmp/cf.tgz -C /tmp && "
                 f"{sudo}mv /tmp/cloudflared {dest} && {sudo}chmod +x {dest}", shell=True)
        else:
            _run(f"curl -sSL {url} -o /tmp/cloudflared && {sudo}install -m 0755 /tmp/cloudflared {dest}",
                 shell=True)
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

    print("==> Detecting compute")
    kind, vram = _detect_compute()
    print(f"   kind: {kind}  available memory: {vram} MiB")
    if kind == "cpu":
        raise SystemExit("no GPU/Metal — aborting")

    gguf_repo, gguf_file = _pick_gguf(kind, vram)
    print(f"   LLM:    {gguf_repo} :: {gguf_file}")
    served = "sarvam-m"

    repo = _ensure_repo()
    indictrans_dir = repo / "services" / "indictrans"

    print("==> Installing Python deps (llama-cpp-python + transformers + IndicTransToolkit + FastAPI)")
    # llama-cpp-python: pre-built CUDA wheels for Colab speed, default Metal on macOS.
    extra = []
    if kind == "cuda":
        # CUDA 12.4 wheel index covers the Colab DLAMI driver bundle (Colab usually ships CUDA 12.x).
        extra = ["--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124"]
    _run([sys.executable, "-m", "pip", "install", "-q", "llama-cpp-python[server]", *extra])
    _pip_install(
        "torch>=2.4,<2.6",
        "transformers>=4.44,<5",
        "sentencepiece",
        "IndicTransToolkit",
        "fastapi>=0.115",
        "uvicorn[standard]>=0.32",
        "httpx>=0.27",
        "pydantic>=2.9",
        "huggingface_hub",
    )

    print("==> Pre-downloading models (parallel)")
    import concurrent.futures as cf
    from huggingface_hub import hf_hub_download, snapshot_download

    def _dl_gguf() -> str:
        return hf_hub_download(gguf_repo, gguf_file, token=os.environ["HF_TOKEN"])

    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(snapshot_download, "ai4bharat/indictrans2-en-indic-1B", token=os.environ["HF_TOKEN"])
        f2 = ex.submit(_dl_gguf)
        gguf_path = None
        for f, name in [(f1, "IndicTrans2-1B"), (f2, f"{gguf_repo}/{gguf_file}")]:
            try:
                r = f.result()
                if f is f2:
                    gguf_path = r
                print(f"   ✓ {name}  ({r})")
            except Exception as e:
                print(f"   ✗ {name} — {e}")
                if f is f2:
                    print("     Set BHASHAI_GGUF_FILE to a smaller quant from this repo:")
                    print(f"     https://huggingface.co/{gguf_repo}/tree/main")
                raise
    assert gguf_path

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

    print(f"==> Starting llama.cpp server on :8002 ({gguf_file})")
    llama_cmd = [
        sys.executable, "-m", "llama_cpp.server",
        "--model", gguf_path,
        "--host", "127.0.0.1", "--port", "8002",
        "--n_ctx", "8192",
        "--n_gpu_layers", "-1",       # offload all layers to GPU/Metal
        "--model_alias", served,
    ]
    if kind == "metal":
        llama_cmd += ["--n_batch", "256"]   # Metal: smaller batch keeps unified mem fits
    else:
        llama_cmd += ["--n_batch", "512"]
    vllm_proc = subprocess.Popen(llama_cmd, env={**os.environ})

    _wait_http("http://127.0.0.1:8001/health", "IndicTrans2", timeout=600)
    _wait_http("http://127.0.0.1:8002/v1/models", "llama.cpp (Sarvam-M)", timeout=900)

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
