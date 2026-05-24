import type { EngineKind } from '@bhashai/shared';
import type { EngineAttempt, RouterOutcome, TranslateRequest, TranslateResult, TranslationEngine } from './types';
import { preferenceOrder } from './preference-matrix';

export class EngineRouterError extends Error {
  constructor(
    message: string,
    readonly attempts: EngineAttempt[],
  ) {
    super(message);
    this.name = 'EngineRouterError';
  }
}

export interface RouteOptions {
  /** Force this engine to the front of the chain if it's enabled + supports the pair. */
  defaultEngine?: EngineKind;
}

export class EngineRouter {
  constructor(private readonly engines: TranslationEngine[]) {}

  byKind(kind: EngineKind): TranslationEngine | undefined {
    return this.engines.find((e) => e.kind === kind);
  }

  /** Ordered [primary, ...fallbacks] of enabled engines that support the pair. */
  selectChain(src: string, tgt: string, opts: RouteOptions = {}): TranslationEngine[] {
    const order = preferenceOrder(tgt);
    const rank = (k: EngineKind) => {
      const i = order.indexOf(k);
      return i === -1 ? order.length : i;
    };
    let chain = this.engines
      .filter((e) => e.isEnabled() && e.supports(src, tgt))
      .sort((a, b) => rank(a.kind) - rank(b.kind));

    if (opts.defaultEngine) {
      const forced = chain.find((e) => e.kind === opts.defaultEngine);
      if (forced) chain = [forced, ...chain.filter((e) => e !== forced)];
    }
    return chain;
  }

  /** Run the chain until one engine succeeds; record every attempt. */
  async translate(req: TranslateRequest, opts: RouteOptions = {}): Promise<RouterOutcome> {
    const chain = this.selectChain(req.sourceLanguage, req.targetLanguage, opts);
    if (chain.length === 0) {
      throw new EngineRouterError(
        `No enabled engine supports ${req.sourceLanguage}->${req.targetLanguage}`,
        [],
      );
    }
    const attempts: EngineAttempt[] = [];
    let lastError = '';
    for (const engine of chain) {
      const start = Date.now();
      try {
        const result = await engine.translate(req);
        if (!result.text || result.text.trim() === '') throw new Error('engine returned empty output');
        attempts.push({
          engine: engine.kind,
          success: true,
          promptVersion: result.promptVersion,
          latencyMs: result.latencyMs,
          costMicroUsd: result.costMicroUsd,
          rawOutput: result.raw,
        });
        return { result, attempts };
      } catch (err) {
        lastError = err instanceof Error ? err.message : String(err);
        attempts.push({
          engine: engine.kind,
          success: false,
          latencyMs: Date.now() - start,
          costMicroUsd: 0,
          errorMessage: lastError,
        });
      }
    }
    throw new EngineRouterError(
      `All ${chain.length} engine(s) failed for ${req.sourceLanguage}->${req.targetLanguage}: ${lastError}`,
      attempts,
    );
  }

  /** Comparison mode: run every enabled engine that supports the pair, return all outputs. */
  async compare(req: TranslateRequest): Promise<TranslateResult[]> {
    const chain = this.selectChain(req.sourceLanguage, req.targetLanguage);
    const results: TranslateResult[] = [];
    for (const engine of chain) {
      try {
        results.push(await engine.translate(req));
      } catch {
        /* skip failures in comparison */
      }
    }
    return results;
  }
}
