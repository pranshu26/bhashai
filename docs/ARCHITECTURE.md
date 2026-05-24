# BhashAI — System Architecture

> Companion docs: [PRD](./PRD.md) · [Translation Quality](./TRANSLATION-QUALITY.md) ·
> [PDF Reconstruction](./PDF-RECONSTRUCTION.md) · [Deployment](./DEPLOYMENT-EC2.md) ·
> [Testing](./TESTING.md) · [Limitations](./LIMITATIONS.md) · [Plan](./IMPLEMENTATION-PLAN.md)

## 1. Design principles

1. **Asynchronous by default.** Anything touching a file is a queued job, not a request handler.
2. **Pipeline, not a model.** Quality is produced by analyze → route → translate → post-edit →
   QA → reconstruct, with feedback loops — never by trusting one engine.
3. **Idempotent, resumable units.** Each chunk and each stage can re-run safely. A poisoned
   chunk never destroys the job.
4. **Preserve the original, always.** The source file is immutable; everything else is derived.
5. **Honest output.** If fidelity is degraded, we flag it; we never silently drop content.
6. **Config over code.** Languages, engines, plans, and feature gates are configuration.

## 2. Process topology

```
                                  ┌─────────────────────┐
        Browser (Next.js, apps/web)                      │
                  │  HTTPS (REST + polling/WS)            │
                  ▼                                       │
        ┌───────────────────┐         ┌──────────────────┴─────┐
        │ Nginx (reverse     │         │  Redis (BullMQ queues, │
        │ proxy + TLS)       │         │  job state, pub/sub)   │
        └─────────┬──────────┘         └──────────┬─────────────┘
                  ▼                                ▲
        ┌───────────────────┐                     │ enqueue / events
        │ api-server         │─────────────────────┘
        │ (NestJS, apps/api) │
        └───┬───────────┬────┘
            │           │ Prisma
            │           ▼
            │     ┌──────────────┐        ┌─────────────────────────────┐
            │     │ PostgreSQL   │        │ Worker processes (apps/worker)│
            │     │ (Prisma)     │◄───────│  extraction / translation /   │
            │     └──────────────┘        │  qa / reconstruction          │
            │                             └───────┬───────────────┬───────┘
            ▼ presigned URLs                      │ HTTP          │ HTTP
        ┌──────────────┐              ┌───────────▼──────┐  ┌─────▼─────────────┐
        │ AWS S3        │◄─────────────│ Python svc        │  │ External engines  │
        │ raw/processed │  read/write  │ (services/parser, │  │ Amazon Translate, │
        └──────────────┘              │  IndicTrans2)     │  │ Google, LLMs      │
                                      └───────────────────┘  └───────────────────┘
```

**Processes (each independently deployable & scalable):**

| Process | Package | Responsibility |
| --- | --- | --- |
| `api-server` | `apps/api` | HTTP API, auth, job orchestration, enqueue, progress, downloads. Does **no** heavy work. |
| `extraction-worker` | `apps/worker` | `document.extract`, `document.analyze`, `document.chunk`. |
| `translation-worker` | `apps/worker` | `translation.chunk`, `translation.postedit`. |
| `qa-worker` | `apps/worker` | `translation.qa`. |
| `reconstruction-worker` | `apps/worker` | `document.reconstruct`, `document.export`, `cleanup`. |
| `parser-service` | `services/parser` | Python FastAPI: PDF/DOCX layout extraction, OCR, image/table extraction, layout-preserved PDF render. |
| `indictrans-service` | `services/indictrans` | Python FastAPI: IndicTrans2 inference (CPU dev / GPU prod). Optional, config-gated. |

Workers are logically separate but in Phase 1 can run in **one** `apps/worker` process listening
on all queues (set `WORKER_QUEUES=*`); they split into dedicated processes for scaling (Phase 4).

## 3. End-to-end data flow

