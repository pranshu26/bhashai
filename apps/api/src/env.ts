import { resolve } from 'node:path';
import * as dotenv from 'dotenv';
import { z } from 'zod';

// Load the monorepo-root .env for dev; in containers env comes from the environment (no-op).
dotenv.config({ path: resolve(__dirname, '../../../.env') });

const schema = z.object({
  PORT: z.coerce.number().default(3001),
  DATABASE_URL: z.string(),
  REDIS_URL: z.string().default('redis://localhost:6379'),
  JWT_SECRET: z.string().min(8).default('dev-secret-change-me-please'),
  JWT_EXPIRES_IN: z.string().default('7d'),
  STORAGE_DRIVER: z.enum(['local', 's3']).default('local'),
  AWS_REGION: z.string().default('ap-south-1'),
  AWS_ACCESS_KEY_ID: z.string().optional(),
  AWS_SECRET_ACCESS_KEY: z.string().optional(),
  S3_BUCKET_RAW: z.string().default('bhashai-raw-dev'),
  S3_BUCKET_PROCESSED: z.string().default('bhashai-processed-dev'),
  LOCAL_STORAGE_DIR: z.string().default(resolve(__dirname, '../../../.data')),
  MAX_UPLOAD_MB: z.coerce.number().default(100),
  PARSER_SERVICE_URL: z.string().default('http://localhost:8000'),
});

export const env = schema.parse(process.env);
export type Env = typeof env;
