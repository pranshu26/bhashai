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

INDICTRANS_URL = os.environ.get("INDICTRANS_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BhashAI parser-service")


class AnalyzeReq(BaseModel):
    in_path: str


class TranslatePdfReq(BaseModel):
    in_path: str
    out_path: str
    target: str
    pages: str = ""


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
    try:
        return overlay.translate_pdf(req.in_path, req.out_path, req.target, INDICTRANS_URL, req.pages)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))
