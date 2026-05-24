import { describe, it, expect, vi, afterEach } from 'vitest';
import { emptyGuide } from '@bhashai/shared';
import { EngineRouter, EngineRouterError } from './router';
import { MockEngine } from './adapters/mock';
import { IndicTrans2Engine } from './adapters/indictrans';
import { buildEngines } from './index';
import type { TranslateRequest, TranslateResult, TranslationEngine } from './types';

function makeReq(tgt = 'hi'): TranslateRequest {
  return { sourceText: 'hello world', sourceLanguage: 'en', targetLanguage: tgt, guide: emptyGuide(tgt, 'FORMAL'), tone: 'FORMAL' };
}

class FakeEngine implements TranslationEngine {
  constructor(
    readonly kind: any,
    private readonly behavior: 'ok' | 'throw' | 'empty',
    private readonly enabled = true,
  ) {}
  supports() { return true; }
  isEnabled() { return this.enabled; }
  async translate(): Promise<TranslateResult> {
    if (this.behavior === 'throw') throw new Error(`${this.kind} down`);
    return {
      text: this.behavior === 'empty' ? '' : `${this.kind}-output`,
      raw: '', engine: this.kind, latencyMs: 1, costMicroUsd: 0,
    };
  }
}

afterEach(() => vi.restoreAllMocks());

describe('EngineRouter', () => {
  it('falls back to the next engine when the primary fails, recording every attempt', async () => {
    // LLM ranks before MOCK; make LLM throw so it falls through to MOCK.
    const router = new EngineRouter([new FakeEngine('LLM', 'throw'), new MockEngine()]);
    const out = await router.translate(makeReq());
    expect(out.result.engine).toBe('MOCK');
    expect(out.attempts).toHaveLength(2);
    expect(out.attempts[0]).toMatchObject({ engine: 'LLM', success: false });
    expect(out.attempts[1]).toMatchObject({ engine: 'MOCK', success: true });
  });

  it('treats empty output as a failure and falls through', async () => {
    const router = new EngineRouter([new FakeEngine('LLM', 'empty'), new MockEngine()]);
    const out = await router.translate(makeReq());
    expect(out.result.engine).toBe('MOCK');
  });

  it('throws EngineRouterError with attempts when all engines fail', async () => {
    const router = new EngineRouter([new FakeEngine('LLM', 'throw'), new FakeEngine('AMAZON_TRANSLATE', 'throw')]);
    await expect(router.translate(makeReq())).rejects.toBeInstanceOf(EngineRouterError);
  });

  it('forces a default engine to the front when enabled + supported', async () => {
    const router = new EngineRouter([new FakeEngine('LLM', 'ok'), new MockEngine()]);
    const chain = router.selectChain('en', 'hi', { defaultEngine: 'MOCK' });
    expect(chain[0].kind).toBe('MOCK');
  });

  it('comparison mode runs all enabled supporting engines', async () => {
    const router = new EngineRouter([new FakeEngine('LLM', 'ok'), new MockEngine()]);
    const results = await router.compare(makeReq());
    expect(results.map((r) => r.engine).sort()).toEqual(['LLM', 'MOCK']);
  });
});

describe('buildEngines (env-driven registry)', () => {
  it('with no keys: only Mock is enabled; LLM/Amazon/IndicTrans disabled', () => {
    const { router, llm } = buildEngines({});
    expect(llm.isEnabled()).toBe(false);
    const chain = router.selectChain('en', 'hi');
    expect(chain.map((e) => e.kind)).toEqual(['MOCK']);
  });

  it('enables the LLM engine when an API key is present', () => {
    const { llm } = buildEngines({ LLM_PROVIDER: 'anthropic', ANTHROPIC_API_KEY: 'sk-test' });
    expect(llm.isEnabled()).toBe(true);
  });
});

describe('IndicTrans2Engine contract', () => {
  it('is disabled without a service URL', () => {
    expect(new IndicTrans2Engine({}).isEnabled()).toBe(false);
  });

  it('calls {url}/translate and returns the translation', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ translation: 'नमस्ते दुनिया' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const engine = new IndicTrans2Engine({ url: 'http://indictrans:8001' });
    expect(engine.isEnabled()).toBe(true);
    expect(engine.supports('en', 'hi')).toBe(true);
    const res = await engine.translate(makeReq());
    expect(res.text).toBe('नमस्ते दुनिया');
    expect(res.engine).toBe('INDICTRANS2');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://indictrans:8001/translate');
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({ target: 'hi', source: 'en' });
  });
});