```
upload ─► S3 raw ─► TranslationJob(PENDING)
  └─ POST /:id/start
      ├─[document.extract]──► parser-service ─► extractedText + DocumentAssets ─► S3 processed
      ├─[document.analyze]──► doc/chapter summaries, entities, glossary candidates, tone ─► TranslationGuide
      ├─[document.chunk]────► TranslationChunk rows (chapter/section/index, source text)
      ├─[translation.chunk]─► EngineRouter ─► raw translation  (per chunk, parallel, retryable)
      ├─[translation.postedit]► LLM editor ─► natural target-language text (per chunk)
      ├─[translation.qa]────► QA checks ─► qaScore + flags (per chunk) ─► QAReport (aggregate)
      ├─[document.reconstruct]► assemble translated doc tree (DOCX/PDF/bilingual)
      └─[document.export]───► ExportedFile in S3 ─► TranslationJob(COMPLETED) ─► signed download
```

Every transition writes a `JobEventLog` row and updates `TranslationJob.currentStage` +
`progressPercentage`. Failures move the chunk to `FAILED`, increment `failedChunks`, and
(per policy) leave the job `PARTIALLY_COMPLETED` rather than killing it.

## 4. Monorepo layout

```
bhashai/
├─ apps/
│  ├─ api/                 # NestJS HTTP API (orchestrator only)
│  ├─ worker/              # NestJS standalone app hosting BullMQ processors
│  └─ web/                 # Next.js (App Router) + TypeScript frontend
├─ packages/
│  ├─ db/                  # Prisma schema, client, migrations, seed  (@bhashai/db)
│  ├─ shared/              # DTOs, enums, zod schemas, constants, language matrix
│  ├─ engines/             # TranslationEngine interface + router + adapters
│  ├─ parsing/             # extraction/structure/chunking orchestration (calls parser-service)
│  ├─ glossary/            # glossary parse + enforcement + compliance
│  ├─ qa/                  # QA checks + scoring + report builder
│  ├─ reconstruct/         # DOCX/PDF/bilingual assembly
│  └─ storage/             # S3 + local-disk storage abstraction
├─ services/
│  ├─ parser/              # Python FastAPI: PDF/DOCX/OCR/layout
│  └─ indictrans/          # Python FastAPI: IndicTrans2 (optional/GPU)
├─ docs/                   # this documentation set
├─ infra/                  # docker-compose, nginx, ecosystem (PM2), deploy scripts
├─ pnpm-workspace.yaml
├─ turbo.json              # task orchestration (build/test/lint/dev)
├─ tsconfig.base.json
└─ .env.example
```

Shared logic lives in `packages/*` so both `apps/api` and `apps/worker` import the same
engine router, QA, parsing, and DB client — no duplication.

## 5. Database schema (PostgreSQL via Prisma)

The canonical schema lives in `packages/db/prisma/schema.prisma`. The 11 mandatory models and
their enums are below. Money is stored as integer **micro-USD** (`*_microUsd`) to avoid float
drift; text payloads that can be large are stored in S3 with only the **URL/key** in the DB.

