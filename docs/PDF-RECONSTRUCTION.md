# BhashAI — Document Parsing & PDF Reconstruction Strategy

> The honest engineering truth: perfect layout preservation of arbitrary translated PDFs is
> **not** generally solvable, because translated text changes length and line-breaking. We
> therefore classify the document, pick the highest-fidelity mode that is actually achievable,
> and **flag** every place fidelity degrades. We never pretend.

Companion: [ARCHITECTURE](./ARCHITECTURE.md) · [LIMITATIONS](./LIMITATIONS.md).

## 1. The normalized document model

All parsers (DOCX, PDF, OCR) emit one **normalized JSON tree** stored at
`processed/jobs/{jobId}/extracted/document.json`. Reconstruction reads only this tree, so every
input format converges on the same downstream pipeline.

```jsonc
{
  "docType": "PDF_TEXT",
  "pages": [{
    "number": 1, "width": 595, "height": 842,        // PDF points
    "blocks": [{
      "id": "p1b3", "type": "paragraph|heading|list|table|caption|figure|footnote|header|footer",
      "level": 2,                                     // heading level / list depth
      "bbox": [x, y, w, h],                           // null for DOCX (no coords)
      "text": "…", "translatedText": null,
      "font": { "family": "Times", "size": 11, "bold": false },
      "assetId": null,                                // links to DocumentAsset (image/table)
      "referenceLabel": "Figure 4",                   // if a caption/figure
      "order": 12                                     // reading order within page
    }]
  }],
  "outline": [{ "title": "Chapter 1", "level": 1, "blockId": "p1b0" }]
}
```

Translation fills `translatedText` per block; reconstruction walks the same tree. Images/tables
are `DocumentAsset` rows referenced by `assetId` — they are **moved, never re-generated**.

## 2. Document classification (first step of `document.extract`)

| Class (`DocType`) | Detection | Path |
| --- | --- | --- |
| `TXT` | extension/mime | plain split |
| `DOCX` | mime + zip/OOXML | python-docx structural parse |
| `PDF_TEXT` | PDF with extractable text layer on most pages | PyMuPDF/pdfplumber text+coords |
| `PDF_SCANNED` | PDF whose pages are mostly images, little/no text layer | OCR path |
| `PDF_MIXED` | some pages text, some scanned | per-page routing (text vs OCR) |

Detection heuristic: for each page, `chars = len(extractable_text)`, `imgArea/pageArea`. If
`chars < T_low` and `imgArea/pageArea > T_img` → scanned page. Job `docType` = aggregate.

## 3. Tooling (Python `services/parser`)

| Need | Primary | Fallback / notes |
| --- | --- | --- |
| PDF text + coords + fonts | **PyMuPDF (fitz)** | pdfplumber for tables |
| PDF tables | **pdfplumber** / Camelot | heuristic line detection |
| PDF images | PyMuPDF image extraction | bbox-cropped render |
| DOCX parse | **python-docx** | mammoth for HTML view |
| DOCX/PDF write | **python-docx** (DOCX) + **LibreOffice headless** (DOCX→PDF) | reportlab/WeasyPrint for reflowed PDF |
| OCR | **AWS Textract** (layout + tables) | **Tesseract** (open-source, `tesseract-ocr-{hin,…}`) when `ENABLE_OCR=local`; Google Vision optional |
| Layout-preserved PDF | PyMuPDF redaction-overlay (replace text spans in place) | — |

`ENABLE_OCR` and the OCR provider are config-gated. Textract gives best layout/tables but costs
money; Tesseract is the zero-cost default for dev.

## 4. Per-type handling

### 4.1 DOCX (best fidelity — fully structural)
DOCX is XML; we keep the document model and only swap text runs.
- Preserve heading hierarchy, paragraphs, lists, tables (cell-by-cell), images, captions,
  footnotes/endnotes (where python-docx exposes them), and basic run styling (bold/italic/size).
- Translate **paragraph/cell/caption** text blocks; keep images and drawing objects untouched.
- Rebuild a translated `.docx` from the same template, then optionally export PDF via
  LibreOffice headless. This is the **highest-quality** path and the Phase 1 target.

### 4.2 Text-based PDF
- Extract text blocks with page number, bbox, font metadata; extract images separately as assets.
- Preserve page order and figure/table reference labels.
- Translate text blocks. Then choose reconstruction mode (§5). Default **REFLOWED** because
  translated text rarely fits the original boxes; **LAYOUT_PRESERVED** offered as best-effort.

