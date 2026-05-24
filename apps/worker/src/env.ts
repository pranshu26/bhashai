import { resolve } from 'node:path';
import * as dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config({ path: resolve(__dirname, '../../../.env') });

const schema = z.object({
  DATABASE_URL: z.string(),
  REDIS_URL: z.string().default('redis://localhost:6379'),
  STORAGE_DRIVER: z.enum(['local', 's3']).default('local'),
  LOCAL_STORAGE_DIR: z.string().default(resolve(__dirname, '../../../.data')),
  AWS_REGION: z.string().default('ap-south-1'),
  AWS_ACCESS_KEY_ID: z.string().optional(),
  AWS_SECRET_ACCESS_KEY: z.string().optional(),
  S3_BUCKET_RAW: z.string().default('bhashai-raw-dev'),
  S3_BUCKET_PROCESSED: z.string().default('bhashai-processed-dev'),
  PARSER_SERVICE_URL: z.string().default('http://localhost:8000'),
  INDICTRANS_SERVICE_URL: z.string().optional(),
  LLM_PROVIDER: z.string().optional(),
  LLM_MODEL: z.string().optional(),
  ANTHROPIC_API_KEY: z.string().optional(),
  OPENAI_API_KEY: z.string().optional(),
  AWS_TRANSLATE_ENABLED: z.string().optional(),
  DEFAULT_TRANSLATION_ENGINE: z.string().default('INDICTRANS2'),
  WORKER_CONCURRENCY: z.coerce.number().default(2),
});

export const env = schema.parse(process.env);
