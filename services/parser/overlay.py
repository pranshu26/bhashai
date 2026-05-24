"""Layout-preserved PDF translation: extract text blocks, remove only the text (keep images +
vector artwork), re-insert the translation in place with overflow-proof auto-fit.

Importable by the FastAPI app and the CLI script. Translation is delegated to the IndicTrans2
service over HTTP (/translate_batch)."""
import io
import json
import os
import urllib.request

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont  # HarfBuzz-shaped text rendering (raqm)

# macOS system fonts cover all 12 target scripts for local dev. On Linux/EC2, set FONT_DIR to a
# dir of Noto fonts (see deploy docs) or DEVANAGARI_FONT/<LANG>_FONT envs.
_MAC_FONT_DIR = "/System/Library/Fonts/Supplemental"
_LANG_FONT = {
    "hi": "Devanagari Sangam MN.ttc",
    "mr": "Devanagari Sangam MN.ttc",
    "bn": "Bangla Sangam MN.ttc",
    "as": "Bangla Sangam MN.ttc",
    "pa": "Gurmukhi Sangam MN.ttc",
    "gu": "Gujarati Sangam MN.ttc",
    "ta": "Tamil Sangam MN.ttc",
    "te": "Telugu Sangam MN.ttc",
    "kn": "Kannada Sangam MN.ttc",
    "or": "Oriya Sangam MN.ttc",
    "ml": "Malayalam Sangam MN.ttc",
    "ur": "GeezaPro.ttc",
}


def resolve_font(target: str) -> str:
    """Find a font file able to render `target`'s script."""
    env = os.environ.get(f"{target.upper()}_FONT") or os.environ.get("BHASHAI_FONT")
    if env and os.path.exists(env):
        return env
    font_dir = os.environ.get("FONT_DIR", _MAC_FONT_DIR)
    name = _LANG_FONT.get(target, "Devanagari Sangam MN.ttc")
    path = os.path.join(font_dir, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No font for '{target}' at {path}. Set FONT_DIR (Noto fonts) or {target.upper()}_FONT."
        )
    return path


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


def translate_via_service(texts, target, url):
    body = json.dumps({"texts": texts, "source": "en", "target": target}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/translate_batch", data=body, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=1200) as r:
        return json.loads(r.read())["translations"]


def extract_text_blocks(page):
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        spans = [s for line in b["lines"] for s in line["spans"]]
        text = " ".join(s["text"] for s in spans).strip()
        if not text:
            continue
        first = spans[0]
        blocks.append((fitz.Rect(b["bbox"]), text, first["size"], fitz.sRGB_to_pdf(first["color"])))
    return blocks


def place_text(page, rect, text, fs_start, fs_min, rgb, page_h):
    """Draw text guaranteeing visibility (insert_textbox is atomic). Shrink font, then grow the
    box downward until it fits. Returns (fontsize, grew)."""
    fs = fs_start
    while fs >= fs_min:
        box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
        if page.insert_textbox(box, text, fontname="tgt", fontsize=fs, color=rgb, align=0) >= 0:
            return fs, False
        fs -= 0.5
    y1 = rect.y1
    while y1 < page_h - 2:
        y1 = min(page_h - 2, y1 + max(14.0, rect.height * 0.5))
        box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, y1)
        if page.insert_textbox(box, text, fontname="tgt", fontsize=fs_min, color=rgb, align=0) >= 0:
            return fs_min, True
    box = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, page_h - 2)
    for fs2 in (fs_min, 3.5, 3.0):
        if page.insert_textbox(box, text, fontname="tgt", fontsize=fs2, color=rgb, align=0) >= 0:
            return fs2, True
    return fs_min, True


