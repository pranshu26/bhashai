import type { EngineKind } from '@bhashai/shared';

// Default ranking: Indian-language specialist first, then LLM (with post-edit), then cloud,
// then Mock as the offline fallback. Per-language overrides slot in here as we measure quality.
const DEFAULT_ORDER: EngineKind[] = [
  'INDICTRANS2',
  'LLM',
  'AMAZON_TRANSLATE',
  'GOOGLE_ADVANCED',
  'MOCK',
];

const PER_LANGUAGE: Partial<Record<string, EngineKind[]>> = {
  // Odia/Assamese aren't on Amazon — prefer specialist/LLM explicitly.
  or: ['INDICTRANS2', 'LLM', 'MOCK'],
  as: ['INDICTRANS2', 'LLM', 'MOCK'],
};

export function preferenceOrder(targetLanguage: string): EngineKind[] {
  return PER_LANGUAGE[targetLanguage] ?? DEFAULT_ORDER;
}
