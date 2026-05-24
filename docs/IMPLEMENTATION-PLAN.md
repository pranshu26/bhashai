# BhashAI Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build an asynchronous, queue-driven English→Indian-language document translation
platform with multi-engine routing, QA, and structure-preserving reconstruction.

**Architecture:** pnpm monorepo; NestJS API (orchestrator) + NestJS workers (BullMQ) + Next.js
web + Python parser/IndicTrans services; Postgres (Prisma) + Redis + S3. See
[ARCHITECTURE.md](./ARCHITECTURE.md).

**Tech Stack:** TypeScript, NestJS, Next.js, Prisma, BullMQ, Redis, Postgres, AWS S3, Vitest,
Playwright; Python FastAPI + PyMuPDF/python-docx/Tesseract/Textract.

---

## Scope note (why this is a roadmap + contracts, not 5000 lines of inlined code)

The spec spans ~8 independent subsystems. Per superpowers:writing-plans scope guidance, each
phase below is a self-contained, testable slice. Phase 1 tasks list exact files, the interfaces
to honor, and the acceptance test that proves the task. Actual code is produced during execution
(TDD: failing test → implement → pass → commit), not duplicated here.

## Phase 0 — Foundation (scaffold)  ✅ done with task #9
- pnpm workspace, turbo, tsconfig.base, eslint/prettier.
- `infra/docker-compose.yml` (postgres, redis, api, worker, web, parser).
- `.env.example`, `.gitignore`, root README.
- `packages/shared` (enums, language matrix, zod DTOs), `packages/db` (Prisma).
**Gate:** `pnpm install` clean; `docker compose up postgres redis` healthy.

## Phase 1 — Core MVP (TXT/DOCX, async, Mock+LLM+Amazon, basic glossary + QA)

Build order respects dependencies. Each task = failing test → implement → green → commit.

### 1.1 `packages/db` — Prisma schema + client (task #11)
- Files: `packages/db/prisma/schema.prisma`, `src/index.ts` (exports `PrismaClient` singleton),
  `prisma/seed.ts`.
- Implement all 11 models + enums from ARCHITECTURE.md §5.
- **Gate:** `prisma migrate dev` creates tables; a smoke test creates a User + TranslationJob.

### 1.2 `packages/shared` — contracts (part of task #9)
- Files: `src/enums.ts`, `src/languages.ts` (12 langs + script ranges + names),
  `src/dto/*.ts` (zod schemas for every API body), `src/guide.ts` (TranslationGuide type).
- **Gate:** types compile; language matrix unit test (script regex per language).

### 1.3 `packages/storage` — storage abstraction (task #13 part)
- Files: `src/storage.service.ts` (`put/get/presignPut/presignGet`), `s3.driver.ts`,
  `local.driver.ts`. Driver chosen by `STORAGE_DRIVER`.
- **Gate:** local driver round-trips a file; key layout matches ARCHITECTURE.md §11.

### 1.4 `apps/api` — Nest skeleton + config + health (task #10)
- Files: `src/main.ts`, `src/app.module.ts`, `src/config/*` (env validation via zod),
  `src/health/*`. Global validation pipe + exception filter + Pino logger.
- **Gate:** `GET /api/health` returns DB+Redis+storage status; e2e boots app.

### 1.5 `apps/api` — Auth (task #12)
- Files: `src/auth/*` (signup/login, argon2 hash, JWT, `JwtAuthGuard`, `@CurrentUser`).
- **Gate:** signup→login→access protected route; wrong password rejected.

### 1.6 `apps/api` — Upload + jobs (tasks #13, #14)
- Files: `src/upload/*` (presigned PUT + multipart guard ≤ MAX_UPLOAD_MB),
  `src/translation-jobs/*` (CRUD, start/cancel/retry-failed, progress, chunks), `JobEventLog`
  service, ownership guard.
- `start` enqueues `document.extract`; returns 202 immediately.
- **Gate:** create→upload→start is non-blocking; events logged; ownership enforced.

### 1.7 `packages/parsing` — extract/analyze/chunk (task #15)
- Files: `src/extract.ts` (TXT inline; DOCX + PDF via `PARSER_SERVICE_URL`),
  `src/structure.ts` (doc tree), `src/chunker.ts` (chapter→section→paragraph, no mid-sentence,
  keep headings/captions together, store prev context).
- **Gate:** tests #3 (chunking) and #2/#11 (DOCX structure/assets) green with fixtures.

### 1.8 `packages/engines` — router + adapters (task #16)
- Files: `src/types.ts` (interfaces from TRANSLATION-QUALITY.md §3), `src/router.ts`,
  `src/registry.ts`, `src/adapters/{mock,llm,amazon,glossary-rule}.ts`,
  `src/llm/{anthropic,openai}.ts`, `src/preference-matrix.ts`.
