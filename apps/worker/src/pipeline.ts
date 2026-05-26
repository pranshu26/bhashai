import { statSync, readFileSync } from 'node:fs';
import { detectDocType, extractDocument, chunkDocument } from '@bhashai/parsing';
import { StorageKeys } from '@bhashai/storage';
import { emptyGuide, type Tone, type EngineKind } from '@bhashai/shared';
import { env } from './env';
import {
  prisma,
  storage,
  router,
  localPath,
  parserAnalyze,
  parserTranslatePdf,
} from './services';

type JobRow = NonNullable<Awaited<ReturnType<typeof prisma.translationJob.findUnique>>>;

const setJob = (id: string, data: Record<string, unknown>) =>
  prisma.translationJob.update({ where: { id }, data: data as never });

const event = (jobId: string, stage: string, ev: string, message?: string) =>
  prisma.jobEventLog.create({ data: { jobId, stage: stage as never, event: ev, message } });

export async function processJob(jobId: string): Promise<void> {
  const job = await prisma.translationJob.findUnique({ where: { id: jobId } });
  if (!job) return;
  if (!job.originalFileUrl) throw new Error('job has no uploaded file');

  try {
    const docType = detectDocType(job.originalFileName ?? '');
    // clear any stale error from a prior failed attempt (BullMQ retries re-run this)
    await setJob(jobId, { docType, status: 'EXTRACTING', currentStage: 'EXTRACT', progressPercentage: 5, errorMessage: null });
    await event(jobId, 'EXTRACT', 'extract.completed', `docType=${docType}`);

    if (docType.startsWith('PDF')) {
      await processPdf(job);
    } else {
      await processText(job, docType);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await setJob(jobId, { status: 'FAILED', errorMessage: message });
    await event(jobId, 'DONE', 'job.failed', message);
    throw err;
  }
}

async function processPdf(job: JobRow): Promise<void> {
  const inPath = localPath('raw', job.originalFileUrl!);
  const analysis = await parserAnalyze(inPath);
  await setJob(job.id, {
    status: 'TRANSLATING',
    currentStage: 'TRANSLATE',
    totalChunks: analysis.totalBlocks,
    progressPercentage: 10,
  });
  await event(
    job.id,
    'TRANSLATE',
    'chunk.translate.started',
    `${analysis.pageCount} pages (${analysis.textPages} text, ${analysis.imagePages} image)`,
  );

  const exportKey = StorageKeys.exportFile(job.id, job.outputMode, 'pdf');
  const outPath = localPath('processed', exportKey);
  const report = await parserTranslatePdf(inPath, outPath, job.targetLanguage);

  // For S3, push the rendered file up (local already wrote it to the processed store path).
  if (storage.kind === 's3') {
    await storage.processed.put(exportKey, readFileSync(outPath), 'application/pdf');
  }

  await setJob(job.id, { status: 'EXPORTING', currentStage: 'EXPORT', progressPercentage: 95, completedChunks: report.blocksTranslated });
  await prisma.exportedFile.create({
    data: {
      jobId: job.id,
      outputMode: job.outputMode,
      format: 'pdf',
      fileUrl: exportKey,
      sizeBytes: statSync(outPath).size,
      isPartial: report.failedPages > 0,
    },
  });

  const partial = report.failedPages > 0;
  const pagesList = report.failedPageNumbers?.length ? ` (pages ${report.failedPageNumbers.join(', ')})` : '';
  const failNote = partial
    ? `${report.failedBlocks} text block(s) across ${report.failedPages} page(s) kept the original English${pagesList} — usually a transient rate limit. Re-running the translation often clears it.`
    : null;
  await setJob(job.id, {
    status: partial ? 'PARTIALLY_COMPLETED' : 'COMPLETED',
    currentStage: 'DONE',
    progressPercentage: 100,
    translatedFileUrl: exportKey,
    totalChunks: report.blocksTranslated,
    completedChunks: report.blocksTranslated - report.failedBlocks,
    failedChunks: report.failedBlocks,
    errorMessage: failNote,
    completedAt: new Date(),
  });
  await event(
    job.id,
    'EXPORT',
    partial ? 'job.partially_completed' : 'job.completed',
    `blocks=${report.blocksTranslated} overflow=${report.overflowBlocks} imageTextPages=${report.imageTextPages} failedPages=${report.failedPages} failedBlocks=${report.failedBlocks}`,
  );
}

async function processText(job: JobRow, docType: string): Promise<void> {
  const bytes = await storage.raw.get(job.originalFileUrl!);
  const tree = await extractDocument({ buffer: bytes, filename: job.originalFileName ?? 'doc.txt' });
  const chunks = chunkDocument(tree, { maxChars: 1800 });
  await setJob(job.id, { status: 'TRANSLATING', currentStage: 'TRANSLATE', totalChunks: chunks.length, progressPercentage: 20 });

  const guide = emptyGuide(job.targetLanguage, job.tone as Tone);
  const outParts: string[] = [];
  let done = 0;
  let failed = 0;

  for (const c of chunks) {
    const row = await prisma.translationChunk.create({
      data: {
        jobId: job.id,
        chapterIndex: c.chapterIndex,
        sectionTitle: c.sectionTitle,
        chunkIndex: c.chunkIndex,
        sourceText: c.sourceText,
        prevContext: c.prevContext,
        status: 'TRANSLATING',
      },
    });
    try {
      const outcome = await router.translate(
        {
          sourceText: c.sourceText,
          sourceLanguage: job.sourceLanguage,
          targetLanguage: job.targetLanguage,
          guide,
          tone: job.tone as Tone,
          prevContext: c.prevContext,
        },
        { defaultEngine: env.DEFAULT_TRANSLATION_ENGINE as EngineKind },
      );
      for (const a of outcome.attempts) {
        await prisma.translationEngineRun.create({
          data: {
            jobId: job.id,
            chunkId: row.id,
            engine: a.engine,
            success: a.success,
            latencyMs: a.latencyMs,
            costMicroUsd: a.costMicroUsd,
            errorMessage: a.errorMessage,
            rawOutput: a.rawOutput,
          },
        });
      }
      await prisma.translationChunk.update({
        where: { id: row.id },
        data: { translatedText: outcome.result.text, status: 'TRANSLATED', engineUsed: outcome.result.engine },
      });
      outParts.push(outcome.result.text);
      done++;
    } catch (err) {
      failed++;
      outParts.push(c.sourceText); // keep source on failure, never drop content
      await prisma.translationChunk.update({
        where: { id: row.id },
        data: { status: 'FAILED', errorMessage: err instanceof Error ? err.message : String(err) },
      });
    }
    await setJob(job.id, {
      completedChunks: done,
      failedChunks: failed,
      progressPercentage: 20 + Math.round((70 * (done + failed)) / chunks.length),
    });
  }

  const exportKey = StorageKeys.exportFile(job.id, job.outputMode, 'txt');
  await storage.processed.put(exportKey, outParts.join('\n\n'), 'text/plain; charset=utf-8');
  await prisma.exportedFile.create({
    data: { jobId: job.id, outputMode: job.outputMode, format: 'txt', fileUrl: exportKey, isPartial: failed > 0 },
  });
  await setJob(job.id, {
    status: failed > 0 ? 'PARTIALLY_COMPLETED' : 'COMPLETED',
    currentStage: 'DONE',
    progressPercentage: 100,
    translatedFileUrl: exportKey,
    completedAt: new Date(),
  });
  await event(job.id, 'EXPORT', failed > 0 ? 'job.partially_completed' : 'job.completed', `docType=${docType} chunks=${chunks.length} failed=${failed}`);
}
