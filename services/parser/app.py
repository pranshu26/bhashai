"""BhashAI parser-service (FastAPI). Wraps PDF/DOCX extraction + layout-preserved translation.

Contract used by apps/worker:
  GET  /health
  POST /analyze       {in_path}                               -> structure summary
  POST /translate-pdf {in_path, out_path, target, pages?}     -> translation report

Path-based (worker + service share a filesystem on the single box). INDICTRANS_SERVICE_URL is
read from env. Heavy CPU work stays in this Python process so the Node worker stays responsive.
"""
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import overlay
import llm_postedit

INDICTRANS_URL = os.environ.get("INDICTRANS_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BhashAI parser-service")


class AnalyzeReq(BaseModel):
    in_path: str


class TranslatePdfReq(BaseModel):
    in_path: str
    out_path: str
    target: str
    pages: str = ""
    ocr: bool | None = None  # None => use ENABLE_OCR env default
    post_edit: bool | None = None  # None => on when an LLM key is configured
    engine: str | None = None  # None => TRANSLATE_ENGINE env (llm | indictrans)


ENABLE_OCR = os.environ.get("ENABLE_OCR", "false").lower() in ("local", "tesseract", "true", "textract")
TRANSLATE_ENGINE = os.environ.get("TRANSLATE_ENGINE", "llm")  # llm = hosted Sarvam (no GPU); indictrans = Modal NMT


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indictrans": INDICTRANS_URL}


@app.post("/analyze")
def analyze(req: AnalyzeReq) -> dict:
    if not os.path.exists(req.in_path):
        raise HTTPException(404, f"not found: {req.in_path}")
    try:
        return overlay.analyze_pdf(req.in_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))


@app.post("/translate-pdf")
def translate_pdf(req: TranslatePdfReq) -> dict:
    if not os.path.exists(req.in_path):
        raise HTTPException(404, f"not found: {req.in_path}")
    os.makedirs(os.path.dirname(req.out_path) or ".", exist_ok=True)
    ocr = ENABLE_OCR if req.ocr is None else req.ocr
    post_edit = llm_postedit.is_enabled() if req.post_edit is None else req.post_edit
    engine = TRANSLATE_ENGINE if req.engine is None else req.engine
    try:
        return overlay.translate_pdf(
            req.in_path, req.out_path, req.target, INDICTRANS_URL, req.pages,
            ocr=ocr, post_edit=post_edit, engine=engine,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))
