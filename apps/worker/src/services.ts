import { join } from 'node:path';
import { createStorage } from '@bhashai/storage';
import { buildEngines } from '@bhashai/engines';
import { prisma } from '@bhashai/db';
import { env } from './env';

export { prisma };

export const storage = createStorage(
  env.STORAGE_DRIVER === 's3'
    ? {
        driver: 's3',
        s3: {
          region: env.AWS_REGION,
          rawBucket: env.S3_BUCKET_RAW,
          processedBucket: env.S3_BUCKET_PROCESSED,
          accessKeyId: env.AWS_ACCESS_KEY_ID,
          secretAccessKey: env.AWS_SECRET_ACCESS_KEY,
        },
      }
    : { driver: 'local', local: { rootDir: env.LOCAL_STORAGE_DIR } },
);

export const { router, llm } = buildEngines(env);

/** Absolute path inside the local store (PDF path shares the filesystem with parser-service). */
export const localPath = (store: 'raw' | 'processed', key: string) =>
  join(env.LOCAL_STORAGE_DIR, store, key);

async function postJson(path: string, body: unknown): Promise<unknown> {
  const res = await fetch(env.PARSER_SERVICE_URL.replace(/\/$/, '') + path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`parser-service ${path} ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface PdfAnalysis {
  pageCount: number;
  textPages: number;
  imagePages: number;
  totalBlocks: number;
}
export interface PdfReport {
  pagesProcessed: number;
  blocksTranslated: number;
  overflowBlocks: number;
  imageTextPages: number;
  failedPages: number;
}

export const parserAnalyze = (inPath: string) =>
  postJson('/analyze', { in_path: inPath }) as Promise<PdfAnalysis>;

export const parserTranslatePdf = (inPath: string, outPath: string, target: string, pages = '') =>
  postJson('/translate-pdf', { in_path: inPath, out_path: outPath, target, pages }) as Promise<PdfReport>;
