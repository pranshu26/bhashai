# BhashAI — Testing Plan

Test pyramid: many fast **unit** tests in `packages/*`, focused **integration** tests per app
module, a few **e2e** tests that drive the real queue with a Mock engine. CI runs all of it with
`STORAGE_DRIVER=local`, Mock engine, and ephemeral Postgres/Redis (docker compose in CI).

## 1. Tooling
- TS unit/integration: **Vitest** (`packages/*`, `apps/api`, `apps/worker`).
- API e2e: **Supertest** against the Nest app + a real test Postgres/Redis.
- Frontend: **Playwright** for the critical flows (Phase 1: create→upload→progress→download).
- Python services: **pytest** (`services/parser`, `services/indictrans`).
- Determinism: the **Mock** engine returns stable, reversible output so QA/number/entity checks
  are assertable without network or cost.

## 2. Required test matrix (maps to the spec's testing requirements)

| # | Requirement | Test | Location |
| --- | --- | --- | --- |
| 1 | Small text translation | translate short text via router(Mock), assert non-empty target, run records | `packages/engines` |
| 2 | DOCX translation | parse fixture .docx → tree → translate → rebuild .docx; re-parse asserts headings/tables/images preserved | `packages/parsing`, `packages/reconstruct` |
| 3 | Long-document chunking | 200-page fixture → chunker; assert no mid-sentence splits, headings stay with sections, order preserved | `packages/parsing` |
| 4 | Failed chunk retry | force chunk to throw N times → backoff → `retry-failed` re-enqueues only failed; job not killed | `apps/worker` e2e |
| 5 | Glossary enforcement | term in source → translation contains approved target; violation flagged | `packages/glossary`, `packages/qa` |
| 6 | Number preservation | numbers/dates/% in source ⊆ target; mismatch → `number_mismatch` | `packages/qa` |
| 7 | Named-entity preservation | guide entities appear in approved render; else `entity_mismatch` | `packages/qa` |
| 8 | Table preservation | table fixture → reconstructed table row×col equal; else `table_mismatch` | `packages/parsing`, `packages/qa` |
| 9 | PDF text extraction | text-PDF fixture → blocks with page/bbox/font; order correct | `services/parser` (pytest) |
| 10 | Scanned PDF OCR fallback | image-only PDF → OCR path returns text + confidence; low-conf flagged | `services/parser` |
| 11 | Image/caption preservation | image-bearing fixture → DocumentAsset created, caption translated, image bytes unchanged | `packages/parsing` |
| 12 | Large file upload | presigned-PUT path issues URL; multipart guard rejects > MAX_UPLOAD_MB | `apps/api` e2e |
| 13 | Queue recovery after crash | kill worker mid-job → restart → job resumes, no lost/dup chunks (idempotency) | `apps/worker` e2e |
| 14 | Export file generation | completed job → ExportedFile rows for requested modes; files openable | `packages/reconstruct` e2e |

## 3. Acceptance-criteria gate (maps to PRD §9)

A CI job `acceptance` asserts, end-to-end with Mock engine on a multi-section DOCX fixture:
1. `POST /translation-jobs` → `POST /:id/upload` → `POST /:id/start` returns immediately (async). ✔ non-blocking
2. Source stored under raw bucket/driver. ✔ S3 (local driver in CI)
3. `GET /:id/progress` advances through stages; chunk counts move. ✔ progress + queues
4. A deliberately-failed chunk is recoverable via `retry-failed`. ✔ retry
5. Output DOCX re-parses with original heading/table/image structure. ✔ DOCX structure
6. PDF strategy present (unit tests for classifier + reflow), even if full PDF is Phase 2. ✔ plan
7. Glossary/reference endpoints accept input and affect prompts/QA. ✔ glossary
8. QAReport produced with flags. ✔ QA
9. `docker compose up` boots all services + `/health` green. ✔ EC2-deployable
10. Engine registry contains an Indian-language-specialized adapter (IndicTrans2), test-covered via contract test. ✔ IndicTrans2-ready
11. More than one engine in the registry; router selects/falls back. ✔ not single-LLM

## 4. Conventions
- Each test is independent; DB reset per file (transaction rollback or truncate).
- No network in unit tests; LLM/Amazon/Google adapters tested via contract tests with recorded
  fixtures + a live smoke test gated behind `RUN_LIVE=1`.
- Fixtures live in `packages/*/test/fixtures` (tiny DOCX/PDF/CSV samples committed to the repo).
- Coverage gate: lines ≥ 70% on `packages/{engines,parsing,glossary,qa,reconstruct}`.
