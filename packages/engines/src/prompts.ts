import { getLanguage } from '@bhashai/shared';
import type { TranslateRequest } from './types';

export const TRANSLATE_PROMPT_VERSION = 'translate.v1';
export const POSTEDIT_PROMPT_VERSION = 'postedit.v1';

function langName(code: string): string {
  return getLanguage(code)?.name ?? code;
}

function glossaryLines(req: TranslateRequest): string {
  const rel = req.guide.glossary.filter((g) =>
    req.sourceText.toLowerCase().includes(g.source.toLowerCase()),
  );
  if (rel.length === 0) return '(none relevant to this text)';
  return rel.map((g) => `- "${g.source}" -> "${g.target}"`).join('\n');
}

export function buildTranslatePrompt(req: TranslateRequest): { system: string; user: string } {
  const tgt = langName(req.targetLanguage);
  const g = req.guide;
  const system =
    `You are an expert human translator with native-level command of English and ${tgt}. ` +
    `Translate the provided text into ${tgt} naturally and accurately. Do not translate literally. ` +
    `Preserve meaning, tone, formatting, numbers, names, citations, table references, figure references, ` +
    `and all factual content. Do not add or remove meaning. Do not summarize. Do not omit any sentence. ` +
    `Output ONLY the translation — no notes, no English commentary.`;
  const user = [
    `Target language: ${tgt} (${req.targetLanguage})`,
    `Tone / register: ${req.tone}${g.pronounPolicy ? ` (${g.pronounPolicy})` : ''}`,
    g.domain ? `Domain: ${g.domain}` : '',
    g.documentSummary ? `Document summary:\n${g.documentSummary}` : '',
    req.prevContext ? `Previous context (already translated — do NOT re-translate):\n${req.prevContext}` : '',
    `Glossary — use these EXACT target terms:\n${glossaryLines(req)}`,
    g.doNotTranslate.length ? `Do NOT translate (keep verbatim): ${g.doNotTranslate.join(', ')}` : '',
    g.entities.length
      ? `Named entities — render consistently as:\n${g.entities
          .map((e) => `- "${e.name}" -> "${e.render ?? e.name}"`)
          .join('\n')}`
      : '',
    'Preserve numbers, dates, %, currency, citation markers ([12], (Author, 2020)) and reference labels (Figure 4, Table 2) verbatim.',
    g.styleRules.length ? `Style: ${g.styleRules.join('; ')}` : '',
    `\nSource text:\n"""\n${req.sourceText}\n"""`,
    '\nOutput only the translated text.',
  ]
    .filter(Boolean)
    .join('\n');
  return { system, user };
}

export function buildPostEditPrompt(
  req: TranslateRequest,
  draft: string,
): { system: string; user: string } {
  const tgt = langName(req.targetLanguage);
  const system =
    `You are a senior native-language editor of ${tgt}. Improve the translated text so it reads ` +
    `naturally, fluently, and professionally in ${tgt} while preserving the EXACT meaning of the source. ` +
    `Do not add or remove content. Enforce the glossary. Preserve numbers, references, citations, named ` +
    `entities, and formatting markers. Keep the ${req.tone} register. Output ONLY the edited text.`;
  const user = [
    `Source (English):\n"""\n${req.sourceText}\n"""`,
    `Draft translation to improve:\n"""\n${draft}\n"""`,
    `Glossary (must appear exactly):\n${glossaryLines(req)}`,
    req.guide.doNotTranslate.length
      ? `Do NOT translate (keep verbatim): ${req.guide.doNotTranslate.join(', ')}`
      : '',
    `\nReturn only the improved ${tgt} text.`,
  ]
    .filter(Boolean)
    .join('\n');
  return { system, user };
}
