"""IndicTrans2 (AI4Bharat) translation service.

Contract used by @bhashai/engines IndicTrans2Engine:
  POST /translate        {text, source, target}  -> {translation}
  POST /translate_batch  {texts, source, target} -> {translations}
  GET  /health

Model is lazy-loaded on first request. Default is the distilled 200M en->indic model
(CPU-practical); override with INDICTRANS_MODEL (e.g. ai4bharat/indictrans2-en-indic-1B on GPU).
"""
import os
import re
from typing import List

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

try:  # package was renamed across versions
    from IndicTransToolkit.processor import IndicProcessor
except Exception:  # pragma: no cover
    from IndicTransToolkit import IndicProcessor

from langs import to_flores

MODEL_NAME = os.environ.get("INDICTRANS_MODEL", "ai4bharat/indictrans2-en-indic-dist-200M")
MAX_LEN = int(os.environ.get("INDICTRANS_MAX_LEN", "256"))
BATCH = int(os.environ.get("INDICTRANS_BATCH", "16"))
# Greedy (1) is ~5x faster than 5-beam and IndicTrans2 quality stays strong; raise for max quality.
NUM_BEAMS = int(os.environ.get("INDICTRANS_NUM_BEAMS", "1"))
MAX_UNIT_CHARS = int(os.environ.get("INDICTRANS_MAX_UNIT_CHARS", "280"))
DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else ("mps" if torch.backends.mps.is_available() else "cpu")
)

_SENT_RE = re.compile(r"[^.?!।]*[.?!।]+|\S[^.?!।]*$")


def _split_units(text: str) -> List[str]:
    """Split text into sentence-sized units (<= MAX_UNIT_CHARS) so nothing is truncated."""
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_RE.findall(text) if p.strip()] or [text]
    units: List[str] = []
    cur = ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > MAX_UNIT_CHARS:
            units.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip() if cur else p
    if cur:
        units.append(cur)
    # hard-cap any unit with no sentence breaks
    capped: List[str] = []
    for u in units:
        if len(u) <= MAX_UNIT_CHARS * 2:
            capped.append(u)
        else:
            capped.extend(u[i : i + MAX_UNIT_CHARS] for i in range(0, len(u), MAX_UNIT_CHARS))
    return capped


class _Engine:
    def __init__(self) -> None:
        self.tok = None
        self.model = None
        self.ip = None

    def load(self) -> None:
        if self.model is not None:
            return
        self.tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        # fp16 on CUDA: ~2x faster + halves VRAM (1B fits a T4 easily). fp32 on CPU/MPS.
        dtype = torch.float16 if DEVICE == "cuda" else torch.float32
        self.model = (
            AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, trust_remote_code=True, torch_dtype=dtype)
            .to(DEVICE)
            .eval()
        )
        self.ip = IndicProcessor(inference=True)

    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        """Translate each input fully: long inputs are split into sentence units (avoids the
        256-token truncation that would drop content), translated in bounded sub-batches
        (keeps MPS/GPU memory in check), then reassembled per input."""
        self.load()
        src_f, tgt_f = to_flores(src), to_flores(tgt)

        units: List[str] = []
        spans = []  # (start, end) slice of units belonging to each input text
        for t in texts:
            sents = _split_units(t)
            spans.append((len(units), len(units) + len(sents)))
            units.extend(sents)

        translated: List[str] = []
        for i in range(0, len(units), BATCH):
            translated.extend(self._generate(units[i : i + BATCH], src_f, tgt_f))

        out = []
        for start, end in spans:
            out.append(" ".join(translated[start:end]).strip())
        return out

    def _generate(self, batch: List[str], src_f: str, tgt_f: str) -> List[str]:
        if not batch:
            return []
        pre = self.ip.preprocess_batch(batch, src_lang=src_f, tgt_lang=tgt_f)
        inputs = self.tok(
            pre,
            truncation=True,
            padding="longest",
            return_tensors="pt",
            return_attention_mask=True,
            max_length=MAX_LEN,
        ).to(DEVICE)
        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                use_cache=False,  # IndicTrans2 remote code uses legacy tuple cache; incompatible
                min_length=0,     # with transformers >=4.44 Cache. Disabling avoids the mismatch.
                max_length=MAX_LEN,
                num_beams=NUM_BEAMS,
                num_return_sequences=1,
            )
        decoded = self.tok.batch_decode(
            generated, skip_special_tokens=True, clean_up_tokenization_spaces=True
        )
        return self.ip.postprocess_batch(decoded, lang=tgt_f)


ENGINE = _Engine()
app = FastAPI(title="BhashAI IndicTrans2 service")


class TranslateReq(BaseModel):
    text: str
    source: str = "en"
    target: str


class TranslateBatchReq(BaseModel):
    texts: List[str]
    source: str = "en"
    target: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "device": DEVICE, "model": MODEL_NAME, "loaded": ENGINE.model is not None}


@app.post("/translate")
def translate(req: TranslateReq) -> dict:
    try:
        out = ENGINE.translate([req.text], req.source, req.target)
        return {"translation": out[0]}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/translate_batch")
def translate_batch(req: TranslateBatchReq) -> dict:
    try:
        return {"translations": ENGINE.translate(req.texts, req.source, req.target)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))
