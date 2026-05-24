import { SUPPORTED_TARGET_LANGUAGES } from '@bhashai/shared';
import type { TranslateRequest, TranslateResult, TranslationEngine } from '../types';

export interface IndicTransConfig {
  url?: string; // INDICTRANS_SERVICE_URL; engine disabled when unset
}

/**
 * Adapter for the self-hosted IndicTrans2 (AI4Bharat) FastAPI service.
 * Service contract: POST {url}/translate {text, source, target} -> {translation}.
 * The Python service is built in Phase 3; this adapter is contract-tested now.
 */
export class IndicTrans2Engine implements TranslationEngine {
  readonly kind = 'INDICTRANS2' as const;

  constructor(private readonly config: IndicTransConfig) {}

  isEnabled(): boolean {
    return !!this.config.url;
  }
  supports(src: string, tgt: string): boolean {
    // IndicTrans2 covers all 22 scheduled Indian languages (our 12 are a subset).
    return src === 'en' && SUPPORTED_TARGET_LANGUAGES.includes(tgt);
  }

  async translate(req: TranslateRequest): Promise<TranslateResult> {
    const start = Date.now();
    const res = await fetch(`${this.config.url}/translate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        text: req.sourceText,
        source: req.sourceLanguage,
        target: req.targetLanguage,
      }),
    });
    if (!res.ok) throw new Error(`IndicTrans2 ${res.status}: ${await res.text()}`);
    const data = (await res.json()) as { translation: string };
    if (!data.translation) throw new Error('IndicTrans2 returned no translation');
    return {
      text: data.translation,
      raw: data.translation,
      engine: this.kind,
      promptVersion: 'indictrans2',
      latencyMs: Date.now() - start,
      costMicroUsd: 0, // self-hosted compute
    };
  }
}
