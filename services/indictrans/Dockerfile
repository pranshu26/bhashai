# IndicTrans2 service on a CUDA GPU (best quality: 1B model + beam search, fp16).
# Build:  docker build -t bhashai-indictrans services/indictrans
# Run:    docker run --gpus all -p 8001:8001 -e HF_TOKEN=hf_xxx bhashai-indictrans
# The model is HF-gated, so HF_TOKEN must be passed at runtime. First request downloads the
# model into the container layer; for serverless/ephemeral GPUs, bake it in or mount a cache.
FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

WORKDIR /app
RUN pip install --no-cache-dir \
    "transformers>=4.44,<5" sentencepiece IndicTransToolkit \
    "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9"

COPY app.py langs.py ./

# Full 1B en->indic model + 5-beam search — the GPU handles this fast; big quality jump over
# the CPU/MPS dev default (distilled-200M, greedy). Auto-selects CUDA via the service code.
ENV INDICTRANS_MODEL=ai4bharat/indictrans2-en-indic-1B \
    INDICTRANS_NUM_BEAMS=5 \
    INDICTRANS_BATCH=32 \
    HF_HOME=/app/.hf

EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
