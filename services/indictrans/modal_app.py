"""BhashAI IndicTrans2 1B on Modal — serverless GPU, scale-to-zero (~$0 idle).

ONE-TIME SETUP (you run these locally):
  pip install modal
  modal token new                                  # opens browser to log in
  modal secret create huggingface HF_TOKEN=hf_xxx  # your HF token (accept 1B model terms first)
  modal deploy services/indictrans/modal_app.py    # prints a stable https URL

Then set in BhashAI:  INDICTRANS_SERVICE_URL=https://<your>--bhashai-indictrans-web.modal.run
Endpoints match the parser contract: GET /health, POST /translate, POST /translate_batch.
"""
import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch", "transformers>=4.44,<5", "sentencepiece", "IndicTransToolkit",
        "fastapi", "uvicorn[standard]", "pydantic",
    )
)

app = modal.App("bhashai-indictrans")

MODEL = "ai4bharat/indictrans2-en-indic-1B"
NUM_BEAMS = 5
BATCH = 32
MAX_LEN = 256
MAX_UNIT = 280
FLORES = {
    "en": "eng_Latn", "hi": "hin_Deva", "mr": "mar_Deva", "pa": "pan_Guru", "bn": "ben_Beng",
    "gu": "guj_Gujr", "ta": "tam_Taml", "te": "tel_Telu", "kn": "kan_Knda", "or": "ory_Orya",
    "ur": "urd_Arab", "as": "asm_Beng", "ml": "mal_Mlym",
}


@app.cls(
    gpu="T4",
    image=image,
    secrets=[modal.Secret.from_name("huggingface")],  # injects HF_TOKEN
    scaledown_window=300,  # stay warm 5 min after last request, then scale to zero
    timeout=600,
)
class Translator:
    @modal.enter()
    def load(self):
        import re
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        try:
            from IndicTransToolkit.processor import IndicProcessor
        except Exception:
            from IndicTransToolkit import IndicProcessor

        self._re = re.compile(r"[^.?!।]*[.?!।]+|\S[^.?!।]*$")
        self.tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
        self.model = (
            AutoModelForSeq2SeqLM.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16)
            .to("cuda").eval()
        )
        self.ip = IndicProcessor(inference=True)
        self.torch = torch

    def _units(self, text):
        text = text.strip()
        if not text:
            return []
        parts = [p.strip() for p in self._re.findall(text) if p.strip()] or [text]
        out, cur = [], ""
        for p in parts:
            if cur and len(cur) + len(p) + 1 > MAX_UNIT:
                out.append(cur); cur = p
            else:
                cur = f"{cur} {p}".strip() if cur else p
        if cur:
            out.append(cur)
        return out

    def _translate(self, texts, src, tgt):
        src_f, tgt_f = FLORES[src], FLORES[tgt]
        units, spans = [], []
        for t in texts:
            u = self._units(t); spans.append((len(units), len(units) + len(u))); units += u
        done = []
        for i in range(0, len(units), BATCH):
            batch = units[i : i + BATCH]
            if not batch:
                continue
            pre = self.ip.preprocess_batch(batch, src_lang=src_f, tgt_lang=tgt_f)
            enc = self.tok(pre, truncation=True, padding="longest", return_tensors="pt",
                           return_attention_mask=True, max_length=MAX_LEN).to("cuda")
            with self.torch.no_grad():
                gen = self.model.generate(**enc, use_cache=False, min_length=0, max_length=MAX_LEN,
                                          num_beams=NUM_BEAMS, num_return_sequences=1)
            dec = self.tok.batch_decode(gen, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            done += self.ip.postprocess_batch(dec, lang=tgt_f)
        return [" ".join(done[a:b]).strip() for a, b in spans]

    @modal.asgi_app()
    def web(self):
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel

        api = FastAPI()

        class T(BaseModel):
            text: str; source: str = "en"; target: str

        class TB(BaseModel):
            texts: list; source: str = "en"; target: str

        @api.get("/health")
        def health():
            return {"status": "ok", "device": "cuda", "model": MODEL, "beams": NUM_BEAMS}

        @api.post("/translate")
        def tr(r: T):
            try:
                return {"translation": self._translate([r.text], r.source, r.target)[0]}
            except Exception as e:
                raise HTTPException(500, str(e))

        @api.post("/translate_batch")
        def trb(r: TB):
            try:
                return {"translations": self._translate(r.texts, r.source, r.target)}
            except Exception as e:
                raise HTTPException(500, str(e))

        return api
