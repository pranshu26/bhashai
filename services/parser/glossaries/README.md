# Parser glossaries

One file per target language code (`<code>.json`). Schema matches `GlossaryPair` on the TS
side (`packages/shared/src/guide.ts`) so a future migration that reads glossaries from the
DB per-job can drop them in unchanged:

```json
[
  { "source": "AI", "target": "एआई" },
  { "source": "prompt", "target": "प्रॉम्प्ट" }
]
```

Loaded by `services/parser/llm_postedit.py::_load_glossary`. The `TRANSLATION_GLOSSARY`
env var (raw `source=target; source=target` string) overrides the file when set, so an
operator can A/B a new glossary without touching the repo.