- Include an `indictrans.ts` adapter (HTTP to service) behind enable flag — contract-tested now,
  live later. Record `TranslationEngineRun` for every attempt.
- **Gate:** tests #1 (Mock translate), contract test for IndicTrans2 adapter, router fallback.

### 1.9 `packages/glossary` + `packages/qa` (task #18)
- Glossary: `src/parse-csv.ts`, `src/relevant.ts` (subset per chunk), `src/enforce.ts`
  (placeholder-protect for non-LLM engines), `src/compliance.ts`.
- QA: `src/checks/*` (untranslated, script, number, entity, length, citation, table),
  `src/score.ts`, `src/report.ts` (builds QA-REPORT-FORMAT.md shape), optional `src/judge.ts`.
- **Gate:** tests #5 (glossary), #6 (numbers), #7 (entities), #8 (table) green.

### 1.10 `apps/worker` — queues + processors (task #17)
- Files: `src/queues.ts` (9 queues + names), `src/main.ts` (register workers per `WORKER_QUEUES`),
  `src/processors/{extract,analyze,chunk,translate,postedit,qa,reconstruct,export,cleanup}.ts`,
  `src/progress.ts` (weights), idempotency guards on DB status, retry/backoff config.
- Fan-out chunks; fan-in gate on counts; resumable.
- **Gate:** tests #4 (retry), #13 (crash recovery) green; e2e job completes with Mock engine.

### 1.11 `packages/reconstruct` — DOCX export (task #19)
- Files: `src/docx.ts` (rebuild translated .docx from tree), `src/bilingual.ts`,
  `src/reflowed-pdf.ts` (HTML→PDF via parser-service/WeasyPrint), `ExportedFile` writes.
- **Gate:** test #2/#14 — rebuilt DOCX re-parses with original structure; bilingual export opens.

### 1.12 `apps/web` — core pages (task #20)
- Pages (App Router): landing, login/signup, dashboard, new-job, upload, settings,
  glossary/reference upload, progress (polling), review, download, admin/logs.
- API client with auth; progress page polls `GET /:id/progress`.
- **Gate:** Playwright: create→upload→start→watch progress→download (Mock engine).

### 1.13 Tests + acceptance (task #21)
- Wire CI: docker compose Postgres/Redis, Mock engine, run unit+integration+e2e + `acceptance`.
- **Gate:** all matrix rows in [TESTING.md](./TESTING.md) §2 + acceptance §3 pass.

**Phase 1 languages:** Hindi, Marathi, Bengali first (script checks + fixtures), others enabled
via config.

## Phase 2 — PDF support (task #22)
- `services/parser`: PyMuPDF text+coords+fonts; pdfplumber tables; image extraction; classifier
  (text/scanned/mixed); OCR (Tesseract default, Textract optional); page-by-page streaming.
- `packages/reconstruct`: LAYOUT_PRESERVED overlay (redact+redraw, auto-fit) + reflowed PDF +
  bilingual PDF; RTL for Urdu.
- Caption/figure/table-reference handling; asset warnings.
- **Gate:** tests #9, #10, #11 + layout-warning behavior; honest mode reporting.

## Phase 3 — Quality moat (task #23)
- `services/indictrans`: FastAPI serving IndicTrans2 (CPU dev / GPU prod); router enables it per
  language preference matrix.
- LLM post-edit always-on for non-LLM engines; reference calibration → style guide; translation
  memory (exact+fuzzy); engine comparison mode; chunk QA scoring + back-translation sampling;
  admin QA dashboard; SSE/WS progress.
- **Gate:** engine-comparison records multiple runs/chunk; TM reuse measured; style guide applied.

## Phase 4 — Production hardening (task #24)
- EC2 deploy (compose + nginx + certbot), PM2 alternative, split worker processes, DB→RDS /
  Redis→ElastiCache path, S3 lifecycle + cleanup cron, CloudWatch logs/metrics, cost tracking
  rollups, rate limits, user plans + upload caps, ASG worker scaling, Amazon async batch for bulk.
- **Gate:** load test; `/health` + alarms; documented runbook.

---

## Self-review against spec
- All 14 mandatory backend modules map to tasks 1.4–1.11 + Phase 2/3 (parser, reconstruction,
  reference calibration, billing-placeholder lives in `apps/api/src/billing` cost-estimate stub).
- All 11 DB models defined in 1.1.
- All 16 deliverables: architecture(✅docs), DB(1.1), API(1.6), queue(1.10), worker(1.10), engine
  router(1.8), PDF strategy(docs+Phase2), frontend(1.12), backend(1.4–1.11), worker impl(1.10),
  EC2 guide(✅docs), env guide(✅docs+.env.example), testing(✅docs+1.13), prompts(✅docs),
  QA format(✅docs), limitations(✅docs).
- Acceptance criteria → TESTING.md §3 gate.
