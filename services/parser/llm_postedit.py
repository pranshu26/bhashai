"""LLM post-edit: refine IndicTrans2 drafts into fluent, correct target-language text.

Default backend is a self-hosted Sarvam-M (24B, Indic-specialised) served OpenAI-compatibly on
Modal (set LLM_BASE_URL=https://...modal.run/v1, LLM_MODEL=sarvam-m). Falls back to Anthropic /
OpenAI if their keys are set instead. Chunks are refined CONCURRENTLY; on any error or shape
mismatch it falls back to the draft (never drops or corrupts content)."""
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_LANG_NAMES = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "or": "Odia", "ur": "Urdu",
    "as": "Assamese", "ml": "Malayalam",
}


def _provider_cfg():
    """Returns (kind, key, model, base_url). kind is 'openai' (OpenAI-compatible — incl. self-hosted
    vLLM/Sarvam-M) or 'anthropic'. Prefers the self-hosted endpoint when LLM_BASE_URL is set."""
    base = os.environ.get("LLM_BASE_URL")  # e.g. https://<you>--bhashai-sarvam-serve.modal.run/v1
    model = os.environ.get("LLM_MODEL") or None
    a = os.environ.get("ANTHROPIC_API_KEY")
    o = os.environ.get("OPENAI_API_KEY")
    prov = os.environ.get("LLM_PROVIDER", "").lower()

    if base and prov != "anthropic":  # self-hosted Sarvam-M / any OpenAI-compatible endpoint
        return ("openai", os.environ.get("LLM_API_KEY", "EMPTY"), model or "sarvam-m", base.rstrip("/"))
    if prov == "anthropic" and a:
        return ("anthropic", a, model or "claude-sonnet-4-6", None)
    if prov == "openai" and o:
        return ("openai", o, model or "gpt-4o", "https://api.openai.com/v1")
    if a:
        return ("anthropic", a, model or "claude-sonnet-4-6", None)
    if o:
        return ("openai", o, model or "gpt-4o", "https://api.openai.com/v1")
    return (None, None, None, None)


def is_enabled() -> bool:
    return _provider_cfg()[0] is not None


def warmup() -> None:
    """Best-effort: fire a 1-token request to spin up a scale-to-zero endpoint so its cold start
    overlaps with the (concurrent) NMT phase. No-op for hosted APIs or when disabled. Call this in
    a daemon thread at the start of a translation."""
    kind, key, model, base_url = _provider_cfg()
    if kind != "openai" or not base_url or not any(h in base_url for h in ("modal.run", "localhost", "127.0.0.1")):
        return  # only a self-hosted (scale-to-zero) endpoint benefits; hosted APIs are always warm
    try:
        payload = {
            "model": model, "max_tokens": 1, "temperature": 0,
            "messages": [{"role": "user", "content": "ok"}],
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=900).read()  # wait out the cold start
    except Exception:
        pass


