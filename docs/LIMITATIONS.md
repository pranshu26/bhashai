# BhashAI — Limitations & Fallback Strategy

We state limits plainly. The product's credibility depends on **never overclaiming**. Every limit
below has (a) a detection signal, (b) a fallback, and (c) a user-visible flag.

## 1. Translation quality limits

| Limit | Why | Detection | Fallback | Flag |
| --- | --- | --- | --- | --- |
| Quality varies by language | low-resource languages, fewer training data | per-language QA score trends, back-translation drift | route to best engine per language; LLM post-edit; recommend human review | `back_translation_drift`, low `qaScore` |
| Idioms / literary nuance | MT literalness | LLM-judge `tone_issue`/`wrong_translation` | LITERARY tone + post-edit; flag for human | `tone_issue` |
| Domain terminology drift | no approved terms | glossary-compliance check | require/encourage glossary upload; TM reuse | `glossary_violation` |
| Honorific/register errors | T–V distinctions | tone-validation sampling | tone policy in prompt; flag | `tone_issue` |
| Hallucination / omission | LLM on long text | length-anomaly + LLM-judge `missing/added_meaning` | smaller chunks, no-omit prompt, re-translate | `length_anomaly`, `missing_meaning` |

**Core fallback:** when the primary engine's output fails QA, the router (a) retries with the
next engine in the chain, (b) re-runs post-edit, and only then (c) marks the chunk `QA_FLAGGED`
and routes it to human review. Nothing is silently shipped.

## 2. Document/PDF limits

| Limit | Why | Detection | Fallback | Flag |
| --- | --- | --- | --- | --- |
| Exact layout of arbitrary translated PDFs | translated text length ≠ source; reflow inevitable | always | **REFLOWED** mode (default) — clean, readable, structure-faithful | mode banner |
| LAYOUT_PRESERVED overflow | longer target text in fixed boxes | render-time fit check | shrink-to-fit → spill | `layout_warning` |
| Complex multi-column scanned PDFs | OCR reading-order ambiguity | block-order heuristic confidence | REFLOWED + human review | `ocr_warning`, `layout_warning` |
| Text baked into figures/charts | not reliably OCR-able; would require repainting | OCR confidence per region | keep image as-is; translate caption + references only | `image_text_warning` |
| Equations / formulas | re-typesetting is out of scope | block type = equation | preserve as image/block, do not translate | `image_text_warning` |
| Exotic fonts/ligatures (esp. complex scripts) | font substitution shifts metrics | render diff | embed appropriate Unicode font; auto-fit | `layout_warning` |
| Footnotes/endnotes in PDF | format may not expose linkage | extraction check | place as same-page blocks; DOCX preserves properly | `reference_mismatch` (if lost) |

**Core fallback:** if LAYOUT_PRESERVED cannot render a page within fidelity tolerance, the job
falls back to REFLOWED for that page (or whole doc) and records why. The user is told which mode
was actually used and can request BILINGUAL for verification.

## 3. Scale limits

| Limit | Mitigation |
| --- | --- |
| Very large files (100MB+/500+ pages) | stream parse, S3-backed artifacts, per-chunk queue, partial completion + resumable retry |
| LLM context window | never send whole doc; per-chunk prompts with summaries as context |
| Engine rate limits / cost spikes | per-engine concurrency caps, cost ceiling per job, async Amazon batch for bulk |
| Worker crash mid-job | idempotent stages + durable Postgres/Redis state → resume on restart |

## 4. What we explicitly do NOT do (v1)

- Repaint/redraw complex figures with translated internal text.
- Re-typeset mathematical equations.
- Guarantee pixel-identical PDFs.
- Translate audio/video/images-as-art.
- Promise equal quality across all 12 languages — we measure and report per-language quality.

## 5. Degradation ladder (how the system steps down, never off)

```
best:   IndicTrans2/Google doc-translate + glossary + LLM post-edit + full QA + LAYOUT_PRESERVED
  │ engine disabled / unsupported lang
  ▼
        LLM translate + glossary + post-edit + full QA + REFLOWED
  │ QA fails repeatedly
  ▼
        next engine in chain + re-post-edit
  │ still failing
  ▼
        mark chunk QA_FLAGGED → human review mode (job PARTIALLY_COMPLETED, downloadable)
  │ stage crashes
  ▼
        retry w/ backoff → dead-letter + JobEventLog error → user can retry-failed
```

At no rung do we drop content or claim success we didn't achieve.
