"""Layout-preserved PDF translation overlay (proof on the real sample).

For each page: extract text blocks (paragraphs) with PyMuPDF, translate each block, remove
ONLY the original text (keep images + vector artwork), and re-insert the translation into the
same box with auto-fit font sizing. Image-baked text is untouched (and reported).

Usage:
  python translate_pdf_overlay.py --in IN.pdf --out OUT.pdf --target hi --font FONT.ttf \
      --pages 3,4,5 --engine service --service-url http://localhost:8001
  (--engine mock needs no model; emits Devanagari placeholder text to test overlay mechanics)
"""
import argparse
import json
import urllib.request

import fitz  # PyMuPDF


def parse_pages(spec: str, n: int):
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a) - 1, int(b)))
        else:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < n]


def translate_service(texts, target, url):
    body = json.dumps({"texts": texts, "source": "en", "target": target}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/translate_batch", data=body, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["translations"]


def translate_mock(texts, target):
    # Devanagari placeholder of similar length — exercises fitting/overflow without a model.
    word = "अनुवादित "
    return [(word * max(1, len(t) // 8)).strip() for t in texts]


def extract_text_blocks(page):
    """Return [(rect, text, fontsize, rgb)] for text blocks with non-empty content."""
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        spans = [s for line in b["lines"] for s in line["spans"]]
        text = " ".join(s["text"] for s in spans).strip()
        if not text:
            continue
        first = spans[0]
        rgb = fitz.sRGB_to_pdf(first["color"])
        blocks.append((fitz.Rect(b["bbox"]), text, first["size"], rgb))
    return blocks


def place_text(page, rect, text, fs_start, fs_min, rgb, page_h):
    """Draw `text` in `rect`, guaranteeing it is shown (insert_textbox is atomic — it draws
    nothing on overflow). Strategy: shrink font in the original box; if still no fit, grow the
    box downward at min font until it fits. Returns (fontsize, grew) where grew=True flags that
    the text spilled past its original box."""
    fs = fs_start
    while fs >= fs_min:
        box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
        if page.insert_textbox(box, text, fontname="deva", fontsize=fs, color=rgb, align=0) >= 0:
            return fs, False
        fs -= 0.5
    y1 = rect.y1
    while y1 < page_h - 2:
        y1 = min(page_h - 2, y1 + max(14.0, rect.height * 0.5))
        box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, y1)
        if page.insert_textbox(box, text, fontname="deva", fontsize=fs_min, color=rgb, align=0) >= 0:
            return fs_min, True
    box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, page_h - 2)
    for fs2 in (fs_min, 3.5, 3.0):
        if page.insert_textbox(box, text, fontname="deva", fontsize=fs2, color=rgb, align=0) >= 0:
            return fs2, True
    return fs_min, True


def overlay(in_pdf, out_pdf, target, font_path, pages_spec, engine, url):
    doc = fitz.open(in_pdf)
    pages = parse_pages(pages_spec, doc.page_count)
    report = {
        "pages": [],
        "blocks_translated": 0,
        "overflow_blocks": 0,
        "image_text_pages": 0,
        "failed_pages": 0,
    }

    for pi in pages:
        page = doc[pi]
        blocks = extract_text_blocks(page)
        page_info = {"page": pi + 1, "blocks": len(blocks), "overflow": 0}
        if not blocks:
            # likely image-baked text or a pure-graphic page
            report["image_text_pages"] += 1
            report["pages"].append({**page_info, "note": "no text layer (image/graphic page) — left as-is"})
            continue

        src_texts = [t for _, t, _, _ in blocks]
        if engine == "mock":
            translations = translate_mock(src_texts, target)
        else:
            translations, last_err = None, ""
            for _attempt in range(2):
                try:
                    translations = translate_service(src_texts, target, url)
                    break
                except Exception as ex:  # noqa: BLE001
                    last_err = str(ex)
            if translations is None:
                # don't abort the document: keep original text on this page and flag it
                translations = src_texts
                page_info["translate_error"] = last_err[:200]
                report["failed_pages"] += 1

        # 1) remove only the original text, keep images + vector art
        for rect, _, _, _ in blocks:
            page.add_redact_annot(rect)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_NONE,
        )

        # 2) embed the target-script font and re-insert translations with auto-fit
        page.insert_font(fontname="deva", fontfile=font_path)
        page_h = page.rect.height
        for (rect, _src, size, rgb), translated in zip(blocks, translations):
            _fs, grew = place_text(page, rect, translated, max(6.0, size), 4.0, rgb, page_h)
            if grew:
                page_info["overflow"] += 1
                report["overflow_blocks"] += 1
            report["blocks_translated"] += 1
        report["pages"].append(page_info)

    # save only the selected pages for a quick proof
    out = fitz.open()
    for pi in pages:
        out.insert_pdf(doc, from_page=pi, to_page=pi)
    out.save(out_pdf, garbage=4, deflate=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--target", default="hi")
    ap.add_argument("--font", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--engine", choices=["mock", "service"], default="service")
    ap.add_argument("--service-url", default="http://localhost:8001")
    a = ap.parse_args()
    overlay(a.inp, a.out, a.target, a.font, a.pages, a.engine, a.service_url)
