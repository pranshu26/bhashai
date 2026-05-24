# BhashAI — Translation Quality Strategy

> The product's moat. Quality comes from the **pipeline + QA gate**, not from any one engine.
> Companion: [ARCHITECTURE](./ARCHITECTURE.md) · [QA report format](./QA-REPORT-FORMAT.md) ·
> prompt templates in [`docs/prompts/`](./prompts/).

## 0. Why a generic LLM call is not enough

Indian-language MT fails in specific, repeatable ways:
- **Register/honorifics:** आप vs तुम vs तू; wrong choice makes government text rude or childish.
- **Named-entity transliteration drift:** "Pranab Mukherjee" → inconsistent spellings across pages.
- **Code-mixing & retained English:** "RTI Act", "GDP", "Section 80C" should often stay English.
- **Domain terminology:** legal/medical/academic terms need approved equivalents, not literal ones.
- **Omission & hallucination:** long inputs get summarized or padded by LLMs.
- **Number/date/unit corruption:** ৪ vs 4, lakh/crore vs million, % placement.

We attack each with a dedicated stage and a QA check, then route per-language to the engine
that empirically does best.

## 1. The 5-step quality pipeline

### Step 1 — Analyze document context (`document.analyze`)
Run **once per job** over the extracted structure. Produces:
- Document summary (≤200 words) and per-chapter summaries.
- Key entities (people, orgs, places, schemes, laws) → preserve/transliterate consistently.
- Domain terms + glossary **candidates** (frequent capitalized/technical n-grams).
- Do-not-translate terms (acronyms, code, identifiers, legal section refs).
- Detected tone/register and target audience (cross-checked against the user's chosen tone).
- Measurement/unit and citation/reference styles present.

Implemented as one LLM call over the structure outline + sampled text (never the whole doc),
merged with user-provided glossary/reference signals.

### Step 2 — Build the job translation guide (stored in `TranslationJob.guideJson`)
A single structured object injected into **every** chunk prompt:

```jsonc
{
  "targetLanguage": "mr",
  "tone": "GOVERNMENT",
  "domain": "public-policy",
  "audience": "citizens",
  "styleRules": ["use formal register (आपण)", "spell out scheme names then keep English in ()"],
  "glossary": [{ "source": "Right to Information", "target": "माहितीचा अधिकार" }],
  "approvedTerms": [{ "source": "Gram Panchayat", "target": "ग्रामपंचायत" }],
  "doNotTranslate": ["RTI", "GDP", "Section 80C", "BhashAI"],
  "entities": [{ "name": "Pranab Mukherjee", "render": "प्रणव मुखर्जी" }],
  "acronymPolicy": "keep acronym, gloss once on first use",
  "unitPolicy": "keep numerals as-is; convert million→लाख/कोटी only if source uses Indian system",
  "citationPolicy": "preserve citation markers and reference numbers verbatim",
  "pronounPolicy": "formal-V",
  "sentenceComplexity": "split sentences > 40 words"
}
```

The guide merges three sources, in priority order: **user glossary/reference (highest)** →
reference-style-guide (derived) → auto-analysis (lowest).

### Step 3 — Translate chunk with context (`translation.chunk`)
Every chunk prompt includes: target language, tone, document summary, chapter summary, section
title, previous-chunk summary, glossary terms relevant to *this* chunk, do-not-translate terms,
formatting-preservation + no-hallucination + no-omission instructions, and explicit "preserve
numbers/citations/references/tables/figure-numbers/entities". Template:
[`prompts/translate.md`](./prompts/translate.md).

The router (see §3) picks the engine. For IndicTrans2/Amazon/Google, the structured guide is
applied via custom terminology / pre+post substitution rather than a prompt.

### Step 4 — Post-edit (`translation.postedit`)
A senior-native-editor LLM pass that makes the output read naturally (not literal), enforces
glossary, and preserves numbers/refs/formatting. Template:
[`prompts/postedit.md`](./prompts/postedit.md). Skipped when `qualityPriority=false` and the
primary engine is already an LLM (speed mode), or always-on for IndicTrans2/Amazon outputs.

### Step 5 — QA (`translation.qa`)
Two layers:
- **Deterministic checks** (no LLM, fast, always run) — see §5.
- **LLM judge** (template [`prompts/qa.md`](./prompts/qa.md)) returning strict JSON
  `{pass, score, issues[], recommendedFix}`.
- **Back-translation sampling:** for `qualityPriority` jobs, sample K% of chunks, translate
  back to English, and compare semantic similarity; large drift → flag.

Chunk `qaScore` = weighted blend; chunks below threshold → `QA_FLAGGED` and surfaced for human
review. The job aggregate rolls up into the `QAReport`.

## 2. Glossary system

Users upload **CSV** (`source,target,doNotTranslate,caseSensitive,notes`), an **approved
translated reference document**, a **brand/style guide**, or a **government terminology guide**.

The system:
1. Parses glossary → `TranslationGlossaryTerm` rows (job- or user-scoped).
2. Injects the **relevant subset** per chunk (term appears in the chunk's source) into prompts.
3. For non-LLM engines, applies terms via custom-terminology APIs (Amazon/Google) or
   placeholder-protect → translate → restore (the `GLOSSARY_RULE` engine layer).
4. **Compliance QA:** for each glossary term present in source, assert the approved target
   appears in the translation; otherwise `glossaryViolation` flag.
5. Approved human edits become `TranslationMemoryEntry` rows for reuse.

## 3. Translation engine router (detailed)

### Engine registry
| Engine | `EngineKind` | Role | Phase |
| --- | --- | --- | --- |
| Mock | `MOCK` | deterministic, offline, for tests/CI/dev | 1 |
| LLM | `LLM` | Anthropic/OpenAI/Gemini via provider interface; translate + post-edit + QA judge | 1 |
| Amazon Translate | `AMAZON_TRANSLATE` | AWS-native sync + async batch (S3, ≤5GB), custom terminology | 1 |
| Google Advanced | `GOOGLE_ADVANCED` | document translation (DOCX/PDF/PPTX…), formatting-heavy | 3 |
| IndicTrans2 | `INDICTRANS2` | AI4Bharat, all 22 Indian languages, specialized | 3 |
| Glossary rule | `GLOSSARY_RULE` | placeholder-protect / term substitution layer | 1 |
| Translation memory | `TRANSLATION_MEMORY` | exact/fuzzy reuse of approved human translations | 3 |

### Interface
```ts
export interface TranslateRequest {
  sourceText: string;
  sourceLanguage: string;          // BCP-47-ish, e.g. "en"
  targetLanguage: string;          // e.g. "mr"
  guide: TranslationGuide;         // §2 object
  prevContext?: string;
  tone: Tone;
  promptVersion?: string;
}
export interface TranslateResult {
  text: string;
  raw: string;                     // engine raw output before our normalization
  engine: EngineKind;
  promptVersion?: string;
  latencyMs: number;
  costMicroUsd: number;
  warnings?: string[];
}
export interface TranslationEngine {
  kind: EngineKind;
  supports(src: string, tgt: string): boolean;
  isEnabled(): boolean;
  translate(req: TranslateRequest): Promise<TranslateResult>;
}
```

### Routing policy
```
selectChain(src, tgt, job):
  candidates = registry.filter(e => e.isEnabled() && e.supports(src, tgt))
  ranked = candidates.sortBy(preferenceMatrix[tgt] ?? defaultPreference)
  if job.qualityPriority: ranked = movePostEditOn(ranked)        // always post-edit
  else:                   ranked = preferSingleLLM(ranked)        // fewer calls
  return ranked   // [primary, ...fallbacks]
```

`preferenceMatrix` is **per target language** (config), e.g. for most Indian languages prefer
`INDICTRANS2 → LLM(postedit) → AMAZON_TRANSLATE`; if IndicTrans2 disabled, `LLM → AMAZON`.
The `GLOSSARY_RULE` layer wraps whichever engine runs. Every attempt → `TranslationEngineRun`.

### Comparison mode
When enabled per job/chunk, the router runs the top-N engines on the same chunk, stores all
runs, and selects the highest QA-scoring output (or presents both in the review UI). This is
how we *measure* which engine is best per language instead of guessing.

### Failure handling
Engine throws / times out / returns empty or wrong-script → router advances to the next in the
chain, records the failed run, and only marks the chunk `FAILED` if the whole chain is exhausted.

## 4. Provider-agnostic LLM layer

`packages/engines/llm` exposes one `LlmProvider` interface implemented by Anthropic, OpenAI,
and Gemini adapters (selected by env). Prompts are **versioned** (`promptVersion`) so we can
A/B and roll back. Temperature is low for translation, near-zero for QA-JSON.

## 5. Deterministic QA checks (no LLM, always run)

| Check | Method | Flag |
| --- | --- | --- |
| Untranslated English | ratio of Latin-script tokens in target (minus do-not-translate) | `untranslated` |
| Script validation | target text matches the target language's Unicode block(s) | `wrong_script` |
| Missing text / omission | length ratio target/source far outside language-specific band | `length_anomaly` |
| Number preservation | multiset of numbers in source ⊆ translation (allow numeral-system map) | `number_mismatch` |
| Date / percentage | regex-extracted dates/percents preserved | `number_mismatch` |
| Named entity | entities from guide appear (in approved render) | `entity_mismatch` |
| Glossary compliance | approved target present for each source term | `glossary_violation` |
| Citation/reference | `[12]`, `(Author, 2020)`, "Figure 4", "Table 2" markers preserved | `citation_mismatch` |
| Table cell count | reconstructed table has same row×col count as source | `table_mismatch` |
| Figure/table refs | "as shown in Figure 4" references intact | `reference_mismatch` |

These run in `packages/qa` and are cheap, so they run on **every** chunk regardless of mode.

## 6. Reference calibration

When approved reference documents are uploaded, `document.analyze` (or a dedicated job) derives
a **Reference Style Guide** by analyzing: translation style, preferred vocabulary, typical
sentence length, formality/register, acronym handling, headings style, terminology, whether
English terms are retained, and overall register. Stored in
`TranslationReferenceDocument.styleGuideJson` and merged into the job guide (§2).

## 7. Quality scoring

- **Chunk score (0-100):** start at 100, subtract weighted penalties per deterministic flag,
  then average with the LLM-judge score. Below `QA_PASS_THRESHOLD` (default 70) → `QA_FLAGGED`.
- **Job aggregate:** chunk-count-weighted mean, with hard caps: any ERROR-severity flag caps
  `pass=false`. Surfaces counts of each flag type and a list of recommended-review sections.
- **Honesty rule:** if any chunk is `QA_FLAGGED` or `FAILED`, the job UI and report state that
  human review is recommended; we never present a flagged job as "perfect."

## 8. Tone & register handling

`Tone` selects a register policy injected into prompts and validated in QA:
- GOVERNMENT/FORMAL/ACADEMIC → formal-V pronouns, no contractions, full forms.
- CONVERSATIONAL/INFORMAL → informal pronouns where natural.
- TECHNICAL → keep technical English terms, gloss once.
- LITERARY → prioritize fluency/idiom over literalness.
Tone-validation QA samples register markers and flags mismatches (`tone_issue`).
