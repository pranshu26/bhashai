# BhashAI

English → Indian-language **document** translation platform. PDF and DOCX, structure
preserved (layout, fonts, runs, headers/footers, tables, hyperlinks, tracked changes),
asynchronous and queue-driven. Built for school/teacher educational materials, government
and NGO docs, academic content.

> Status: **in production.** Live at `http://16.171.29.33/` (single EC2 box, eu-north-1).
> Production engine: OpenRouter Qwen-2.5-72B via an OpenAI-compatible chat endpoint.
> See [`docs/DEPLOYMENT-EC2.md`](docs/DEPLOYMENT-EC2.md) for the deploy.

## What works today

- **PDF translation** — `services/parser/overlay.py::translate_pdf`. PyMuPDF extracts text
  blocks, the LLM translates them in concurrent batched JSON-array calls with a per-item
  fallback so no paragraph silently falls back to English, the original blocks are redacted
  (images/vector art kept), and HarfBuzz-shaped Devanagari/Indic overlays are rendered back
  in place with auto-fit. Optional OCR pass for scanned/image pages (`ENABLE_OCR=true`).
- **DOCX translation** — `services/parser/overlay.py::translate_docx`. Walks every paragraph's
  `<w:t>` nodes via lxml (including text inside `<w:ins>` tracked-change runs and
  `<w:hyperlink>` wrappers that python-docx's `p.text` silently skips), translates each
  paragraph as one unit, writes the translation into a carrier text node with
  `xml:space="preserve"` and blanks the rest. Styles, lists, headings, tables, headers and
  footers survive.
- **Live progress** — the parser writes `<out_path>.progress` while running; the API reads
  it so the web UI's bar climbs in real time. Per-page failure reporting on the PDF path.
- **Web app** — Next.js. Login, dashboard, upload, job page with live progress, download.
  Fraunces display + Hanken Grotesk body, "Indic ink & marigold" palette, responsive.
- **API + worker** — NestJS (`apps/api`) + BullMQ (`apps/worker`). Worker calls the parser
  via undici with `headersTimeout: 0 / bodyTimeout: 0` so long translations never hit the
  global fetch 300s timeout.
- **Engines** — primary path is OpenAI-compatible chat (`LLM_BASE_URL` + `LLM_API_KEY` +
  `LLM_MODEL`). `services/parser/llm_postedit.py::translate_batch` does the direct
  translation; the same module's `post_edit_batch` does an optional teacher-grade refine
  pass. Alternate paths: Sarvam Translate API (hosted), IndicTrans2 NMT on Modal (with
  optional LLM post-edit), Sarvam-M 24B on Modal (`services/sarvam/`, archived).

## What's planned but not built yet

- `packages/qa/`, `packages/glossary/`, `packages/reconstruct/` — scaffolded but empty.
  The glossary currently lives inline in `llm_postedit.py` and is enforced via the
  translation system prompt. Automated QA scoring is not built — the pipeline reports
  failed-block / failed-page counts and surfaces them in the UI, but there is no
  fidelity scorer yet.
- The engine **router** in `packages/engines/` is plaintext-only. PDF and DOCX paths go
  straight through the Python parser. Migrating PDF/DOCX onto the router so every chunk
  records engine + prompt + latency + cost + QA flags is on the roadmap.

## Stack
Next.js · NestJS · Prisma/PostgreSQL · BullMQ/Redis · AWS S3 (or local store) · Python
FastAPI (parser) · TypeScript monorepo (pnpm + Turbo).

## Repo layout
```
apps/      api (NestJS) · worker (BullMQ) · web (Next.js)
packages/  shared · db · storage · engines · parsing  (glossary, qa, reconstruct — scaffolded)
services/  parser (PyMuPDF/python-docx + LLM) · indictrans (Modal NMT) · sarvam (Modal vLLM, archived)
infra/     docker-compose · nginx · ecosystem (PM2) · deploy-ec2.sh
docs/      architecture · deployment · quality · limitations · prompts
```

## Quickstart (dev)
```bash
cp .env.example .env            # defaults: local storage, no AWS needed
pnpm install
pnpm infra:up                   # postgres + redis via docker
pnpm db:migrate
pnpm dev                        # api + web + worker (turbo)
```
Then run the parser-service in a second shell:
```bash
cd services/parser && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 8000
```

## Documentation
| Doc | What |
| --- | --- |
| [PRD](docs/PRD.md) | Product requirements, modes, tones, languages, acceptance criteria |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Components, data flow, DB schema, API, queues, workers, engine router |
| [TRANSLATION-QUALITY](docs/TRANSLATION-QUALITY.md) | 5-step pipeline, router, glossary, QA, scoring (target — parts not yet built) |
| [PDF-RECONSTRUCTION](docs/PDF-RECONSTRUCTION.md) | Parsing, OCR, 3 output modes, fidelity strategy |
| [DEPLOYMENT-EC2](docs/DEPLOYMENT-EC2.md) | EC2/Docker/Nginx/PM2 + env var reference |
| [TESTING](docs/TESTING.md) | Test matrix + acceptance gate |
| [QA-REPORT-FORMAT](docs/QA-REPORT-FORMAT.md) | QA report JSON schema |
| [LIMITATIONS](docs/LIMITATIONS.md) | Honest limits + fallback ladder |
| [IMPLEMENTATION-PLAN](docs/IMPLEMENTATION-PLAN.md) | Phased, task-by-task build plan |
| [prompts/](docs/prompts/) | Translate / post-edit / QA / analyze prompt templates |
