# Prompt: document analysis (`promptVersion: analyze.v1`)

Used once per job in `document.analyze` over the structure outline + sampled text
(NOT the full document). Builds inputs for the job translation guide.

## System
You are a document analyst preparing a translation brief. Read the outline and samples and
produce a compact JSON brief. Do not translate anything. Return JSON only.

## User
Target language: {{targetLanguageName}}
User-selected tone: {{tone}}
Document outline (headings/sections):
{{outline}}

Representative text samples:
"""
{{samples}}
"""

Return JSON:
{
  "documentSummary": "<=200 words",
  "chapterSummaries": [{ "index": 0, "title": "", "summary": "" }],
  "domain": "",
  "audience": "",
  "detectedTone": "",
  "entities": [{ "name": "", "type": "PERSON|ORG|PLACE|SCHEME|LAW|OTHER" }],
  "glossaryCandidates": [{ "source": "", "suggestedTarget": "", "reason": "" }],
  "doNotTranslate": [""],
  "unitPolicy": "",
  "citationPolicy": "",
  "styleRules": [""]
}