def _pil_font(font_path, size_px):
    try:
        return ImageFont.truetype(font_path, size_px, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        return ImageFont.truetype(font_path, size_px)


def _wrap_words(draw, words, font, max_w):
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_text_png(text, box_w_pt, box_h_pt, color_rgb, font_path, scale=3.0, max_fs_pt=None, min_fs_pt=5.0):
    """Render HarfBuzz/raqm-shaped text to a transparent PNG. Returns (png_bytes, height_pt, fits).
    PyMuPDF's text insertion does NOT shape Indic scripts (conjuncts/matras break); this does."""
    color = tuple(int(max(0.0, min(1.0, c)) * 255) for c in color_rgb)
    w_px = max(4, int(box_w_pt * scale))
    probe = ImageDraw.Draw(Image.new("RGBA", (w_px, 8)))
    words = text.split() or [text]
    fs = max(min_fs_pt, max_fs_pt or box_h_pt)
    best = None
    while fs >= min_fs_pt:
        font = _pil_font(font_path, max(6, int(fs * scale)))
        lines = _wrap_words(probe, words, font, w_px)
        asc, desc = font.getmetrics()
        lh = (asc + desc) * 1.2
        best = (font, lines, lh, lh * len(lines))
        if lh * len(lines) <= box_h_pt * scale:
            break
        fs -= 0.5
    font, lines, lh, total = best
    h_px = max(int(lh), int(total) + 2)
    img = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0.0
    for ln in lines:
        d.text((0, y), ln, font=font, fill=color + (255,))
        y += lh
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), h_px / scale, total <= box_h_pt * scale


def place_text_img(page, rect, text, color_rgb, font_path, size_hint_pt, page_h):
    """Draw correctly-shaped translated text as a transparent image overlay. Returns grew(bool)."""
    text = text.strip()
    if not text:
        return False
    box_w = rect.width + 2.0
    png, h_pt, fits = render_text_png(
        text, box_w, rect.height + 1.0, color_rgb, font_path, max_fs_pt=max(7.0, size_hint_pt)
    )
    y0 = rect.y0 - 1.0
    bottom = min(page_h - 2.0, y0 + h_pt)
    page.insert_image(
        fitz.Rect(rect.x0 - 1.0, y0, rect.x0 - 1.0 + box_w, bottom), stream=png, keep_proportion=False
    )
    return not fits


def analyze_pdf(in_path):
    """Per-page structure summary for the worker (chunk planning, progress, image-page flags)."""
    doc = fitz.open(in_path)
    pages = []
    text_pages = image_pages = total_blocks = 0
    for i, page in enumerate(doc):
        blocks = extract_text_blocks(page)
        text_chars = sum(len(t) for _, t, _, _ in blocks)
        imgs = len(page.get_images(full=True))
        is_text = len(blocks) > 0 and text_chars >= 40
        if is_text:
            text_pages += 1
        else:
            image_pages += 1
        total_blocks += len(blocks)
        pages.append(
            {"page": i + 1, "blocks": len(blocks), "textChars": text_chars, "images": imgs,
             "type": "TEXT" if is_text else "IMAGE"}
        )
    return {
        "pageCount": doc.page_count,
        "textPages": text_pages,
        "imagePages": image_pages,
        "totalBlocks": total_blocks,
        "pages": pages,
    }


