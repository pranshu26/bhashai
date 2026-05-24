"""IndicTrans2 (AI4Bharat) translation service.

Contract used by @bhashai/engines IndicTrans2Engine:
  POST /translate        {text, source, target}  -> {translation}
  POST /translate_batch  {texts, source, target} -> {translations}
  GET  /health

Model is lazy-loaded on first request. Default is the distilled 200M en->indic model
(CPU-practical); override with INDICTRANS_MODEL (e.g. ai4bharat/indictrans2-en-indic-1B on GPU).
"""
import os
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
DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else ("mps" if torch.backends.mps.is_available() else "cpu")
)


class _Engine:
    def __init__(self) -> None:
        self.tok = None
        self.model = None
        self.ip = None

    def load(self) -> None:
        if self.model is not None:
            return
        self.tok = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        self.model = (
            AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, trust_remote_code=True)
            .to(DEVICE)
            .eval()
        )
        self.ip = IndicProcessor(inference=True)

    def translate(self, texts: List[str], src: str, tgt: str) -> List[str]:
        self.load()
        src_f, tgt_f = to_flores(src), to_flores(tgt)
        batch = self.ip.preprocess_batch(texts, src_lang=src_f, tgt_lang=tgt_f)
        inputs = self.tok(
            batch,
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
                num_beams=5,
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
