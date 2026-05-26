"""LLM post-edit: refine the draft translation into fluent, teacher-grade target-language text.

Default backend is an OpenAI-compatible chat endpoint set via LLM_BASE_URL + LLM_API_KEY + LLM_MODEL
(e.g. Groq's free Llama-3.3-70B: https://api.groq.com/openai/v1). Falls back to Anthropic/OpenAI by
key. The refine pass enforces terminology consistency + meaning fidelity (it fixed inconsistent
terms, reversed examples, and meaning drift that the raw MT draft produced). Chunks run
concurrently; on any error/shape-mismatch it falls back to the draft (never drops content)."""
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_UA = "bhashai/1.0 (+translation-service)"  # some hosts (Groq/Cloudflare) 403 the default urllib UA

_LANG_NAMES = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "or": "Odia", "ur": "Urdu",
    "as": "Assamese", "ml": "Malayalam",
}


def _provider_cfg():
    """Returns (kind, key, model, base_url). kind is 'openai' (OpenAI-compatible — Groq/vLLM/OpenAI)
    or 'anthropic'. Prefers the configured OpenAI-compatible endpoint when LLM_BASE_URL is set."""
    base = os.environ.get("LLM_BASE_URL")  # e.g. https://api.groq.com/openai/v1
    model = os.environ.get("LLM_MODEL") or None
    a = os.environ.get("ANTHROPIC_API_KEY")
    o = os.environ.get("OPENAI_API_KEY")
    prov = os.environ.get("LLM_PROVIDER", "").lower()

    if base and prov != "anthropic":  # Groq / any OpenAI-compatible endpoint
        return ("openai", os.environ.get("LLM_API_KEY", "EMPTY"), model or "llama-3.3-70b-versatile", base.rstrip("/"))
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


def _http_json(url, body, headers, timeout):
    """POST JSON with retry/backoff on rate-limit (429) / 5xx. Adds a real User-Agent."""
    headers = {**headers, "user-agent": _UA}
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(min(20.0, 1.5 * (2 ** attempt)) + random.random())
                continue
            raise
        except Exception:  # noqa: BLE001 -- transient network
            if attempt < 4:
                time.sleep(1.0 + random.random())
                continue
            raise
    raise RuntimeError("unreachable")


def warmup() -> None:
    """Best-effort: spin up a scale-to-zero self-hosted endpoint so its cold start overlaps the NMT
    phase. No-op for hosted APIs (Groq etc., always warm) or when disabled."""
    kind, key, model, base_url = _provider_cfg()
    if kind != "openai" or not base_url or not any(h in base_url for h in ("modal.run", "localhost", "127.0.0.1")):
        return
    try:
        payload = {"model": model, "max_tokens": 1, "temperature": 0,
                   "messages": [{"role": "user", "content": "ok"}],
                   "chat_template_kwargs": {"enable_thinking": False}}
        _http_json(base_url.rstrip("/") + "/chat/completions", json.dumps(payload).encode(),
                   {"authorization": f"Bearer {key}", "content-type": "application/json"}, timeout=900)
    except Exception:  # noqa: BLE001
        pass