def _luma(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _sample_bg(pix, rect, zoom):
    """Sample a background colour just above a text rect (pixmap pixel space) to cover with."""
    x = max(0, min(pix.width - 1, int((rect.x0 + rect.x1) / 2 * zoom)))
    y = max(0, min(pix.height - 1, int(rect.y0 * zoom) - max(2, int(rect.height * zoom * 0.4))))
    try:
        p = pix.pixel(x, y)
        return (p[0] / 255, p[1] / 255, p[2] / 255)
    except Exception:
        return (1, 1, 1)


def apply_postedit(sources, translations, target):
    """Refine drafts via the LLM post-edit layer; safe no-op fallback to drafts."""
    try:
        from llm_postedit import post_edit_batch

        return post_edit_batch(list(zip(sources, translations)), target)
    except Exception:
        return translations


def ocr_translate_page(page, target, service_url, font_path, min_conf=55, post_edit=False):
    """OCR text baked into an image page; translate high-confidence lines and overlay them.
    Low-confidence regions are left untouched and flagged (never silently wrong)."""
    import io
    import pytesseract
    from PIL import Image

    zoom = 200 / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    data = pytesseract.image_to_data(
        Image.open(io.BytesIO(pix.tobytes("png"))), output_type=pytesseract.Output.DICT
    )
    lines: dict = {}
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        try:
            conf = float(data["conf"][i])
        except ValueError:
            conf = -1.0
        if not txt or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        e = lines.setdefault(key, {"w": [], "c": [], "x0": 1e9, "y0": 1e9, "x1": 0.0, "y1": 0.0})
        e["w"].append(txt)
        e["c"].append(conf)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        e["x0"], e["y0"] = min(e["x0"], x), min(e["y0"], y)
        e["x1"], e["y1"] = max(e["x1"], x + w), max(e["y1"], y + h)

    stats = {"ocrLines": 0, "ocrTranslated": 0, "ocrLowConf": 0}
    todo = []
    for e in lines.values():
        text = " ".join(e["w"]).strip()
        if len(text) < 2 or not any(ch.isalpha() for ch in text):
            continue
        stats["ocrLines"] += 1
        if sum(e["c"]) / len(e["c"]) < min_conf:
            stats["ocrLowConf"] += 1
            continue
        todo.append((fitz.Rect(e["x0"] / zoom, e["y0"] / zoom, e["x1"] / zoom, e["y1"] / zoom), text))

    if not todo:
        return stats
    try:
        translations = translate_via_service([t for _, t in todo], target, service_url)
    except Exception:
        return stats
    if post_edit:
        translations = apply_postedit([t for _, t in todo], translations, target)
    page_h = page.rect.height
    for (rect, _src), tr in zip(todo, translations):
        bg = _sample_bg(pix, rect, zoom)
        page.draw_rect(rect, color=bg, fill=bg)
        tcol = (0, 0, 0) if _luma(bg) > 0.55 else (1, 1, 1)
        place_text_img(page, rect, tr, tcol, font_path, max(7.0, rect.height * 0.85), page_h)
        stats["ocrTranslated"] += 1
    return stats


def translate_pdf(in_path, out_path, target, service_url, pages_spec="", font_path=None, ocr=False, post_edit=False):
    """Translate a PDF in place (layout-preserved). Returns a report dict."""
    font_path = font_path or resolve_font(target)
    doc = fitz.open(in_path)
    pages = parse_pages(pages_spec, doc.page_count)
    report = {
        "sourcePages": doc.page_count,
        "pagesProcessed": len(pages),
        "blocksTranslated": 0,
        "overflowBlocks": 0,
        "imageTextPages": 0,
        "ocrPages": 0,
        "ocrLinesTranslated": 0,
        "ocrLowConf": 0,
        "failedPages": 0,
        "pages": [],
    }

    for pi in pages:
        page = doc[pi]
        blocks = extract_text_blocks(page)
        info = {"page": pi + 1, "blocks": len(blocks), "overflow": 0}
        if not blocks:
            report["imageTextPages"] += 1
            if ocr:
                st = ocr_translate_page(page, target, service_url, font_path, post_edit=post_edit)
                info["ocr"] = st
                report["ocrLinesTranslated"] += st["ocrTranslated"]
                report["ocrLowConf"] += st["ocrLowConf"]
                if st["ocrTranslated"] > 0:
                    report["ocrPages"] += 1
            else:
                info["note"] = "no text layer (image/graphic page) — artwork kept, flagged"
            report["pages"].append(info)
            continue

        src = [t for _, t, _, _ in blocks]
        translations, last_err = None, ""
        for _ in range(2):
            try:
                translations = translate_via_service(src, target, service_url)
                break
            except Exception as ex:  # noqa: BLE001
                last_err = str(ex)
        if translations is None:
            translations = src
            info["translateError"] = last_err[:200]
            report["failedPages"] += 1
        elif post_edit:
            translations = apply_postedit(src, translations, target)

        for rect, _t, _s, _c in blocks:
            page.add_redact_annot(rect)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE
        )
        page_h = page.rect.height
        for (rect, _t, size, rgb), translated in zip(blocks, translations):
            grew = place_text_img(page, rect, translated, rgb, font_path, max(7.0, size), page_h)
            if grew:
                info["overflow"] += 1
                report["overflowBlocks"] += 1
            report["blocksTranslated"] += 1
        report["pages"].append(info)

    out = fitz.open()
    for pi in pages:
        out.insert_pdf(doc, from_page=pi, to_page=pi)
    out.save(out_path, garbage=4, deflate=True)
    return report
