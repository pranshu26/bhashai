# Sample documents

Real-world artifacts for end-to-end testing. Large binaries are git-ignored (kept locally);
this manifest is committed so the characterization is preserved.

## digital-saathi-teacher-guide-2025-26.pdf

- **Source:** "Digital Saathi Teacher Guide 2025-26" (Slam Out Loud × Girl Rising). Original
  filename: `Copy - ENG_Digital Saathi_Teacher Guide_2025-26 (1).pdf`.
- **Local path:** `samples/digital-saathi-teacher-guide-2025-26.pdf` (36 MB, git-ignored).
- **Produced by:** Canva (PDF 1.4). Title metadata: "SOL X GR Digital Literacy ENG".

### Characterization (via `services/parser/scripts/inspect_pdf.py`)
| Property | Value |
| --- | --- |
| Pages | 74 (A4, 595.5 × 842.25 pt) |
| Extractable text | ~64,878 chars (a real text layer — **no OCR needed** for text pages) |
| Embedded images | 162 |
| Page mix | 50 TEXT · 22 IMAGE/GRAPHIC-dominant · 2 MIXED |

### What this means for translation
- **Text pages translate directly** from the text layer (IndicTrans2 / LLM), no OCR.
- **Best output mode = LAYOUT_PRESERVED overlay**: keep the Canva artwork as-is and replace the
  English text spans in place with the translated text (PyMuPDF redact + insert). This preserves
  the visual design — the right call for a designed guide like this.
  - Risk: Indic text is usually longer than English → auto-fit / shrink, then flag overflow.
- **Image-baked text** (on the ~22 graphic pages) is **not** in the text layer. It will be either
  OCR'd (Phase 2, if confidence is high) or **flagged** (`image_text_warning`) — never silently
  dropped. The original artwork is preserved regardless.
- **Fallback = REFLOWED**: a clean translated document (text + referenced images) if overlay
  fidelity is poor on a given page.
