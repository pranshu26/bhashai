import {
  Body,
  Controller,
  Get,
  Param,
  Post,
  Res,
  StreamableFile,
  UploadedFile,
  UseGuards,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import type { Response } from 'express';
import { createJobSchema, type CreateJobDto } from '@bhashai/shared';
import { ZodBody } from '../common/zod.pipe';
import { JwtGuard } from '../auth/jwt.guard';
import { CurrentUser, type AuthUser } from '../auth/current-user.decorator';
import { JobsService } from './jobs.service';
import { env } from '../env';

@Controller('translation-jobs')
@UseGuards(JwtGuard)
export class JobsController {
  constructor(private readonly jobs: JobsService) {}

  @Post()
  create(@CurrentUser() u: AuthUser, @Body(new ZodBody(createJobSchema)) dto: CreateJobDto) {
    return this.jobs.create(u.userId, dto);
  }

  @Get()
  list(@CurrentUser() u: AuthUser) {
    return this.jobs.list(u.userId);
  }

  @Get(':id')
  get(@CurrentUser() u: AuthUser, @Param('id') id: string) {
    return this.jobs.get(u.userId, id);
  }

  @Post(':id/upload')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: env.MAX_UPLOAD_MB * 1024 * 1024 } }))
  upload(@CurrentUser() u: AuthUser, @Param('id') id: string, @UploadedFile() file: Express.Multer.File) {
    return this.jobs.upload(u.userId, id, file);
  }

  @Post(':id/start')
  start(@CurrentUser() u: AuthUser, @Param('id') id: string) {
    return this.jobs.start(u.userId, id);
  }

  @Get(':id/progress')
  progress(@CurrentUser() u: AuthUser, @Param('id') id: string) {
    return this.jobs.progress(u.userId, id);
  }

  @Post(':id/cancel')
  cancel(@CurrentUser() u: AuthUser, @Param('id') id: string) {
    return this.jobs.cancel(u.userId, id);
  }

  @Post(':id/retry-failed')
  retryFailed(@CurrentUser() u: AuthUser, @Param('id') id: string) {
    return this.jobs.retryFailed(u.userId, id);
  }

  @Get(':id/download')
  async download(@CurrentUser() u: AuthUser, @Param('id') id: string, @Res({ passthrough: true }) res: Response) {
    const out = await this.jobs.download(u.userId, id);
    if (out.kind === 'url') {
      res.redirect(out.url);
      return undefined;
    }
    res.set({
      'Content-Type': 'application/pdf',
      'Content-Disposition': `attachment; filename="${out.filename}"`,
    });
    return new StreamableFile(out.buffer);
  }
}