def _call_llm(system: str, user: str, kind: str, key: str, model: str, base_url: str, max_tokens: int = 4096) -> str:
    if kind == "anthropic":
        body = json.dumps({
            "model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "system": system, "messages": [{"role": "user", "content": user}],
        }).encode()
        d = _http_json("https://api.anthropic.com/v1/messages", body,
                       {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, 120)
        return "".join(c.get("text", "") for c in d["content"] if c.get("type") == "text")

    # OpenAI-compatible: Groq / OpenAI / self-hosted vLLM.
    payload = {
        "model": model, "max_tokens": max_tokens, "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if any(h in base_url for h in ("modal.run", "localhost", "127.0.0.1")):
        payload["chat_template_kwargs"] = {"enable_thinking": False}  # self-hosted vLLM thinking off
    elif "api.sarvam.ai" in base_url:
        payload["reasoning_effort"] = "low"
    d = _http_json(base_url.rstrip("/") + "/chat/completions", json.dumps(payload).encode(),
                   {"authorization": f"Bearer {key}", "content-type": "application/json"}, 180)
    return d["choices"][0]["message"].get("content") or ""


def _refine_system(lang, target_code):
    rules = (
        "- Keep terminology, acronyms, and proper nouns CONSISTENT throughout: pick ONE rendering for "
        "each term and reuse it everywhere (never vary, e.g. don't mix forms of 'AI').\n"
        "- Preserve the EXACT meaning, especially examples, comparisons, numbers, dates, URLs and "
        "symbols — never reorder, swap, or invert them.\n"
        "- Translate any English still left in the draft, except URLs, proper nouns, and "
        "fill-in-the-blank markers (lines of underscores)."
    )
    glossary = os.environ.get("TRANSLATION_GLOSSARY", "")
    if not glossary and target_code == "hi":
        glossary = "AI=एआई; prompt=प्रॉम्प्ट; internet=इंटरनेट; website=वेबसाइट; search engine=सर्च इंजन; email=ईमेल; password=पासवर्ड; online=ऑनलाइन; computer=कंप्यूटर"
    gloss = f"\n- Prefer these {lang} renderings for key terms: {glossary}" if glossary else ""
    return (
        f"You are a senior {lang} editor for school/teacher educational materials. You receive English "
        f"source lines and their draft {lang} translations. Rewrite each draft into fluent, natural, "
        f"correct {lang} a teacher can use directly.\n{rules}{gloss}\n"
        f"Return ONLY a JSON array of strings — the refined {lang} translations, same order and same "
        f"count. No prose, no markdown."
    )


def _refine_chunk(chunk, system, kind, key, model, base_url):
    items = [{"n": j + 1, "source": s, "draft": d} for j, (s, d) in enumerate(chunk)]
    user = f"Refine these. Return a JSON array of exactly {len(chunk)} strings.\n" + json.dumps(items, ensure_ascii=False)
    try:
        raw = _call_llm(system, user, kind, key, model, base_url).strip()
        start, end = raw.find("["), raw.rfind("]")
        arr = json.loads(raw[start : end + 1]) if start >= 0 and end > start else None
        if isinstance(arr, list) and len(arr) == len(chunk):
            return [str(x) for x in arr]
    except Exception:  # noqa: BLE001
        pass
    return [d for _, d in chunk]  # fall back to the draft (never drop content)


def post_edit_batch(pairs, target_code, batch_size=12, max_workers=None):
    """pairs: list of (source_en, draft). Returns refined list (same order). Chunks are refined
    concurrently; bigger batches keep the doc consistent and cut call count."""
    kind, key, model, base_url = _provider_cfg()
    if kind is None or not pairs:
        return [d for _, d in pairs]
    if max_workers is None:
        max_workers = int(os.environ.get("POST_EDIT_CONCURRENCY", "6"))
    batch_size = int(os.environ.get("POST_EDIT_BATCH", batch_size))
    system = _refine_system(_LANG_NAMES.get(target_code, target_code), target_code)
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


def translate_batch(texts, target_code, batch_size=6, max_workers=None):
    """Translate English `texts` -> target language directly via the chat LLM. Returns
    (translations, failed_index_set, last_err). On a batch count-mismatch it retries each item
    individually so paragraphs never silently fall back to English."""
    kind, key, model, base_url = _provider_cfg()
    if kind is None or not texts:
        return list(texts), (set(range(len(texts))) if texts else set()), None
    if max_workers is None:
        max_workers = int(os.environ.get("POST_EDIT_CONCURRENCY", "6"))
    lang = _LANG_NAMES.get(target_code, target_code)
    glossary = os.environ.get("TRANSLATION_GLOSSARY", "")
    if not glossary and target_code == "hi":
        glossary = "AI=एआई; prompt=प्रॉम्प्ट; internet=इंटरनेट; website=वेबसाइट; search engine=सर्च इंजन; email=ईमेल; password=पासवर्ड; online=ऑनलाइन; computer=कंप्यूटर"
    gloss = f"\n- Prefer these {lang} renderings for key terms: {glossary}" if glossary else ""
    system = (
        f"You are an expert English->{lang} translator for school/teacher educational materials. "
        f"Translate each line into fluent, natural {lang} a teacher can use directly.\n"
        f"- Translate EVERYTHING; leave NO English except URLs, email addresses, proper nouns, and "
        f"fill-in-the-blank markers (runs of underscores).\n"
        f"- Keep terminology, acronyms, and proper nouns CONSISTENT throughout (one rendering each).\n"
        f"- Preserve the exact meaning, examples, comparisons, numbers, dates, URLs and symbols.{gloss}\n"
        f"Return ONLY a JSON array of strings — the {lang} translations, same order and same count. "
        f"No prose, no markdown."
    )
    batch_size = int(os.environ.get("TRANSLATE_BATCH", batch_size))
    chunks = [(i, texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
    last_err = {"v": None}

    def _try_chunk(chunk):
        """Returns a list of len(chunk) translations, or None on error/count-mismatch."""
        items = [{"n": j + 1, "text": t} for j, t in enumerate(chunk)]
        user = (
            f"Translate these {len(chunk)} lines to {lang}. Return a JSON array of EXACTLY "
            f"{len(chunk)} strings — one per input item, same order. Do NOT merge, split, add or "
            f"omit items.\n" + json.dumps(items, ensure_ascii=False)
        )
        try:
            raw = _call_llm(system, user, kind, key, model, base_url, max_tokens=8000).strip()
            s, e = raw.find("["), raw.rfind("]")
            arr = json.loads(raw[s : e + 1]) if s >= 0 and e > s else None
            if isinstance(arr, list) and len(arr) == len(chunk):
                return [str(x) for x in arr]
        except Exception as ex:  # noqa: BLE001
            last_err["v"] = str(ex)
        return None

    def _do(item):
        start, chunk = item
        got = _try_chunk(chunk)
        if got is not None:
            return (start, got, [True] * len(chunk))
        if len(chunk) == 1:
            return (start, [chunk[0]], [False])  # single item failed -> keep source
        # batch count-mismatch/error -> translate each item ALONE (guarantees completeness)
        vals, oks = [], []
        for c in chunk:
            one = _try_chunk([c])
            if one is not None:
                vals.append(one[0]); oks.append(True)
            else:
                vals.append(c); oks.append(False)
        return (start, vals, oks)

    if len(chunks) <= 1:
        results = [_do(chunks[0])] if chunks else []
    else:
        workers = max(1, min(max_workers, len(chunks)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, chunks))

    out = list(texts)
    failed: set = set()
    for start, vals, oks in results:
        for k, (v, ok) in enumerate(zip(vals, oks)):
            out[start + k] = v
            if not ok:
                failed.add(start + k)
    return out, failed, last_err["v"]
