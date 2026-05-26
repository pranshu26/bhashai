import { ForbiddenException, Injectable, NotFoundException, BadRequestException } from '@nestjs/common';
import { QUEUE, type CreateJobDto } from '@bhashai/shared';
import { StorageKeys } from '@bhashai/storage';
import { PrismaService } from '../prisma.service';
import { StorageService } from '../storage.service';
import { QueueService } from '../queue/queue.service';

@Injectable()
export class JobsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly storage: StorageService,
    private readonly queue: QueueService,
  ) {}

  private async event(jobId: string, stage: string, event: string, message?: string) {
    await this.prisma.db.jobEventLog.create({
      data: { jobId, stage: stage as never, event, message },
    });
  }

  private async owned(userId: string, id: string) {
    const job = await this.prisma.db.translationJob.findUnique({ where: { id } });
    if (!job) throw new NotFoundException('job not found');
    if (job.userId !== userId) throw new ForbiddenException('not your job');
    return job;
  }

  async create(userId: string, dto: CreateJobDto) {
    const job = await this.prisma.db.translationJob.create({
      data: {
        userId,
        sourceLanguage: dto.sourceLanguage,
        targetLanguage: dto.targetLanguage,
        tone: dto.tone as never,
        mode: dto.mode,
        outputMode: dto.outputMode as never,
        qualityPriority: dto.qualityPriority,
        specialInstructions: dto.specialInstructions,
      },
    });
    await this.event(job.id, 'CREATED', 'job.created');
    return job;
  }

  list(userId: string) {
    return this.prisma.db.translationJob.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
  }

  get(userId: string, id: string) {
    return this.owned(userId, id);
  }

  async upload(userId: string, id: string, file: Express.Multer.File) {
    const job = await this.owned(userId, id);
    if (!file) throw new BadRequestException('no file');
    const key = StorageKeys.source(job.id, file.originalname);
    await this.storage.storage.raw.put(key, file.buffer, file.mimetype);
    const updated = await this.prisma.db.translationJob.update({
      where: { id: job.id },
      data: { originalFileUrl: key, originalFileName: file.originalname, status: 'UPLOADED', currentStage: 'UPLOAD' },
    });
    await this.event(job.id, 'UPLOAD', 'file.uploaded', `${file.originalname} (${file.size} bytes)`);
    return { id: updated.id, status: updated.status, originalFileName: updated.originalFileName };
  }

  async start(userId: string, id: string) {
    const job = await this.owned(userId, id);
    if (!job.originalFileUrl) throw new BadRequestException('upload a file before starting');
    if (['EXTRACTING', 'ANALYZING', 'CHUNKING', 'TRANSLATING', 'POST_EDITING', 'QA', 'RECONSTRUCTING', 'EXPORTING'].includes(job.status))
      throw new BadRequestException('job already running');
    await this.prisma.db.translationJob.update({
      where: { id: job.id },
      data: { status: 'EXTRACTING', currentStage: 'EXTRACT', progressPercentage: 0, errorMessage: null },
    });
    await this.queue.enqueue(QUEUE.EXTRACT, 'extract', { jobId: job.id });
    await this.event(job.id, 'EXTRACT', 'extract.started');
    return { id: job.id, status: 'EXTRACTING' };
  }

  private static readonly RUNNING = [
    'EXTRACTING', 'ANALYZING', 'CHUNKING', 'TRANSLATING', 'POST_EDITING', 'QA', 'RECONSTRUCTING', 'EXPORTING',
  ];

  async progress(userId: string, id: string) {
    const job = await this.owned(userId, id);
    let { progressPercentage, completedChunks, totalChunks } = job;
    // While a PDF job runs, the parser writes a live progress file next to the export; read it so
    // the bar climbs in real time. Best-effort — any miss falls back to the DB values (no regression).
    if (JobsService.RUNNING.includes(job.status)) {
      try {
        const key = StorageKeys.exportFile(job.id, job.outputMode, 'pdf') + '.progress';
        const raw = await this.storage.storage.processed.get(key);
        const p = JSON.parse(raw.toString());
        if (p && p.total > 0) {
          completedChunks = p.done;
          totalChunks = p.total;
          progressPercentage = Math.min(94, 10 + Math.round((84 * p.done) / p.total));
        }
      } catch {
        /* no progress file (not started / finished) — use DB values */
      }
    }
    return {
      id: job.id,
      status: job.status,
      currentStage: job.currentStage,
      progressPercentage,
      totalChunks,
      completedChunks,
      failedChunks: job.failedChunks,
      errorMessage: job.errorMessage,
      hasOutput: !!job.translatedFileUrl,
    };
  }

  async cancel(userId: string, id: string) {
    await this.owned(userId, id);
    await this.prisma.db.translationJob.update({ where: { id }, data: { status: 'CANCELLED' } });
    await this.event(id, 'DONE', 'job.cancelled');
    return { id, status: 'CANCELLED' };
  }

  async retryFailed(userId: string, id: string) {
    const job = await this.owned(userId, id);
    const failed = await this.prisma.db.translationChunk.findMany({
      where: { jobId: id, status: 'FAILED' },
      select: { id: true },
    });
    for (const c of failed) {
      await this.queue.enqueue(QUEUE.TRANSLATE, 'translate', { jobId: id, chunkId: c.id });
    }
    if (failed.length) {
      await this.prisma.db.translationJob.update({ where: { id }, data: { status: 'TRANSLATING' } });
    }
    return { id: job.id, requeued: failed.length };
  }

  /** Returns either bytes to stream (local) or a presigned URL (s3). */
  async download(userId: string, id: string) {
    const job = await this.owned(userId, id);
    if (job.status !== 'COMPLETED' && job.status !== 'PARTIALLY_COMPLETED')
      throw new BadRequestException('job not finished');
    if (!job.translatedFileUrl) throw new NotFoundException('no output yet');
    const store = this.storage.storage.processed;
    const ext = job.translatedFileUrl.match(/\.([a-z0-9]+)$/i)?.[1]?.toLowerCase() ?? 'pdf';
    const filename = `${(job.originalFileName ?? 'document').replace(/\.[^.]+$/, '')}-${job.targetLanguage}.${ext}`;
    if (store.supportsPresign) {
      const { url } = await store.presignGet(job.translatedFileUrl);
      return { kind: 'url' as const, url };
    }
    const buffer = await store.get(job.translatedFileUrl);
    return { kind: 'bytes' as const, buffer, filename };
  }
}
