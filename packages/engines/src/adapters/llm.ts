import type { TranslateRequest, TranslateResult, TranslationEngine } from '../types';
import { buildTranslatePrompt, buildPostEditPrompt, TRANSLATE_PROMPT_VERSION, POSTEDIT_PROMPT_VERSION } from '../prompts';
import { type LlmProvider, estimateCostMicroUsd } from '../llm/provider';

export class LlmEngine implements TranslationEngine {
  readonly kind = 'LLM' as const;

  constructor(private readonly provider: LlmProvider | null) {}

  supports(): boolean {
    return true; // LLM can attempt any language pair (quality varies; QA gates it)
  }
  isEnabled(): boolean {
    return this.provider !== null;
  }

  async translate(req: TranslateRequest): Promise<TranslateResult> {
    if (!this.provider) throw new Error('LLM engine has no provider configured');
    const start = Date.now();
    const { system, user } = buildTranslatePrompt(req);
    const out = await this.provider.complete({ system, user }, { temperature: 0.2 });
    return {
      text: out.text.trim(),
      raw: out.text,
      engine: this.kind,
      promptVersion: TRANSLATE_PROMPT_VERSION,
      latencyMs: Date.now() - start,
      costMicroUsd: estimateCostMicroUsd(out.inputTokens, out.outputTokens),
    };
  }

  /** Post-edit pass: improve fluency of a draft without changing meaning. */
  async postEdit(req: TranslateRequest, draft: string): Promise<TranslateResult> {
    if (!this.provider) throw new Error('LLM engine has no provider configured');
    const start = Date.now();
    const { system, user } = buildPostEditPrompt(req, draft);
    const out = await this.provider.complete({ system, user }, { temperature: 0.3 });
    return {
      text: out.text.trim(),
      raw: out.text,
      engine: this.kind,
      promptVersion: POSTEDIT_PROMPT_VERSION,
      latencyMs: Date.now() - start,
      costMicroUsd: estimateCostMicroUsd(out.inputTokens, out.outputTokens),
    };
  }
}
