import { Worker } from 'bullmq';
import IORedis from 'ioredis';
import { QUEUE } from '@bhashai/shared';
import { env } from './env';
import { processJob } from './pipeline';

const connection = new IORedis(env.REDIS_URL, { maxRetriesPerRequest: null });

// MVP: a single consumer on document.extract runs the whole pipeline (analyze -> translate ->
// export). Stage queues exist in the design and split out under load (see IMPLEMENTATION-PLAN).
const worker = new Worker(
  QUEUE.EXTRACT,
  async (job) => {
    const { jobId } = job.data as { jobId: string };
    // eslint-disable-next-line no-console
    console.log(`[start] job ${jobId}`);
    await processJob(jobId);
  },
  { connection, concurrency: env.WORKER_CONCURRENCY },
);

worker.on('completed', (job) => console.log('[completed]', JSON.stringify(job.data)));
worker.on('failed', (job, err) => console.error('[failed]', JSON.stringify(job?.data), err?.message));

// eslint-disable-next-line no-console
console.log(`BhashAI worker listening on "${QUEUE.EXTRACT}" (concurrency ${env.WORKER_CONCURRENCY})`);

async function shutdown() {
  await worker.close();
  await connection.quit();
  process.exit(0);
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
