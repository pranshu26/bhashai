import { describe, it, expect } from 'vitest';
import { emptyGuide, scriptRatio } from '@bhashai/shared';
import { MockEngine } from './adapters/mock';
import type { TranslateRequest } from './types';

function req(text: string): TranslateRequest {
  const guide = emptyGuide('hi', 'FORMAL');
  guide.glossary = [{ source: 'rupees', target: 'रुपये' }];
  guide.doNotTranslate = ['RTI'];
  guide.entities = [{ name: 'Pranab', render: 'प्रणब' }];
  return { sourceText: text, sourceLanguage: 'en', targetLanguage: 'hi', guide, tone: 'FORMAL' };
}

describe('MockEngine', () => {
  const engine = new MockEngine();

  it('preserves numbers, do-not-translate, glossary targets, and entities', async () => {
    const res = await engine.translate(req('The RTI cost 1947 rupees for Pranab'));
    expect(res.text).toContain('1947'); // number preserved
    expect(res.text).toContain('RTI'); // do-not-translate preserved
    expect(res.text).toContain('रुपये'); // glossary target applied
    expect(res.text).toContain('प्रणब'); // entity render applied
  });

  it('emits target-script text for ordinary words', async () => {
    const res = await engine.translate(req('the methodology chapter describes results'));
    expect(scriptRatio(res.text, 'hi')).toBeGreaterThan(0.8);
  });

  it('is deterministic', async () => {
    const a = await engine.translate(req('reproducible output please'));
    const b = await engine.translate(req('reproducible output please'));
    expect(a.text).toBe(b.text);
    expect(a.costMicroUsd).toBe(0);
    expect(a.engine).toBe('MOCK');
  });
});
