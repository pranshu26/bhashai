"""Characterize a PDF: per-page text vs image content, to choose extract path."""
import sys
import fitz  # PyMuPDF


def classify(text_len: int, img_area_ratio: float) -> str:
    if text_len >= 200:
        return "TEXT"
    if img_area_ratio > 0.5 and text_len < 100:
        return "SCANNED/IMAGE"
    if text_len < 50:
        return "SCANNED/IMAGE"
    return "MIXED"


def main(path: str) -> None:
    doc = fitz.open(path)
    n = doc.page_count
    print(f"pages={n}  size={doc.metadata}")
    counts = {"TEXT": 0, "SCANNED/IMAGE": 0, "MIXED": 0}
    total_text = 0
    total_imgs = 0
    for i, page in enumerate(doc):
        text = page.get_text("text")
        total_text += len(text)
        imgs = page.get_images(full=True)
        total_imgs += len(imgs)
        page_area = abs(page.rect.width * page.rect.height) or 1
        img_area = 0.0
        for img in imgs:
            for r in page.get_image_rects(img[0]):
                img_area += abs(r.width * r.height)
        ratio = img_area / page_area
        cls = classify(len(text.strip()), ratio)
        counts[cls] += 1
        if i < 3 or i in (n // 2, n - 1):
            sample = " ".join(text.split())[:160]
            print(f"  p{i+1:>3}: text={len(text):>5}  imgs={len(imgs):>2}  imgArea={ratio:4.2f}  -> {cls}")
            print(f"        sample: {sample!r}")
    print(f"\nAGGREGATE: {counts}")
    print(f"total_text_chars={total_text}  total_images={total_imgs}")
    dominant = max(counts, key=counts.get)
    print(f"dominant_page_type={dominant}")


if __name__ == "__main__":
    main(sys.argv[1])
