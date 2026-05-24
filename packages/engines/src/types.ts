import type { TranslationGuide, Tone, EngineKind } from '@bhashai/shared';

export interface TranslateRequest {
  sourceText: string;
  sourceLanguage: string;
  targetLanguage: string;
  guide: TranslationGuide;
  tone: Tone;
  prevContext?: string;
  promptVersion?: string;
}

export interface TranslateResult {
  text: string;
  raw: string;
  engine: EngineKind;
  promptVersion?: string;
  latencyMs: number;
  costMicroUsd: number;
  warnings?: string[];
}

export interface TranslationEngine {
  readonly kind: EngineKind;
  supports(src: string, tgt: string): boolean;
  isEnabled(): boolean;
  translate(req: TranslateRequest): Promise<TranslateResult>;
}

/** One engine attempt (success or failure) — persisted as TranslationEngineRun by the worker. */
export interface EngineAttempt {
  engine: EngineKind;
  success: boolean;
  promptVersion?: string;
  latencyMs: number;
  costMicroUsd: number;
  rawOutput?: string;
  errorMessage?: string;
}

export interface RouterOutcome {
  result: TranslateResult;
  attempts: EngineAttempt[];
}
