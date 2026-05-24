import { Controller, Get } from '@nestjs/common';
import { PrismaService } from './prisma.service';
import { env } from './env';

@Controller('health')
export class HealthController {
  constructor(private readonly prisma: PrismaService) {}

  @Get()
  async health() {
    let db = 'down';
    try {
      await this.prisma.db.$queryRaw`SELECT 1`;
      db = 'up';
    } catch {
      /* db down */
    }
    return { status: db === 'up' ? 'ok' : 'degraded', db, storage: env.STORAGE_DRIVER };
  }
}
