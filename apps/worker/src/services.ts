import { join } from 'node:path';
import { createStorage } from '@bhashai/storage';
import { buildEngines } from '@bhashai/engines';
import { prisma } from '@bhashai/db';
import { request, Agent } from 'undici';
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

// The PDF path makes ONE long synchronous call to the parser (/translate-pdf) that can run for
// minutes on large docs. Use undici directly with header/body timeouts DISABLED so the global
// fetch's default 300s headersTimeout can never abort a long translation mid-flight again.
const parserAgent = new Agent({ headersTimeout: 0, bodyTimeout: 0 });

async function postJson(path: string, body: unknown): Promise<unknown> {
  const res = await request(env.PARSER_SERVICE_URL.replace(/\/$/, '') + path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    dispatcher: parserAgent,
  });
  if (res.statusCode < 200 || res.statusCode >= 300) {
    throw new Error(`parser-service ${path} ${res.statusCode}: ${await res.body.text()}`);
  }
  return res.body.json();
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
  failedBlocks: number;
  failedPageNumbers: number[];
}

export const parserAnalyze = (inPath: string) =>
  postJson('/analyze', { in_path: inPath }) as Promise<PdfAnalysis>;

export const parserTranslatePdf = (inPath: string, outPath: string, target: string, pages = '') =>
  postJson('/translate-pdf', { in_path: inPath, out_path: outPath, target, pages }) as Promise<PdfReport>;

export interface DocxReport {
  blocksTranslated: number;
  failedBlocks: number;
  failedPages: number;
}
export const parserTranslateDocx = (inPath: string, outPath: string, target: string) =>
  postJson('/translate-docx', { in_path: inPath, out_path: outPath, target }) as Promise<DocxReport>;
