import { Global, Module } from '@nestjs/common';
import { PrismaService } from './prisma.service';
import { StorageService } from './storage.service';
import { QueueService } from './queue/queue.service';
import { HealthController } from './health.controller';
import { AuthModule } from './auth/auth.module';
import { JobsModule } from './jobs/jobs.module';

@Global()
@Module({
  imports: [AuthModule, JobsModule],
  controllers: [HealthController],
  providers: [PrismaService, StorageService, QueueService],
  exports: [PrismaService, StorageService, QueueService],
})
export class AppModule {}