def _call_llm(system: str, user: str, kind: str, key: str, model: str, base_url: str, max_tokens: int = 4096) -> str:
    if kind == "anthropic":
        body = json.dumps({
            "model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "system": system, "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
            return "".join(c.get("text", "") for c in d["content"] if c.get("type") == "text")

    # OpenAI-compatible: real OpenAI or self-hosted vLLM (Sarvam-M).
    payload = {
        "model": model, "max_tokens": max_tokens, "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if any(h in base_url for h in ("modal.run", "localhost", "127.0.0.1")):
        # Self-hosted vLLM: disable the hybrid "thinking" mode so it returns the JSON array directly.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    elif "api.sarvam.ai" in base_url:
        # Sarvam keeps reasoning in a separate field (content stays clean). Use the minimum reasoning
        # effort: faster + cheaper + leaves room under the tier's max_tokens cap. ('none' is rejected.)
        payload["reasoning_effort"] = "low"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
        headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]


def _refine_chunk(chunk, system, kind, key, model, base_url):
    items = [{"n": j + 1, "source": s, "draft": d} for j, (s, d) in enumerate(chunk)]
    user = f"Refine these. Return a JSON array of exactly {len(chunk)} strings.\n" + json.dumps(items, ensure_ascii=False)
    try:
        raw = _call_llm(system, user, kind, key, model, base_url).strip()
        start, end = raw.find("["), raw.rfind("]")
        arr = json.loads(raw[start : end + 1]) if start >= 0 and end > start else None
        if isinstance(arr, list) and len(arr) == len(chunk):
            return [str(x) for x in arr]
    except Exception:
        pass
    return [d for _, d in chunk]  # fall back to the draft (never drop content)


def post_edit_batch(pairs, target_code, batch_size=10, max_workers=None):
    """pairs: list of (source_en, draft). Returns refined list (same order). Chunks are refined
    concurrently (each chunk = one LLM call) so wall-clock stays low on large documents."""
    kind, key, model, base_url = _provider_cfg()
    if kind is None or not pairs:
        return [d for _, d in pairs]
    if max_workers is None:
        max_workers = int(os.environ.get("POST_EDIT_CONCURRENCY", "8"))
    lang = _LANG_NAMES.get(target_code, target_code)
    system = (
        f"You are a senior {lang} editor. You receive English source lines and their draft {lang} "
        f"translations. Rewrite each draft so it is fluent, natural, and correct {lang}, preserving "
        f"the exact meaning, numbers, names, citations, and any English terms/acronyms. Do not add or "
        f"drop content. Return ONLY a JSON array of strings — the refined {lang} translations, same "
        f"order and same count. No prose, no markdown."
    )
    chunks = [pairs[i : i + batch_size] for i in range(0, len(pairs), batch_size)]
    if len(chunks) <= 1:
        return _refine_chunk(chunks[0], system, kind, key, model, base_url) if chunks else []
    workers = max(1, min(max_workers, len(chunks)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda c: _refine_chunk(c, system, kind, key, model, base_url), chunks))
    out: list = []
    for r in results:
        out.extend(r)
    return out


def translate_batch(texts, target_code, batch_size=8, max_workers=None):
    """Translate English `texts` -> target language directly via the chat LLM (Sarvam). Returns
    (translations, failed_index_set, last_err) — same shape as overlay._batch_translate so the PDF
    pipeline can swap engines transparently. Chunks run concurrently; the LLM produces fluent output
    in one pass, so no separate post-edit is needed. Falls back to source text on error/mismatch."""
    kind, key, model, base_url = _provider_cfg()
    if kind is None or not texts:
        return list(texts), (set(range(len(texts))) if texts else set()), None
    if max_workers is None:
        max_workers = int(os.environ.get("POST_EDIT_CONCURRENCY", "8"))
    lang = _LANG_NAMES.get(target_code, target_code)
    system = (
        f"You are an expert English->{lang} translator for official and educational documents. "
        f"Translate each English line into fluent, natural, accurate {lang}, preserving the exact "
        f"meaning, numbers, names, dates, citations, and any English terms/acronyms that are "
        f"conventionally kept. Do not add, drop, or explain anything. Return ONLY a JSON array of "
        f"strings — the {lang} translations, in the same order and same count. No prose, no markdown."
    )
    chunks = [(i, texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
    last_err = {"v": None}

    def _do(item):
        start, chunk = item
        items = [{"n": j + 1, "text": t} for j, t in enumerate(chunk)]
        user = (
            f"Translate these {len(chunk)} lines to {lang}. Return a JSON array of exactly "
            f"{len(chunk)} strings.\n" + json.dumps(items, ensure_ascii=False)
        )
        try:
            raw = _call_llm(system, user, kind, key, model, base_url, max_tokens=4096).strip()
            s, e = raw.find("["), raw.rfind("]")
            arr = json.loads(raw[s : e + 1]) if s >= 0 and e > s else None
            if isinstance(arr, list) and len(arr) == len(chunk):
                return (start, [str(x) for x in arr], True)
        except Exception as ex:  # noqa: BLE001
            last_err["v"] = str(ex)
        return (start, list(chunk), False)  # fall back to source for this chunk

    if len(chunks) <= 1:
        results = [_do(chunks[0])] if chunks else []
    else:
        workers = max(1, min(max_workers, len(chunks)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, chunks))

    out = list(texts)
    failed: set = set()
    for start, vals, ok in results:
        for k, v in enumerate(vals):
            out[start + k] = v
        if not ok:
            failed.update(range(start, start + len(vals)))
    return out, failed, last_err["v"]
