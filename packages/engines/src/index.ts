import { MockEngine } from './adapters/mock';
import { LlmEngine } from './adapters/llm';
import { AmazonTranslateEngine } from './adapters/amazon';
import { IndicTrans2Engine } from './adapters/indictrans';
import { createLlmProvider } from './llm/provider';
import { EngineRouter } from './router';
import type { TranslationEngine } from './types';

export * from './types';
export * from './router';
export * from './prompts';
export { MockEngine } from './adapters/mock';
export { LlmEngine } from './adapters/llm';
export { AmazonTranslateEngine } from './adapters/amazon';
export { IndicTrans2Engine } from './adapters/indictrans';
export { preferenceOrder } from './preference-matrix';
export type { LlmProvider } from './llm/provider';

export interface EnginesEnv {
  DEFAULT_TRANSLATION_ENGINE?: string;
  LLM_PROVIDER?: string;
  LLM_MODEL?: string;
  ANTHROPIC_API_KEY?: string;
  OPENAI_API_KEY?: string;
  AWS_TRANSLATE_ENABLED?: string;
  AWS_REGION?: string;
  AWS_ACCESS_KEY_ID?: string;
  AWS_SECRET_ACCESS_KEY?: string;
  INDICTRANS_SERVICE_URL?: string;
}

export interface BuiltEngines {
  engines: TranslationEngine[];
  router: EngineRouter;
  /** The LLM engine (for the post-edit stage); disabled if no provider key. */
  llm: LlmEngine;
}

/** Construct the engine registry + router from environment config. */
export function buildEngines(env: EnginesEnv): BuiltEngines {
  const provider =
    env.LLM_PROVIDER === 'anthropic' && env.ANTHROPIC_API_KEY
      ? createLlmProvider({ provider: 'anthropic', apiKey: env.ANTHROPIC_API_KEY, model: env.LLM_MODEL })
      : env.LLM_PROVIDER === 'openai' && env.OPENAI_API_KEY
        ? createLlmProvider({ provider: 'openai', apiKey: env.OPENAI_API_KEY, model: env.LLM_MODEL })
        : env.ANTHROPIC_API_KEY
          ? createLlmProvider({ provider: 'anthropic', apiKey: env.ANTHROPIC_API_KEY, model: env.LLM_MODEL })
          : env.OPENAI_API_KEY
            ? createLlmProvider({ provider: 'openai', apiKey: env.OPENAI_API_KEY, model: env.LLM_MODEL })
            : null;

  const llm = new LlmEngine(provider);
  const engines: TranslationEngine[] = [
    new IndicTrans2Engine({ url: env.INDICTRANS_SERVICE_URL }),
    llm,
    new AmazonTranslateEngine({
      enabled: env.AWS_TRANSLATE_ENABLED === 'true',
      region: env.AWS_REGION ?? 'ap-south-1',
      accessKeyId: env.AWS_ACCESS_KEY_ID,
      secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
    }),
    new MockEngine(),
  ];

  return { engines, router: new EngineRouter(engines), llm };
}
