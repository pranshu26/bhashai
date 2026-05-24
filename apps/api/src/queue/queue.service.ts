import { Injectable, OnModuleDestroy } from '@nestjs/common';
import { Queue, type JobsOptions } from 'bullmq';
import IORedis from 'ioredis';
import { type QueueName } from '@bhashai/shared';
import { env } from '../env';

const DEFAULT_JOB_OPTS: JobsOptions = {
  attempts: 5,
  backoff: { type: 'exponential', delay: 5000 },
  removeOnComplete: 1000,
  removeOnFail: false,
};

@Injectable()
export class QueueService implements OnModuleDestroy {
  // Shared connection for all producer queues.
  private readonly connection = new IORedis(env.REDIS_URL, { maxRetriesPerRequest: null });
  private readonly queues = new Map<QueueName, Queue>();

  private get(name: QueueName): Queue {
    let q = this.queues.get(name);
    if (!q) {
      q = new Queue(name, { connection: this.connection });
      this.queues.set(name, q);
    }
    return q;
  }

  enqueue(name: QueueName, jobName: string, data: Record<string, unknown>, opts: JobsOptions = {}) {
    return this.get(name).add(jobName, data, { ...DEFAULT_JOB_OPTS, ...opts });
  }

  async onModuleDestroy() {
    for (const q of this.queues.values()) await q.close();
    await this.connection.quit();
  }
}
