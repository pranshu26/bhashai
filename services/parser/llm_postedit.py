"""LLM post-edit: refine IndicTrans2 drafts into fluent, correct target-language text.

Reads LLM_PROVIDER / ANTHROPIC_API_KEY / OPENAI_API_KEY / LLM_MODEL from env. Batches lines,
asks the LLM for a same-length JSON array, and falls back to the draft on any error or
mismatch (never drops or corrupts content)."""
import json
import os
import urllib.request

_LANG_NAMES = {
    "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati",
    "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "or": "Odia", "ur": "Urdu",
    "as": "Assamese", "ml": "Malayalam",
}


def _provider_cfg():
    prov = os.environ.get("LLM_PROVIDER", "").lower()
    a = os.environ.get("ANTHROPIC_API_KEY")
    o = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("LLM_MODEL") or None
    if prov == "anthropic" and a:
        return ("anthropic", a, model or "claude-sonnet-4-6")
    if prov == "openai" and o:
        return ("openai", o, model or "gpt-4o")
    if a:
        return ("anthropic", a, model or "claude-sonnet-4-6")
    if o:
        return ("openai", o, model or "gpt-4o")
    return (None, None, None)


def is_enabled() -> bool:
    return _provider_cfg()[0] is not None


def _call_llm(system: str, user: str, provider: str, key: str, model: str) -> str:
    if provider == "anthropic":
        body = json.dumps({
            "model": model, "max_tokens": 4096, "temperature": 0.2,
            "system": system, "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
            return "".join(c.get("text", "") for c in d["content"] if c.get("type") == "text")
    body = json.dumps({
        "model": model, "max_tokens": 4096, "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"authorization": f"Bearer {key}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
        return d["choices"][0]["message"]["content"]


def post_edit_batch(pairs, target_code, batch_size=10):
    """pairs: list of (source_en, draft). Returns refined list (same order). Falls back to drafts."""
    prov, key, model = _provider_cfg()
    drafts = [d for _, d in pairs]
    if prov is None or not pairs:
        return drafts
    lang = _LANG_NAMES.get(target_code, target_code)
    system = (
        f"You are a senior {lang} editor. You receive English source lines and their draft {lang} "
        f"translations. Rewrite each draft so it is fluent, natural, and correct {lang}, preserving "
        f"the exact meaning, numbers, names, citations, and any English terms/acronyms. Do not add or "
        f"drop content. Return ONLY a JSON array of strings — the refined {lang} translations, same "
        f"order and same count. No prose, no markdown."
    )
    out = []
    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i : i + batch_size]
        items = [{"n": j + 1, "source": s, "draft": d} for j, (s, d) in enumerate(chunk)]
        user = f"Refine these. Return a JSON array of exactly {len(chunk)} strings.\n" + json.dumps(items, ensure_ascii=False)
        try:
            raw = _call_llm(system, user, prov, key, model).strip()
            start, end = raw.find("["), raw.rfind("]")
            arr = json.loads(raw[start : end + 1]) if start >= 0 and end > start else None
            if isinstance(arr, list) and len(arr) == len(chunk):
                out.extend(str(x) for x in arr)
            else:
                out.extend(d for _, d in chunk)
        except Exception:
            out.extend(d for _, d in chunk)
    return out
