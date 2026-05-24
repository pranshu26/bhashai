import type { Tone } from './enums';

export interface GlossaryPair {
  source: string;
  target: string;
  doNotTranslate?: boolean;
  caseSensitive?: boolean;
}

export interface EntityRender {
  name: string;
  render?: string;
  type?: 'PERSON' | 'ORG' | 'PLACE' | 'SCHEME' | 'LAW' | 'OTHER';
}

/** The job translation guide injected into every chunk translation. See TRANSLATION-QUALITY.md §2. */
export interface TranslationGuide {
  targetLanguage: string;
  tone: Tone;
  domain?: string;
  audience?: string;
  documentSummary?: string;
  styleRules: string[];
  glossary: GlossaryPair[];
  approvedTerms: GlossaryPair[];
  doNotTranslate: string[];
  entities: EntityRender[];
  acronymPolicy?: string;
  unitPolicy?: string;
  citationPolicy?: string;
  pronounPolicy?: string;
  sentenceComplexity?: string;
}

export function emptyGuide(targetLanguage: string, tone: Tone): TranslationGuide {
  return {
    targetLanguage,
    tone,
    styleRules: [],
    glossary: [],
    approvedTerms: [],
    doNotTranslate: [],
    entities: [],
  };
}
