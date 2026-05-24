// String-union enums shared across services. The Prisma schema mirrors these values exactly,
// so DB enum strings and TS unions are interchangeable.

export const USER_ROLES = ['USER', 'ADMIN', 'REVIEWER'] as const;
export type UserRole = (typeof USER_ROLES)[number];

export const JOB_STATUSES = [
  'PENDING', 'UPLOADED', 'EXTRACTING', 'ANALYZING', 'CHUNKING',
  'TRANSLATING', 'POST_EDITING', 'QA', 'RECONSTRUCTING', 'EXPORTING',
  'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED',
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export const JOB_STAGES = [
  'CREATED', 'UPLOAD', 'EXTRACT', 'ANALYZE', 'CHUNK', 'TRANSLATE',
  'POST_EDIT', 'QA', 'RECONSTRUCT', 'EXPORT', 'DONE',
] as const;
export type JobStage = (typeof JOB_STAGES)[number];

export const CHUNK_STATUSES = [
  'PENDING', 'TRANSLATING', 'TRANSLATED', 'POST_EDITING', 'POST_EDITED',
  'QA_PENDING', 'QA_PASSED', 'QA_FLAGGED', 'FAILED', 'APPROVED',
] as const;
export type ChunkStatus = (typeof CHUNK_STATUSES)[number];

export const DOC_TYPES = ['TXT', 'DOCX', 'PDF_TEXT', 'PDF_SCANNED', 'PDF_MIXED'] as const;
export type DocType = (typeof DOC_TYPES)[number];

export const OUTPUT_MODES = ['REFLOWED', 'LAYOUT_PRESERVED', 'BILINGUAL'] as const;
export type OutputMode = (typeof OUTPUT_MODES)[number];

export const TONES = [
  'FORMAL', 'INFORMAL', 'EDUCATIONAL', 'CONVERSATIONAL',
  'TECHNICAL', 'LITERARY', 'GOVERNMENT', 'ACADEMIC',
] as const;
export type Tone = (typeof TONES)[number];

export const PRODUCT_MODES = [
  'SHORT_TEXT', 'DOCUMENT', 'THESIS', 'CHAPTERWISE', 'BILINGUAL',
  'GLOSSARY_CALIBRATED', 'HUMAN_REVIEW',
] as const;
export type ProductMode = (typeof PRODUCT_MODES)[number];

export const ASSET_TYPES = [
  'IMAGE', 'GRAPH', 'DIAGRAM', 'TABLE', 'FOOTNOTE', 'CAPTION',
  'EQUATION', 'HEADER', 'FOOTER', 'PAGE_NUMBER', 'CHART',
] as const;
export type AssetType = (typeof ASSET_TYPES)[number];

export const ENGINE_KINDS = [
  'MOCK', 'INDICTRANS2', 'AMAZON_TRANSLATE', 'GOOGLE_ADVANCED',
  'LLM', 'GLOSSARY_RULE', 'TRANSLATION_MEMORY',
] as const;
export type EngineKind = (typeof ENGINE_KINDS)[number];

export const QA_SEVERITIES = ['INFO', 'WARNING', 'ERROR'] as const;
export type QaSeverity = (typeof QA_SEVERITIES)[number];

export const QA_FLAG_TYPES = [
  'missing_meaning', 'added_meaning', 'wrong_translation', 'untranslated', 'wrong_script',
  'number_mismatch', 'length_anomaly', 'glossary_violation', 'citation_mismatch',
  'reference_mismatch', 'entity_mismatch', 'table_mismatch', 'tone_issue',
  'layout_warning', 'ocr_warning', 'image_text_warning', 'back_translation_drift',
] as const;
export type QaFlagType = (typeof QA_FLAG_TYPES)[number];

export interface QaFlag {
  type: QaFlagType;
  severity: QaSeverity;
  detail: string;
  sourceSnippet?: string;
  targetSnippet?: string;
}

// Canonical BullMQ queue names.
export const QUEUE = {
  EXTRACT: 'document.extract',
  ANALYZE: 'document.analyze',
  CHUNK: 'document.chunk',
  TRANSLATE: 'translation.chunk',
  POSTEDIT: 'translation.postedit',
  QA: 'translation.qa',
  RECONSTRUCT: 'document.reconstruct',
  EXPORT: 'document.export',
  CLEANUP: 'cleanup',
} as const;
export type QueueName = (typeof QUEUE)[keyof typeof QUEUE];
export const ALL_QUEUES = Object.values(QUEUE) as QueueName[];
