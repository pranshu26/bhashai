# BhashAI — Product Requirements Document

> Status: v0.1 (foundation). Owner: Pranshu. Last updated: 2026-05-24.

## 1. Vision

BhashAI is an English → Indian-language **document** translation platform that produces
**human-quality** output and **preserves the original document** — structure, formatting,
references, images, graphs, diagrams, captions, tables, page order, and export quality.

It is not a sentence translator with a file upload bolted on. It is an asynchronous,
queue-driven **document reconstruction + translation pipeline** with a quality-assurance
layer designed specifically for the failure modes of Indian-language machine translation.

## 2. The two problems we exist to solve

### Problem 1 — Indian-language translation quality
General-purpose engines degrade sharply on Indian regional languages (low-resource
scripts, register/honorific complexity, code-mixing, domain terms, transliteration of
named entities). A single generic LLM call is **not acceptable** as the product.

**Our answer:** a multi-engine pipeline (Indian-language-specialized models +
cloud engines + LLM post-editing), driven by per-job context (summaries, glossary,
do-not-translate lists, tone/register), and gated by automated QA. Quality comes from
the *pipeline*, not from trusting any one engine.

### Problem 2 — Large-document reconstruction
Real inputs are long theses, government reports, NGO/academic/education material, and
Word/PDF files containing images, graphs, tables, footnotes, citations, captions, page
numbers, and internal cross-references. The translated output must look and read like the
original document.

**Our answer:** parse → analyze structure → chunk along document boundaries → translate
with context → QA → reconstruct into the original document shape, with three honest
output modes (reflowed, layout-preserved, bilingual) and explicit limitation reporting.

## 3. Target users

| User | Need |
| --- | --- |
| Academics / researchers | Translate theses, papers, reports while keeping citations, figures, tables. |
| Government / public-sector | Official documents in the right register, approved terminology. |
| NGOs | Education and field material across many Indian languages, on a budget. |
| Education / publishers | Textbooks and chapter-wise material with consistent terminology. |
| Enterprises | Policy, compliance, and report localization with glossary enforcement. |

## 4. Primary target languages

Hindi, Marathi, Punjabi, Bengali, Gujarati, Tamil, Telugu, Kannada, Odia, Urdu, Assamese,
Malayalam. Architecture must extend to all 22 scheduled Indian languages and global
languages without code changes (config + engine capability matrix only).

Source language for v1 is **English**. The pipeline is direction-agnostic by design so
Indian→English and Indian→Indian can be added later.

## 5. Core product modes

1. **Short text translation** — paste text, synchronous, still routed + QA-checked.
2. **Document translation** — DOCX/PDF/TXT upload, asynchronous.
3. **Thesis / report translation** — long-document mode, chapter detection, TOC, references.
4. **Chapter-wise translation** — translate/download selected chapters independently.
5. **Bilingual side-by-side output** — source + translation aligned per paragraph/chunk.
6. **Glossary / reference-calibrated translation** — enforce approved terms + style from
   uploaded reference documents.
7. **Human review mode** — reviewer edits chunks, approves/retranslates, edits feed
   translation memory.

## 6. Tone / register options

Formal, Informal, Educational, Conversational, Technical, Literary, Government/Official,
Academic. Tone is an explicit job parameter that flows into every translation prompt and
into tone-validation QA. For languages with T–V / honorific distinctions (Hindi आप/तुम/तू,
Bengali, etc.), tone selects the pronoun/register policy.

## 7. Functional requirements

### 7.1 Must do
- Accept TXT, DOCX, PDF (text + scanned). Preserve and never discard the original file.
- Run translation **asynchronously** via queues; the frontend never blocks.
- Track progress by **stage** and by **chunk counts** (total / completed / failed).
- Chunk along document structure (chapter → section → paragraph), never mid-sentence.
- Route each chunk through a configurable engine; record engine, cost, latency, raw +
  post-edited output, and QA flags per chunk.
- Enforce glossary / do-not-translate terms in prompts and verify compliance in QA.
- Preserve numbers, dates, %, citations, figure/table references, named entities.
- Reconstruct DOCX preserving heading hierarchy, paragraphs, tables, images, captions.
- Produce a QA report; **never claim perfection when QA flags exist**.
- Allow retry of failed chunks without restarting the whole job; jobs are resumable.
- Keep a full event log of every major step.

### 7.2 Must not do
- Never send a whole large file to an LLM in one call.
- Never silently drop text, images, captions, footnotes, tables, or references.
- Never claim layout preservation it cannot deliver — flag the limitation and offer a
  high-quality reflowed fallback instead.
- Never depend on a single generic engine.

## 8. Non-functional requirements

- **Asynchronous & queue-driven** (BullMQ + Redis). API and workers are separate processes.
- **Scale:** architected for large files (100MB+ PDFs, 500+ page docs). Per-plan upload
  caps enforced at the edge, but the pipeline streams/spills to disk and never assumes the
  whole document fits in memory.
- **Reliability:** idempotent jobs, exponential backoff, partial completion, resumability.
- **Observability:** structured logs, JobEventLog, per-chunk engine runs, health checks.
- **Cost-awareness:** per-chunk cost estimate captured; job-level estimate before start.
- **Security:** auth-gated, per-user job isolation, signed download URLs, secrets in env.
- **Deployable on a single AWS EC2 box** (Docker Compose) and horizontally scalable later.

## 9. Success / acceptance criteria

The product is acceptable only when it:
1. Translates a document asynchronously without blocking the frontend.
2. Stores files in S3 (local-disk driver allowed for dev).
3. Tracks progress; uses queues; retries failed chunks.
4. Preserves DOCX structure on output.
5. Has a serious, implemented-or-specified PDF layout strategy with fallbacks.
6. Supports glossary / reference calibration.
7. Runs automated QA and surfaces flags honestly.
8. Is deployable on EC2.
9. Is designed to support IndicTrans2 or another Indian-language-specialized engine.
10. Does not depend on a single generic LLM call.

See [TESTING.md](./TESTING.md) for the test matrix that proves each criterion.

## 10. Out of scope (v1)

- Real-time/streaming conversational translation.
- Speech/audio/video translation.
- In-image text *re-rendering* (we OCR + translate + flag; we do not repaint complex
  figures). See [LIMITATIONS.md](./LIMITATIONS.md).
- Mobile native apps (responsive web only).
- Full billing/payments (a cost-estimation placeholder module only).

## 11. Assumptions & constraints

- Deployment target is a single EC2 instance initially; GPU model serving (IndicTrans2)
  is a separate, optionally-provisioned service activated by config.
- Phase 1 ships with **Mock + LLM + Amazon Translate** engines wired; IndicTrans2 and
  Google Advanced are complete adapters activated when infrastructure/credentials exist.
- LLM provider keys (Anthropic/OpenAI) are available for the post-edit + QA layers.
- We optimize for **quality and structural fidelity over latency**; "speed priority" is a
  user-selectable mode that trades engines/post-edit passes, not a different pipeline.

## 12. Key risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Indian-language MT quality varies by language | Engine routing per language + LLM post-edit + QA gate; back-translation sampling for high-value docs. |
| Scanned/complex PDF layout can't be perfectly preserved | Honest mode reporting + reflowed fallback + QA layout warnings. |
| Large files exhaust memory | Stream parsing, S3-backed intermediate artifacts, chunk-level queueing. |
| Engine/API outages or cost spikes | Router fallback chain + per-engine enable flags + cost caps. |
| Hallucination / omission by LLM | "No add/no omit" prompts + QA omission/hallucination + length-anomaly checks. |
