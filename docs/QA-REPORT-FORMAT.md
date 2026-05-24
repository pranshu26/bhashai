# BhashAI — QA Report Format

Stored in `QAReport.reportJson`; served by `GET /translation-jobs/:id/qa-report`. The UI renders
a human-readable version. **Honesty rule:** if any chunk is flagged or failed, `pass=false` and a
"human review recommended" banner is shown — never "perfect translation."

## JSON schema (served)

```jsonc
{
  "jobId": "ckxyz…",
  "targetLanguage": "mr",
  "tone": "GOVERNMENT",
  "overallScore": 86,                 // 0-100 aggregate
  "pass": false,                      // false if any ERROR-severity flag OR flagged chunks > 0
  "generatedAt": "2026-05-24T12:00:00Z",
  "summary": {
    "chunksTranslated": 412,
    "chunksFlagged": 7,
    "chunksFailed": 0,
    "glossaryViolations": 2,
    "numberMismatches": 1,
    "untranslatedWarnings": 3,
    "layoutWarnings": 4,            // from reconstruction (LAYOUT_PRESERVED overflow etc.)
    "ocrWarnings": 0,
    "imageTextWarnings": 5,        // text inside figures not translated
    "tableWarnings": 0,
    "backTranslationSampled": 41,  // chunks sampled
    "backTranslationDriftHigh": 1
  },
  "outputMode": "REFLOWED",
  "outputModeLimitations": [
    "Exact page layout not preserved; document was reflowed for readability."
  ],
  "flaggedChunks": [
    {
      "chunkId": "ck…", "chapterIndex": 3, "sectionTitle": "4.2 Methodology",
      "chunkIndex": 118, "qaScore": 54,
      "issues": [
        { "type": "number_mismatch", "severity": "ERROR",
          "detail": "source '1947' missing in translation", "sourceSnippet": "…in 1947…",
          "targetSnippet": "…मध्ये…" },
        { "type": "glossary_violation", "severity": "WARNING",
          "detail": "expected 'माहितीचा अधिकार' for 'Right to Information'" }
      ],
      "recommendedFix": "Restore the year 1947; apply approved glossary term."
    }
  ],
  "assetWarnings": [
    { "assetId": "ck…", "assetType": "GRAPH", "page": 12,
      "warning": "Text inside figure not translated (OCR confidence low/disabled)." }
  ],
  "recommendedReview": [
    { "section": "4.2 Methodology", "reason": "number mismatch (ERROR)" },
    { "section": "Figures p.12", "reason": "untranslated in-image text" }
  ],
  "engineUsage": [
    { "engine": "LLM", "chunks": 380, "costMicroUsd": 1820000, "avgLatencyMs": 1400 },
    { "engine": "AMAZON_TRANSLATE", "chunks": 32, "costMicroUsd": 64000, "avgLatencyMs": 220 }
  ]
}
```

## Scoring rules
- Chunk score starts at 100; deterministic flags subtract weights (ERROR −20, WARNING −8,
  INFO −2 per flag, capped), then averaged with the LLM-judge score.
- `overallScore` = chunk-count-weighted mean of chunk scores.
- `pass` is `false` if **any** ERROR-severity flag exists, or `chunksFlagged > 0`, or
  `chunksFailed > 0`. Layout/OCR/image warnings lower confidence and appear in the banner but do
  not by themselves set `pass=false` (they're inherent-fidelity, not correctness, issues) — they
  are always surfaced.

## Flag type reference
`missing_meaning`, `added_meaning`, `wrong_translation`, `untranslated`, `wrong_script`,
`number_mismatch`, `length_anomaly`, `glossary_violation`, `citation_mismatch`,
`reference_mismatch`, `entity_mismatch`, `table_mismatch`, `tone_issue`,
`layout_warning`, `ocr_warning`, `image_text_warning`, `back_translation_drift`.
