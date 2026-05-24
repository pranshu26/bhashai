// The 12 primary target languages + English source. Script ranges drive the QA
// untranslated/wrong-script checks. Extensible: add an entry to support a new language.

export interface LanguageInfo {
  code: string;
  name: string;
  nativeName: string;
  script: string;
  /** Inclusive Unicode code-point ranges for the script. */
  scriptRanges: ReadonlyArray<readonly [number, number]>;
  rtl: boolean;
}

const DEVANAGARI: ReadonlyArray<readonly [number, number]> = [[0x0900, 0x097f], [0xa8e0, 0xa8ff]];
const BENGALI_ASSAMESE: ReadonlyArray<readonly [number, number]> = [[0x0980, 0x09ff]];
const ARABIC_URDU: ReadonlyArray<readonly [number, number]> = [[0x0600, 0x06ff], [0x0750, 0x077f], [0xfb50, 0xfdff], [0xfe70, 0xfeff]];

export const LANGUAGES: Record<string, LanguageInfo> = {
  en: { code: 'en', name: 'English', nativeName: 'English', script: 'Latin', scriptRanges: [[0x0041, 0x024f]], rtl: false },
  hi: { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', script: 'Devanagari', scriptRanges: DEVANAGARI, rtl: false },
  mr: { code: 'mr', name: 'Marathi', nativeName: 'मराठी', script: 'Devanagari', scriptRanges: DEVANAGARI, rtl: false },
  pa: { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', script: 'Gurmukhi', scriptRanges: [[0x0a00, 0x0a7f]], rtl: false },
  bn: { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', script: 'Bengali', scriptRanges: BENGALI_ASSAMESE, rtl: false },
  gu: { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', script: 'Gujarati', scriptRanges: [[0x0a80, 0x0aff]], rtl: false },
  ta: { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', script: 'Tamil', scriptRanges: [[0x0b80, 0x0bff]], rtl: false },
  te: { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', script: 'Telugu', scriptRanges: [[0x0c00, 0x0c7f]], rtl: false },
  kn: { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', script: 'Kannada', scriptRanges: [[0x0c80, 0x0cff]], rtl: false },
  or: { code: 'or', name: 'Odia', nativeName: 'ଓଡ଼ିଆ', script: 'Odia', scriptRanges: [[0x0b00, 0x0b7f]], rtl: false },
  ur: { code: 'ur', name: 'Urdu', nativeName: 'اردو', script: 'Arabic', scriptRanges: ARABIC_URDU, rtl: true },
  as: { code: 'as', name: 'Assamese', nativeName: 'অসমীয়া', script: 'Bengali-Assamese', scriptRanges: BENGALI_ASSAMESE, rtl: false },
  ml: { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം', script: 'Malayalam', scriptRanges: [[0x0d00, 0x0d7f]], rtl: false },
};

export const SUPPORTED_TARGET_LANGUAGES = Object.keys(LANGUAGES).filter((c) => c !== 'en');

export function getLanguage(code: string): LanguageInfo | undefined {
  return LANGUAGES[code];
}

export function isSupportedTarget(code: string): boolean {
  return code !== 'en' && code in LANGUAGES;
}

function inRanges(cp: number, ranges: ReadonlyArray<readonly [number, number]>): boolean {
  return ranges.some(([lo, hi]) => cp >= lo && cp <= hi);
}

/**
 * Fraction of "letter-like" characters that belong to the language's script.
 * Ignores whitespace, digits, and common punctuation so that numbers/symbols
 * present in any language don't skew the ratio. Returns 1 for empty input.
 */
export function scriptRatio(text: string, code: string): number {
  const lang = LANGUAGES[code];
  if (!lang) return 0;
  let total = 0;
  let inScript = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0)!;
    // skip whitespace, ASCII digits, and punctuation/symbols
    if (/\s/.test(ch)) continue;
    if (cp >= 0x30 && cp <= 0x39) continue;
    if (cp < 0x41) continue; // ASCII punctuation/symbols below 'A'
    if (cp >= 0x2000 && cp <= 0x206f) continue; // general punctuation
    total++;
    if (inRanges(cp, lang.scriptRanges)) inScript++;
  }
  return total === 0 ? 1 : inScript / total;
}

/** Fraction of letter-like chars that are Latin (used to detect untranslated English). */
export function latinRatio(text: string): number {
  return scriptRatio(text, 'en');
}
