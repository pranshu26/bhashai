import { z } from 'zod';
import { TONES, OUTPUT_MODES, PRODUCT_MODES } from './enums';
import { SUPPORTED_TARGET_LANGUAGES } from './languages';

export const signupSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(200),
  name: z.string().min(1).max(120).optional(),
});
export type SignupDto = z.infer<typeof signupSchema>;

export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
export type LoginDto = z.infer<typeof loginSchema>;

export const createJobSchema = z.object({
  sourceLanguage: z.literal('en').default('en'),
  targetLanguage: z.enum(SUPPORTED_TARGET_LANGUAGES as [string, ...string[]]),
  tone: z.enum(TONES).default('FORMAL'),
  mode: z.enum(PRODUCT_MODES).default('DOCUMENT'),
  outputMode: z.enum(OUTPUT_MODES).default('REFLOWED'),
  qualityPriority: z.boolean().default(true),
  specialInstructions: z.string().max(4000).optional(),
});
export type CreateJobDto = z.infer<typeof createJobSchema>;

export const shortTextSchema = z.object({
  text: z.string().min(1).max(20000),
  targetLanguage: z.enum(SUPPORTED_TARGET_LANGUAGES as [string, ...string[]]),
  tone: z.enum(TONES).default('FORMAL'),
});
export type ShortTextDto = z.infer<typeof shortTextSchema>;

export const glossaryTermSchema = z.object({
  targetLanguage: z.string(),
  sourceTerm: z.string().min(1),
  targetTerm: z.string().min(1),
  doNotTranslate: z.boolean().default(false),
  caseSensitive: z.boolean().default(false),
  notes: z.string().optional(),
});
export type GlossaryTermDto = z.infer<typeof glossaryTermSchema>;

export const updateChunkSchema = z.object({
  translatedText: z.string(),
  approve: z.boolean().default(true),
});
export type UpdateChunkDto = z.infer<typeof updateChunkSchema>;
