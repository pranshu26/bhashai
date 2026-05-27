"""Translate a single document via the parser's pipeline, end to end. Useful for A/B'ing
engines without spinning up the API + worker stack.

Examples:
    # Use whatever's in .env / app.py defaults
    python translate_doc.py ~/Downloads/saathi.docx hi

    # Force the new self-hosted backbone (assumes you've already exported the env vars)
    TRANSLATE_ENGINE=indictrans+llm \\
    INDICTRANS_SERVICE_URL=https://<aws-box> \\
    LLM_BASE_URL=https://<aws-box>/v1 \\
    LLM_API_KEY=... \\
    LLM_MODEL=sarvam-m \\
    python translate_doc.py ~/Downloads/saathi.docx hi -o /tmp/saathi-new.docx

Prints a JSON report with: elapsed, engine, blocksTranslated, failedBlocks. Then runs
verify_output.py on the result so you immediately see if there are mid-paragraph leaks.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Allow running from inside services/parser/scripts/ — make the parser modules importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import overlay  # noqa: E402
import llm_postedit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help="path to source .docx or .pdf")
    ap.add_argument("target", help="target language code (hi, mr, bn, pa, gu, ta, te, kn, ml, or, as, ur)")
    ap.add_argument("-o", "--output", help="output path (default: <input>-<target>.<ext>)")
    ap.add_argument("--engine", default=None,
                    help='override TRANSLATE_ENGINE — one of "llm" | "sarvam" | "indictrans" | "indictrans+llm"')
    ap.add_argument("--post-edit", default=None, choices=["on", "off"],
                    help="force LLM refine on/off (default: auto — on when LLM_BASE_URL is configured)")
    ap.add_argument("--pages", default="", help="PDF only: page range, e.g. 1-10")
    ap.add_argument("--no-verify", action="store_true", help="skip the verify_output.py scan at the end")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 2

    ext = src.suffix.lower()
    out_path = Path(args.output).expanduser().resolve() if args.output else src.with_name(
        f"{src.stem}-{args.target}{ext}"
    )

    engine = args.engine or os.environ.get("TRANSLATE_ENGINE", "llm")
    post_edit = None if args.post_edit is None else (args.post_edit == "on")

    print(f"  input    : {src}")
    print(f"  output   : {out_path}")
    print(f"  target   : {args.target}")
    print(f"  engine   : {engine}")
    print(f"  llm      : {'configured' if llm_postedit.is_enabled() else 'NOT configured'}")
    print(f"  indictrans URL: {os.environ.get('INDICTRANS_SERVICE_URL', '(not set)')}")
    print()

    t0 = time.monotonic()
    if ext == ".pdf":
        report = overlay.translate_pdf(
            str(src), str(out_path), args.target,
            os.environ.get("INDICTRANS_SERVICE_URL", ""),
            pages_spec=args.pages,
            post_edit=(True if post_edit is None and llm_postedit.is_enabled() else (post_edit or False)),
            engine=engine,
            progress_path=str(out_path) + ".progress",
        )
    elif ext == ".docx":
        report = overlay.translate_docx(
            str(src), str(out_path), args.target,
            engine=engine, post_edit=post_edit,
            progress_path=str(out_path) + ".progress",
        )
    else:
        print(f"ERROR: unsupported extension: {ext} (need .pdf or .docx)", file=sys.stderr)
        return 2
    elapsed = time.monotonic() - t0

    summary = {
        "elapsed_seconds": round(elapsed, 1),
        "engine": engine,
        "post_edit": post_edit if post_edit is not None else llm_postedit.is_enabled(),
        "output_path": str(out_path),
        "report": report,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()

    if not args.no_verify:
        print(f"--- verify_output.py {out_path} ---")
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "verify_output", Path(__file__).with_name("verify_output.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["verify_output.py", str(out_path), "--target", args.target]
        return mod.main()

    return 0


if __name__ == "__main__":
    sys.exit(main())
