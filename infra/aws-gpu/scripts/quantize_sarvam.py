"""One-time AWQ quantization of Sarvam-M-24B for vLLM.

Run once on the GPU box if there is no public AWQ release of Sarvam-M yet. Produces
~14 GB of weights at /opt/bhashai/models/sarvam-m-awq, suitable for vLLM:

    vllm serve /opt/bhashai/models/sarvam-m-awq \\
        --served-model-name sarvam-m \\
        --quantization awq_marlin

Takes ~20-30 min on an L40S 48 GB. Needs HF_TOKEN exported (and you must have agreed to
the Sarvam-M model terms on HuggingFace first).
"""
import argparse
import os
from pathlib import Path

from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="sarvamai/sarvam-m", help="HF repo id of the bf16 weights")
    ap.add_argument("--dst", default="/opt/bhashai/models/sarvam-m-awq", help="output dir")
    ap.add_argument("--bits", type=int, default=4)
    ap.add_argument("--group-size", type=int, default=128)
    args = ap.parse_args()

    Path(args.dst).mkdir(parents=True, exist_ok=True)
    quant_cfg = {
        "w_bit": args.bits,
        "q_group_size": args.group_size,
        "zero_point": True,
        "version": "GEMM",  # AWQ-Marlin-compatible
    }
    print(f"Loading {args.src} (bf16) — this downloads ~48 GB on first run...")
    model = AutoAWQForCausalLM.from_pretrained(args.src, safetensors=True, device_map="auto")
    tok = AutoTokenizer.from_pretrained(args.src, trust_remote_code=True)

    print("Quantizing — uses ~24 GB VRAM during calibration, takes 20-30 min on L40S...")
    model.quantize(tok, quant_config=quant_cfg)

    print(f"Saving to {args.dst}...")
    model.save_quantized(args.dst)
    tok.save_pretrained(args.dst)
    print("✓ Done. Point vllm serve at the dst path with --quantization awq_marlin.")


if __name__ == "__main__":
    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("HF_TOKEN env var required (and you must have accepted the model terms)")
    main()
