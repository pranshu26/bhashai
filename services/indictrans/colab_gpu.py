# =====================================================================================
# BhashAI · IndicTrans2 1B GPU service for Google Colab / Kaggle (free T4)
# -------------------------------------------------------------------------------------
# HOW TO USE:
#   1. Open https://colab.research.google.com  ->  new notebook.
#   2. Runtime > Change runtime type > Hardware accelerator = T4 GPU. Save.
#   3. Paste THIS WHOLE FILE into one cell.
#   4. Put your HuggingFace token in HF_TOKEN below (accept the model terms first at
#      https://huggingface.co/ai4bharat/indictrans2-en-indic-1B ).
#   5. Run the cell. It prints a public URL like  https://<random>.trycloudflare.com
#   6. Send me that URL — I'll point BhashAI's pipeline at it and translate on the 1B model.
#   Keep the cell running (the tunnel lives as long as the cell runs).
# =====================================================================================
HF_TOKEN = "hf_xxx_PASTE_YOURS"          # <-- your HuggingFace read token
MODEL = "ai4bharat/indictrans2-en-indic-1B"
NUM_BEAMS = 5
BATCH = 32

import os, sys, subprocess, threading, time, re, json

subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "transformers>=4.44,<5", "sentencepiece", "IndicTransToolkit",
                "fastapi", "uvicorn", "nest_asyncio"], check=True)
subprocess.run("wget -q -O /usr/local/bin/cloudflared "
               "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 "
               "&& chmod +x /usr/local/bin/cloudflared", shell=True, check=True)

os.environ["HF_TOKEN"] = HF_TOKEN

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
try:
    from IndicTransToolkit.processor import IndicProcessor
except Exception:
    from IndicTransToolkit import IndicProcessor

FLORES = {"en": "eng_Latn", "hi": "hin_Deva", "mr": "mar_Deva", "pa": "pan_Guru",
          "bn": "ben_Beng", "gu": "guj_Gujr", "ta": "tam_Taml", "te": "tel_Telu",
          "kn": "kan_Knda", "or": "ory_Orya", "ur": "urd_Arab", "as": "asm_Beng", "ml": "mal_Mlym"}
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MAX_LEN, MAX_UNIT = 256, 280
print("device:", DEVICE, "| loading", MODEL, "...")

_tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
_model = AutoModelForSeq2SeqLM.from_pretrained(
    MODEL, trust_remote_code=True, torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32
).to(DEVICE).eval()
_ip = IndicProcessor(inference=True)
print("model loaded.")

_SENT = re.compile(r"[^.?!।]*[.?!।]+|\S[^.?!।]*$")

def _units(text):
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT.findall(text) if p.strip()] or [text]
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + len(p) + 1 > MAX_UNIT:
            out.append(cur); cur = p
        else:
            cur = f"{cur} {p}".strip() if cur else p
    if cur:
        out.append(cur)
    return out

def _gen(batch, src_f, tgt_f):
    if not batch:
        return []
    pre = _ip.preprocess_batch(batch, src_lang=src_f, tgt_lang=tgt_f)
    enc = _tok(pre, truncation=True, padding="longest", return_tensors="pt",
               return_attention_mask=True, max_length=MAX_LEN).to(DEVICE)
    with torch.no_grad():
        gen = _model.generate(**enc, use_cache=False, min_length=0, max_length=MAX_LEN,
                              num_beams=NUM_BEAMS, num_return_sequences=1)
    dec = _tok.batch_decode(gen, skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return _ip.postprocess_batch(dec, lang=tgt_f)

def translate(texts, src, tgt):
    src_f, tgt_f = FLORES[src], FLORES[tgt]
    units, spans = [], []
    for t in texts:
        u = _units(t); spans.append((len(units), len(units) + len(u))); units += u
    done = []
    for i in range(0, len(units), BATCH):
        done += _gen(units[i:i + BATCH], src_f, tgt_f)
    return [" ".join(done[a:b]).strip() for a, b in spans]

app = FastAPI()

class T(BaseModel):
    text: str; source: str = "en"; target: str

class TB(BaseModel):
    texts: list; source: str = "en"; target: str

@app.get("/health")
def health(): return {"status": "ok", "device": DEVICE, "model": MODEL, "beams": NUM_BEAMS}

@app.post("/translate")
def tr(r: T):
    try: return {"translation": translate([r.text], r.source, r.target)[0]}
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/translate_batch")
def trb(r: TB):
    try: return {"translations": translate(r.texts, r.source, r.target)}
    except Exception as e: raise HTTPException(500, str(e))

import nest_asyncio, uvicorn
nest_asyncio.apply()
threading.Thread(
    target=lambda: uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning"), daemon=True
).start()
time.sleep(4)
print("\n=== starting public tunnel — copy the https://...trycloudflare.com URL below ===\n")
proc = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://localhost:8001"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in proc.stdout:
    print(line, end="")
