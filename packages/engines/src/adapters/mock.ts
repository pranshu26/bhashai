import { getLanguage } from '@bhashai/shared';
import type { TranslateRequest, TranslateResult, TranslationEngine } from '../types';

/**
 * Deterministic offline engine for dev/CI. It does NOT really translate, but it produces
 * target-script output while preserving the things the QA layer checks: numbers, glossary
 * target terms, named entities, and do-not-translate terms stay intact; everything else is
 * mapped to in-script pseudo-words. This makes the full pipeline runnable with no API keys
 * and lets QA tests assert pass/fail behavior predictably.
 */
export class MockEngine implements TranslationEngine {
  readonly kind = 'MOCK' as const;

  supports(): boolean {
    return true;
  }
  isEnabled(): boolean {
    return true;
  }

  async translate(req: TranslateRequest): Promise<TranslateResult> {
    const start = Date.now();
    const lang = getLanguage(req.targetLanguage);
    const base = lang ? lang.scriptRanges[0][0] + 0x20 : 0x0920; // letter area of the script block
    const dnt = new Set(req.guide.doNotTranslate.map((t) => t.toLowerCase()));
    const glossary = new Map(req.guide.glossary.map((g) => [g.source.toLowerCase(), g.target]));
    const entities = new Map(
      req.guide.entities.map((e) => [e.name.toLowerCase(), e.render ?? e.name]),
    );

    const out = req.sourceText.replace(/(\s+|[^\s]+)/g, (tok) => {
      if (/^\s+$/.test(tok)) return tok; // keep whitespace
      const lower = tok.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
      if (lower === '') return tok; // pure punctuation
      if (/\d/.test(tok)) return tok; // keep anything with a digit verbatim
      if (dnt.has(lower)) return tok; // do-not-translate verbatim
      const g = glossary.get(lower);
      if (g) return g; // approved glossary target
      const e = entities.get(lower);
      if (e) return e; // named entity render
      return this.toScript(tok, base);
    });

    return {
      text: out,
      raw: out,
      engine: this.kind,
      promptVersion: 'mock.v1',
      latencyMs: Date.now() - start,
      costMicroUsd: 0,
    };
  }

  /** Map an English word to a deterministic in-script pseudo-word of similar length. */
  private toScript(word: string, base: number): string {
    const len = Math.max(2, Math.min(8, word.replace(/[^\p{L}]/gu, '').length));
    let s = '';
    let h = 0;
    for (let i = 0; i < word.length; i++) h = (h * 31 + word.charCodeAt(i)) >>> 0;
    for (let i = 0; i < len; i++) {
      s += String.fromCodePoint(base + ((h + i * 7) % 0x18));
    }
    return s;
  }
}