```prisma
// ---------- Enums ----------
enum UserRole        { USER ADMIN REVIEWER }
enum JobStatus       { PENDING UPLOADED EXTRACTING ANALYZING CHUNKING
                       TRANSLATING POST_EDITING QA RECONSTRUCTING EXPORTING
                       COMPLETED PARTIALLY_COMPLETED FAILED CANCELLED }
enum JobStage        { CREATED UPLOAD EXTRACT ANALYZE CHUNK TRANSLATE
                       POST_EDIT QA RECONSTRUCT EXPORT DONE }
enum ChunkStatus     { PENDING TRANSLATING TRANSLATED POST_EDITING POST_EDITED
                       QA_PENDING QA_PASSED QA_FLAGGED FAILED APPROVED }
enum DocType         { TXT DOCX PDF_TEXT PDF_SCANNED PDF_MIXED }
enum OutputMode      { REFLOWED LAYOUT_PRESERVED BILINGUAL }
enum Tone            { FORMAL INFORMAL EDUCATIONAL CONVERSATIONAL TECHNICAL
                       LITERARY GOVERNMENT ACADEMIC }
enum AssetType       { IMAGE GRAPH DIAGRAM TABLE FOOTNOTE CAPTION EQUATION
                       HEADER FOOTER PAGE_NUMBER CHART }
enum EngineKind      { MOCK INDICTRANS2 AMAZON_TRANSLATE GOOGLE_ADVANCED
                       LLM GLOSSARY_RULE TRANSLATION_MEMORY }
enum QaSeverity      { INFO WARNING ERROR }

// ---------- Core ----------
model User {
  id           String   @id @default(cuid())
  email        String   @unique
  passwordHash String
  name         String?
  role         UserRole @default(USER)
  planId       String   @default("free")
  createdAt    DateTime @default(now())
  updatedAt    DateTime @updatedAt
  jobs         TranslationJob[]
  glossaries   TranslationGlossaryTerm[]
  references   TranslationReferenceDocument[]
}

model TranslationJob {
  id                 String     @id @default(cuid())
  userId             String
  user               User       @relation(fields: [userId], references: [id])
  sourceLanguage     String     @default("en")
  targetLanguage     String
  tone               Tone       @default(FORMAL)
  mode               String     @default("DOCUMENT") // product mode (see PRD §5)
  docType            DocType?
  outputMode         OutputMode @default(REFLOWED)
  qualityPriority    Boolean    @default(true)        // quality vs speed
  specialInstructions String?
  status             JobStatus  @default(PENDING)
  currentStage       JobStage   @default(CREATED)
  progressPercentage Int        @default(0)
  totalChunks        Int        @default(0)
  completedChunks    Int        @default(0)
  failedChunks       Int        @default(0)
  originalFileUrl    String?    // S3 key of immutable source
  extractedTextUrl   String?    // S3 key of normalized extraction JSON
  translatedFileUrl  String?    // S3 key of final export
  guideJson          Json?      // job translation guide (see TRANSLATION-QUALITY.md §2)
  estimatedCostMicroUsd Int?
  actualCostMicroUsd    Int     @default(0)
  errorMessage       String?
  createdAt          DateTime   @default(now())
  updatedAt          DateTime   @updatedAt
  completedAt        DateTime?

  chunks      TranslationChunk[]
  assets      DocumentAsset[]
  qaReport    QAReport?
  engineRuns  TranslationEngineRun[]
  exports     ExportedFile[]
  events      JobEventLog[]
  glossaryTerms TranslationGlossaryTerm[]
  references    TranslationReferenceDocument[]

  @@index([userId, status])
}

model TranslationChunk {
  id             String      @id @default(cuid())
  jobId          String
  job            TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  chapterIndex   Int         @default(0)
  sectionTitle   String?
  chunkIndex     Int                              // global order within job
  sourceText     String                           // chunk source (sized for inline storage)
  translatedText String?                          // post-edited final
  rawTranslatedText String?                        // pre-post-edit
  status         ChunkStatus @default(PENDING)
  retryCount     Int         @default(0)
  engineUsed     EngineKind?
  qaScore        Int?                             // 0-100
  qaFlags        Json?
  tokenCount     Int?
  prevContext    String?                          // summary of preceding chunk
  errorMessage   String?
  createdAt      DateTime    @default(now())
  updatedAt      DateTime    @updatedAt

  engineRuns TranslationEngineRun[]
  @@unique([jobId, chunkIndex])
  @@index([jobId, status])
}

model TranslationGlossaryTerm {
  id              String  @id @default(cuid())
  userId          String?
  user            User?   @relation(fields: [userId], references: [id])
  jobId           String?
  job             TranslationJob? @relation(fields: [jobId], references: [id])
  targetLanguage  String
  sourceTerm      String
  targetTerm      String
  doNotTranslate  Boolean @default(false)
  caseSensitive   Boolean @default(false)
  notes           String?
  createdAt       DateTime @default(now())
  @@index([userId, targetLanguage])
  @@index([jobId])
}

model TranslationReferenceDocument {
  id             String  @id @default(cuid())
  userId         String?
  user           User?   @relation(fields: [userId], references: [id])
  jobId          String?
  job            TranslationJob? @relation(fields: [jobId], references: [id])
  targetLanguage String
  title          String?
  fileUrl        String                 // uploaded approved reference
  styleGuideJson Json?                  // derived "Reference Style Guide"
  createdAt      DateTime @default(now())
}

model TranslationMemoryEntry {
  id             String  @id @default(cuid())
  userId         String?
  targetLanguage String
  domain         String?
  sourceText     String
  targetText     String
  sourceHash     String                 // normalized hash for lookup
  quality        Int     @default(0)    // 0-100, human-approved entries score high
  approvedByHuman Boolean @default(false)
  createdAt      DateTime @default(now())
  @@unique([sourceHash, targetLanguage])
  @@index([targetLanguage, domain])
}

model DocumentAsset {
  id                   String   @id @default(cuid())
  jobId                String
  job                  TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  assetType            AssetType
  originalPageNumber   Int?
  originalBoundingBox  Json?            // {x,y,width,height,page} in PDF points
  fileUrl              String?          // extracted image/table asset in S3
  captionSourceText    String?
  captionTranslatedText String?
  referenceId          String?          // e.g. "Figure 4", "Table 2" label
  ocrConfidence        Float?
  createdAt            DateTime @default(now())
  @@index([jobId, assetType])
}

model QAReport {
  id                 String   @id @default(cuid())
  jobId              String   @unique
  job                TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  overallScore       Int                       // 0-100 aggregate
  pass               Boolean
  chunksTranslated   Int
  chunksFlagged      Int
  glossaryViolations Int      @default(0)
  numberMismatches   Int      @default(0)
  untranslatedWarnings Int    @default(0)
  layoutWarnings     Int      @default(0)
  ocrWarnings        Int      @default(0)
  imageTextWarnings  Int      @default(0)
  reportJson         Json                       // full structured report (see QA-REPORT-FORMAT.md)
  recommendedReview  Json                       // sections recommended for human review
  createdAt          DateTime @default(now())
}

model TranslationEngineRun {
  id              String     @id @default(cuid())
  jobId           String
  job             TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  chunkId         String?
  chunk           TranslationChunk? @relation(fields: [chunkId], references: [id], onDelete: Cascade)
  engine          EngineKind
  promptVersion   String?
  inputText       String?
  rawOutput       String?
  postEditedOutput String?
  latencyMs       Int?
  costMicroUsd    Int?
  qaFlags         Json?
  success         Boolean    @default(true)
  errorMessage    String?
  createdAt       DateTime   @default(now())
  @@index([jobId, engine])
  @@index([chunkId])
}

model ExportedFile {
  id          String     @id @default(cuid())
  jobId       String
  job         TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  outputMode  OutputMode
  format      String                  // "docx" | "pdf" | "txt"
  fileUrl     String                  // S3 key
  sizeBytes   Int?
  isPartial   Boolean    @default(false)
  createdAt   DateTime   @default(now())
}

model JobEventLog {
  id        String   @id @default(cuid())
  jobId     String
  job       TranslationJob @relation(fields: [jobId], references: [id], onDelete: Cascade)
  stage     JobStage
  event     String                    // machine code, e.g. "chunk.translate.completed"
  level     String   @default("info") // info | warn | error
  message   String?
  dataJson  Json?
  createdAt DateTime @default(now())
  @@index([jobId, createdAt])
}
```

