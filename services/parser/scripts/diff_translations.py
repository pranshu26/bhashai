"""Compare two translated outputs of the same source document, paragraph-by-paragraph.
Use to A/B'test engines on a real input (e.g. saathi curriculum DOCX via Qwen vs Sarvam-M).

Outputs:
- Per-paragraph diff: source / engine-A / engine-B, with both leak scores from
  verify_output.longest_english_run.
- Aggregate: leak counts, % of paragraphs where the two engines disagree heavily (very
  different length or wildly different first-N tokens), and per-engine timing if reports
  are available.

Usage:
    python diff_translations.py original.docx engine_a.docx engine_b.docx --target hi -o report.md
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_output import has_indic, longest_english_run, scan_docx, scan_pdf  # noqa: E402


def read_paragraphs(path: Path) -> list[tuple]:
    ext = path.suffix.lower()
    if ext == ".docx":
        return scan_docx(path)
    if ext == ".pdf":
        return scan_pdf(path)
    raise SystemExit(f"unsupported extension: {ext}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source",  help="original English document")
    ap.add_argument("engineA", help="output from engine A (e.g. current Qwen)")
    ap.add_argument("engineB", help="output from engine B (e.g. new Sarvam-M+IndicTrans2)")
    ap.add_argument("--target", default="hi", help="target language code")
    ap.add_argument("--show",   type=int, default=20, help="diffs to render")
    ap.add_argument("-o", "--output", help="write a markdown report here (default: stdout)")
    args = ap.parse_args()

    src = read_paragraphs(Path(args.source).expanduser().resolve())
    a   = read_paragraphs(Path(args.engineA).expanduser().resolve())
    b   = read_paragraphs(Path(args.engineB).expanduser().resolve())

    n = min(len(src), len(a), len(b))
    if not (len(src) == len(a) == len(b)):
        print(f"WARN: paragraph counts differ — src={len(src)} A={len(a)} B={len(b)}. "
              f"Comparing the first {n}.", file=sys.stderr)

    leaks_a = sum(1 for _, t in a[:n] if has_indic(t) and longest_english_run(t) >= 3)
    leaks_b = sum(1 for _, t in b[:n] if has_indic(t) and longest_english_run(t) >= 3)
    full_eng_a = sum(1 for _, t in a[:n] if not has_indic(t) and any(c.isalpha() for c in t))
    full_eng_b = sum(1 for _, t in b[:n] if not has_indic(t) and any(c.isalpha() for c in t))

    lines = []
    lines.append(f"# A/B translation diff — target={args.target}\n")
    lines.append("| Metric | A | B |")
    lines.append("|---|---|---|")
    lines.append(f"| Paragraphs scanned | {n} | {n} |")
    lines.append(f"| Mixed-leak paragraphs | {leaks_a} | {leaks_b} |")
    lines.append(f"| Fully-English paragraphs | {full_eng_a} | {full_eng_b} |")
    lines.append("")
    lines.append("Lower is better in both rows.\n")

    # Find the most divergent paragraphs (largest length ratio between A and B).
    diffs = []
    for i in range(n):
        sa = a[i][1]
        sb = b[i][1]
        if not sa or not sb:
            continue
        ratio = max(len(sa), len(sb)) / max(1, min(len(sa), len(sb)))
        diffs.append((ratio, i))
    diffs.sort(reverse=True)

    lines.append(f"## Most divergent {min(args.show, len(diffs))} paragraphs (largest length ratio)\n")
    for ratio, i in diffs[: args.show]:
        sb_text = b[i][1]
        sa_text = a[i][1]
        src_text = src[i][1] if i < len(src) else "(missing)"
        lines.append(f"### Paragraph #{i + 1}  (length ratio {ratio:.2f}×)")
        lines.append("**Source**")
        lines.append(f"> {src_text[:600]}{'…' if len(src_text) > 600 else ''}")
        lines.append("**Engine A**")
        lines.append(f"> {sa_text[:600]}{'…' if len(sa_text) > 600 else ''}")
        lines.append(f"  · leak-words={longest_english_run(sa_text)}")
        lines.append("**Engine B**")
        lines.append(f"> {sb_text[:600]}{'…' if len(sb_text) > 600 else ''}")
        lines.append(f"  · leak-words={longest_english_run(sb_text)}")
        lines.append("")

    out = "\n".join(lines)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {args.output} ({len(lines)} lines)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