### 4.3 Scanned PDF (OCR)
- OCR each page → text + bounding boxes + confidence (stored on `DocumentAsset.ocrConfidence`).
- Extract layout blocks (Textract) or line/paragraph grouping (Tesseract).
- Translate OCR text; **keep original page images** as the visual backdrop.
- Reconstruct as REFLOWED (recommended) or LAYOUT_PRESERVED overlay (text drawn over/near
  original positions). Low-confidence OCR regions are flagged, not silently trusted.
- We explicitly **do not** claim perfect layout for complex scanned documents.

### 4.4 Graph/image/diagram-heavy PDFs
- **Do not** translate text baked into images unless OCR confidence is high; otherwise keep the
  image as-is and **flag** it (`imageTextWarnings`).
- Preserve graph/image placement; translate **captions** and **surrounding references**.
- Maintain "Figure 1 / Table 2 / Graph 3" numbering and cross-references ("as shown in Figure 4").
- If figure-internal text translation isn't reliable, the QA report says so per asset.

## 5. The three output modes

| Mode (`OutputMode`) | What it is | Best for | Fidelity |
| --- | --- | --- | --- |
| **REFLOWED** | Clean structured translated DOCX/PDF rebuilt from the doc tree; text reflows naturally. | Readability; theses, reports, most jobs. | Structure ✔, exact pixel layout ✘ |
| **LAYOUT_PRESERVED** | Best-effort: keep page count, images, tables, approximate block positions; overlay translated text into original regions. | Forms, certificates, short official docs. | Approximate; degrades as text-length changes |
| **BILINGUAL** | Source and translation aligned per paragraph/chunk (two columns or interleaved). | Human review, verification, legal cross-check. | Structure ✔, no layout claim |

The job records which mode was used and the UI shows the mode + its limitations banner. Users can
re-export a completed job in another mode without re-translating (reconstruction reads the cached
doc tree + translations).

### Why not "always layout-preserved"?
Translated Indian-language text differs in length and line-breaking from English. Forcing it into
original bounding boxes causes overflow/clipping/overlap. LAYOUT_PRESERVED uses auto-fit (shrink
to fit, then spill with a flag) and is honest that it's approximate. REFLOWED is the default
because it reliably yields a professional, readable document.

## 6. Reconstruction algorithm (per mode)

```
REFLOWED:        walk outline → emit headings/paragraphs/lists/tables/captions in order,
                 insert image assets at their anchor blocks, render DOCX (python-docx) or
                 reflowed PDF (WeasyPrint from generated HTML). Honors RTL for Urdu.
LAYOUT_PRESERVED:for each page, clone original page; for each text block, redact original span
                 and draw translatedText in the same bbox with auto-fit; keep images/tables.
                 Overflow → shrink font to MIN, then allow spill + add layoutWarning.
BILINGUAL:       for each chunk, emit [source][translation] pair (2-col table in DOCX, or
                 side-by-side HTML→PDF). Tables/images shown once with bilingual caption.
```

## 7. Tables, footnotes, citations, RTL

- **Tables:** preserved as table structures (not flattened text). Each cell is a translatable
  block; QA asserts row×col count is unchanged (`table_mismatch`).
- **Footnotes/endnotes:** translated and re-attached where the format exposes them (DOCX yes;
  PDF best-effort as same-page blocks).
- **Citations/references:** markers preserved verbatim by prompt rule + QA check.
- **RTL:** Urdu output sets text direction RTL in DOCX/HTML; the renderer mirrors layout.

## 8. Large-file discipline

- Parse **page-by-page / section-by-section**, streaming blocks into the doc tree on disk; never
  load a 100MB PDF fully into Node memory.
- Heavy parsing/OCR/render runs in `services/parser` (Python) so Node workers stay responsive.
- Reconstruction streams pages; assets are referenced by S3 key, not embedded until render.

## 9. Limitation honesty (summary — full list in LIMITATIONS.md)

- Complex multi-column scanned PDFs: reading order may be imperfect → REFLOWED + flag.
- Text inside figures/charts: not repainted unless high-confidence OCR → flagged.
- Exotic fonts/ligatures in LAYOUT_PRESERVED: may shift → auto-fit + flag.
- Equations: preserved as images/blocks; not re-typeset.