### JobEventLog event vocabulary (must be emitted)
`job.created`, `file.uploaded`, `extract.started`, `extract.completed`,
`analyze.completed`, `glossary.generated`, `chunk.completed`,
`chunk.translate.started`, `chunk.translate.completed`, `chunk.translate.failed`,
`qa.completed`, `export.generated`, `job.failed`, `job.cancelled`,
`job.partially_completed`, `job.completed`.

## 6. TranslationJob state machine

```
PENDING ─upload─► UPLOADED ─start─► EXTRACTING ─► ANALYZING ─► CHUNKING ─►
TRANSLATING ─► POST_EDITING ─► QA ─► RECONSTRUCTING ─► EXPORTING ─► COMPLETED
   │                  │            │           │
   └── any stage ──► FAILED (fatal) / PARTIALLY_COMPLETED (some chunks failed)
   └── user ──► CANCELLED
```

`currentStage` mirrors the active queue. `progressPercentage` is computed as a weighted blend
of stage weights and `completedChunks/totalChunks` during translation (see §8 weights).

## 7. API design (REST, JSON, JWT bearer)

All routes are under `/api`. Auth via `Authorization: Bearer <jwt>`. Ownership enforced:
a user may only touch their own jobs (ADMIN bypasses). Validation via zod/class-validator.

