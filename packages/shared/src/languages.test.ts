import { describe, it, expect } from 'vitest';
import { scriptRatio, latinRatio, isSupportedTarget, SUPPORTED_TARGET_LANGUAGES } from './languages';

describe('language script matrix', () => {
  it('lists the 12 primary target languages, excluding English', () => {
    expect(SUPPORTED_TARGET_LANGUAGES).toHaveLength(12);
    expect(SUPPORTED_TARGET_LANGUAGES).not.toContain('en');
    expect(isSupportedTarget('hi')).toBe(true);
    expect(isSupportedTarget('en')).toBe(false);
    expect(isSupportedTarget('xx')).toBe(false);
  });

  it('detects pure Hindi/Devanagari as in-script and not Latin', () => {
    const hindi = 'यह एक वाक्य है।';
    expect(scriptRatio(hindi, 'hi')).toBeGreaterThan(0.95);
    expect(latinRatio(hindi)).toBeLessThan(0.05);
  });

  it('flags untranslated English left in a Hindi target', () => {
    const mixed = 'यह एक untranslated sentence है।';
    expect(latinRatio(mixed)).toBeGreaterThan(0.3); // significant Latin => untranslated
  });

  it('ignores digits and punctuation when scoring script', () => {
    const withNumbers = 'मूल्य 1234 रुपये (50%) है।';
    expect(scriptRatio(withNumbers, 'hi')).toBeGreaterThan(0.95);
  });

  it('recognizes each script as its own', () => {
    expect(scriptRatio('বাংলা', 'bn')).toBe(1);
    expect(scriptRatio('தமிழ்', 'ta')).toBe(1);
    expect(scriptRatio('اردو', 'ur')).toBe(1);
    expect(scriptRatio('ಕನ್ನಡ', 'kn')).toBe(1);
  });
});
