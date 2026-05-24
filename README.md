# BhashAI

English → Indian-language **document** translation platform. Human-quality output with
structure, formatting, references, images, tables, and page order preserved. Asynchronous,
queue-driven, multi-engine, QA-gated. Built for theses, government/NGO/academic/education docs.

> Status: **Phase 0 (foundation) complete.** Architecture + plan written; Phase 1 (core MVP) next.
> See [`docs/IMPLEMENTATION-PLAN.md`](docs/IMPLEMENTATION-PLAN.md) for the build order.

## Why it exists
1. **Indian-language quality** — generic engines fail on regional languages. We use a
   multi-engine pipeline (IndicTrans2 + cloud + LLM post-edit) with glossary enforcement,
   reference calibration, and automated QA. Never one blind engine.
2. **Large-document reconstruction** — long PDFs/DOCX with images, tables, footnotes, citations.
   We parse → analyze → chunk → translate → QA → rebuild into the original document shape, with
   honest output modes and limitation flagging.

## Documentation
| Doc | What |
| --- | --- |
| [PRD](docs/PRD.md) | Product requirements, modes, tones, languages, acceptance criteria |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Components, data flow, DB schema, API, queues, workers, engine router |
| [TRANSLATION-QUALITY](docs/TRANSLATION-QUALITY.md) | 5-step pipeline, router, glossary, QA, scoring |
| [PDF-RECONSTRUCTION](docs/PDF-RECONSTRUCTION.md) | Parsing, OCR, 3 output modes, fidelity strategy |
| [DEPLOYMENT-EC2](docs/DEPLOYMENT-EC2.md) | EC2/Docker/Nginx/PM2 + env var reference |
| [TESTING](docs/TESTING.md) | Test matrix + acceptance gate |
| [QA-REPORT-FORMAT](docs/QA-REPORT-FORMAT.md) | QA report JSON schema |
| [LIMITATIONS](docs/LIMITATIONS.md) | Honest limits + fallback ladder |
| [IMPLEMENTATION-PLAN](docs/IMPLEMENTATION-PLAN.md) | Phased, task-by-task build plan |
| [prompts/](docs/prompts/) | Translate / post-edit / QA / analyze prompt templates |

## Stack
Next.js · NestJS · Prisma/PostgreSQL · BullMQ/Redis · AWS S3 · Python FastAPI (parser,
IndicTrans2) · TypeScript monorepo (pnpm + Turbo).

## Repo layout
```
apps/      api (NestJS) · worker (BullMQ) · web (Next.js)
packages/  shared · db · storage · engines · parsing · glossary · qa · reconstruct
services/  parser (PDF/DOCX/OCR) · indictrans (IndicTrans2)
infra/     docker-compose · nginx · ecosystem (PM2)
docs/      architecture + plan
```

## Quickstart (dev)
```bash
cp .env.example .env            # defaults: local storage, no AWS needed
pnpm install
pnpm infra:up                   # postgres + redis via docker
pnpm db:migrate                 # (after Phase 1 db package lands)
pnpm dev                        # api + web + worker
```

## Engine strategy
The router ships adapters for Mock, LLM (Anthropic/OpenAI/Gemini), Amazon Translate, Google
Advanced, and **IndicTrans2** (AI4Bharat, all 22 Indian languages). Each chunk records the engine,
prompt version, latency, cost, raw + post-edited output, and QA flags. Engines activate via
config — Phase 1 runs Mock + LLM + Amazon; IndicTrans2/Google switch on when provisioned.