| Method | Path | Purpose | Notes |
| --- | --- | --- | --- |
| POST | `/auth/signup` | Create account | returns `{user, accessToken}` |
| POST | `/auth/login` | Login | returns `{user, accessToken}` |
| POST | `/translation-jobs` | Create job (settings, no file yet) | status `PENDING` |
| GET | `/translation-jobs` | List my jobs | paginated |
| GET | `/translation-jobs/:id` | Job detail | includes counts, stage, costs |
| POST | `/translation-jobs/:id/upload` | Attach file | presigned-PUT or multipart; sets `UPLOADED` |
| POST | `/translation-jobs/:id/start` | Begin pipeline | enqueues `document.extract` |
| POST | `/translation-jobs/:id/cancel` | Cancel | drains queues, sets `CANCELLED` |
| POST | `/translation-jobs/:id/retry-failed` | Re-enqueue failed chunks | resumable |
| GET | `/translation-jobs/:id/progress` | Progress snapshot | stage, counts, warnings, partial dl |
| GET | `/translation-jobs/:id/chunks` | List chunks | source/translated/qa per chunk |
| PATCH | `/translation-chunks/:id` | Human edit chunk | sets `APPROVED`, feeds TM |
| POST | `/translation-chunks/:id/retranslate` | Re-run one chunk | optional engine override |
| POST | `/glossaries` | Upload/add glossary (CSV or terms) | parsed to terms |
| GET | `/glossaries` | List glossaries/terms | by user/lang |
| POST | `/reference-documents` | Upload approved reference | triggers style-guide derivation |
| GET | `/translation-jobs/:id/download` | Signed URL for export | `?mode=` selects output |
| GET | `/translation-jobs/:id/qa-report` | QA report JSON | see QA-REPORT-FORMAT.md |
| GET | `/health` | Liveness/readiness | DB + Redis + S3 checks |
| GET | `/admin/jobs`, `/admin/jobs/:id/events` | Admin/debug | ADMIN only |

**Progress delivery:** polling `GET /:id/progress` (Phase 1) with a `Retry-After` hint;
optional WebSocket/SSE channel `/translation-jobs/:id/stream` backed by Redis pub/sub (Phase 3).

## 8. Queue design (BullMQ + Redis)

Nine queues, one responsibility each. Job data carries **only identifiers + S3 keys**, never
large text payloads (workers fetch from DB/S3). Every processor is **idempotent** (guarded by
current DB status) and has retry with exponential backoff.

| Queue | Payload | Producer | Effect |
| --- | --- | --- | --- |
| `document.extract` | `{jobId}` | start endpoint | parse → extractedText + assets |
| `document.analyze` | `{jobId}` | extract worker | summaries, entities, glossary, tone → guide |
| `document.chunk` | `{jobId}` | analyze worker | create TranslationChunk rows |
| `translation.chunk` | `{jobId, chunkId}` | chunk worker (fan-out) | route+translate one chunk |
| `translation.postedit` | `{jobId, chunkId}` | translate worker | LLM post-edit one chunk |
| `translation.qa` | `{jobId, chunkId}` | postedit worker | per-chunk QA |
| `document.reconstruct` | `{jobId}` | qa fan-in (all chunks done) | assemble document tree |
| `document.export` | `{jobId, outputMode}` | reconstruct worker | render DOCX/PDF/bilingual |
| `cleanup` | `{jobId}` | export worker / cron | TTL temp artifacts, finalize |

