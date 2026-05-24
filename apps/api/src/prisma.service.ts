import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { prisma } from '@bhashai/db';

/** Thin Nest-injectable wrapper around the shared Prisma singleton. */
@Injectable()
export class PrismaService implements OnModuleInit, OnModuleDestroy {
  readonly db = prisma;

  async onModuleInit() {
    await this.db.$connect();
  }
  async onModuleDestroy() {
    await this.db.$disconnect();
  }
}