**Fan-out / fan-in:** `document.chunk` enqueues one `translation.chunk` per chunk
(BullMQ child jobs or a counter in Redis). Reconstruction is gated on
`completedChunks + failedChunks == totalChunks`. Atomic counters live in a Redis key per job;
DB counts are the durable source of truth reconciled on each chunk completion.

**Retry policy:** `attempts: 5`, `backoff: { type: 'exponential', delay: 5000 }`. Terminal
failures land in a per-queue **dead-letter** set + a `JobEventLog` error + chunk `FAILED`.
A failed chunk does **not** fail the job; `retry-failed` re-enqueues just the failed set.

**Idempotency keys:** `jobId:stage` for stage jobs, `chunkId:stage` for chunk jobs. Re-delivery
checks DB status first and no-ops if already past that state.

**Progress weights (default):** extract 10, analyze 10, chunk 5, translate 45, postedit 10,
qa 10, reconstruct 5, export 5. Within translate, sub-progress = `completedChunks/totalChunks`.

## 9. Worker design

- Workers are NestJS standalone apps registering BullMQ `Worker`s for the queues named in
  `WORKER_QUEUES` (`*` = all). Concurrency per queue via `WORKER_CONCURRENCY_*` env.
- CPU/IO-heavy parsing & OCR is delegated to `services/parser` (Python) over HTTP; the Node
  worker orchestrates and persists, keeping Node event loop free.
- **Graceful shutdown:** workers finish in-flight jobs on SIGTERM (BullMQ `close()`), so a
  crash/restart resumes from the queue — no lost chunks.
- **Crash recovery:** because state is in Postgres + Redis, restarting a worker re-processes
  only un-acked/queued jobs. The "queue recovery after worker crash" test asserts this.

## 10. Translation engine router

The router is the heart of the "never trust one engine" requirement. Full design in
[TRANSLATION-QUALITY.md](./TRANSLATION-QUALITY.md) §3. Summary:

```ts
interface TranslationEngine {
  kind: EngineKind;
  supports(src: string, tgt: string): boolean;     // capability matrix
  isEnabled(): boolean;                              // env/config gate
  translate(req: TranslateRequest): Promise<TranslateResult>; // {text,costMicroUsd,latencyMs,raw}
}
```

`EngineRouter.selectChain(src, tgt, job)` returns an ordered list (primary + fallbacks) from a
**capability + preference matrix** (per-language best engine), filtered by enabled engines and
the job's quality/speed flag. The router executes the chain until one succeeds, records a
`TranslationEngineRun` for **every** attempt (engine, prompt version, latency, cost, raw +
post-edited output, QA flags), and supports **comparison mode** (run N engines on the same
chunk and score). The post-edit + glossary-rule + translation-memory layers are themselves
engines in the registry, composed by the router.

## 11. Storage layout (S3)

```
S3_BUCKET_RAW/
  jobs/{jobId}/source/{originalFilename}            # immutable original
S3_BUCKET_PROCESSED/
  jobs/{jobId}/extracted/document.json              # normalized structure tree
  jobs/{jobId}/assets/{assetId}.{png|json}          # images/tables
  jobs/{jobId}/exports/{mode}.{docx|pdf}            # final outputs
  references/{refId}/{filename}
```

Downloads are served as **time-limited presigned URLs**; the API never streams large files.
S3 lifecycle rules expire `extracted/` and `assets/` temp artifacts after N days (Phase 4).
Local-disk storage driver mirrors these keys under `./.data/` for dev without AWS.
