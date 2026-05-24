import * as path from 'node:path';
import { S3Client } from '@aws-sdk/client-s3';
import { LocalDriver } from './local.driver';
import { S3Driver } from './s3.driver';
import type { Storage, StorageConfig } from './types';

export function createStorage(config: StorageConfig): Storage {
  if (config.driver === 's3') {
    if (!config.s3) throw new Error('STORAGE_DRIVER=s3 requires s3 config');
    const s3 = config.s3;
    const client = new S3Client({
      region: s3.region,
      endpoint: s3.endpoint,
      forcePathStyle: !!s3.endpoint,
      credentials:
        s3.accessKeyId && s3.secretAccessKey
          ? { accessKeyId: s3.accessKeyId, secretAccessKey: s3.secretAccessKey }
          : undefined, // fall back to the EC2 instance role / default chain
    });
    return {
      kind: 's3',
      raw: new S3Driver(client, s3.rawBucket),
      processed: new S3Driver(client, s3.processedBucket),
    };
  }
  const root = config.local?.rootDir ?? '.data';
  return {
    kind: 'local',
    raw: new LocalDriver(path.join(root, 'raw')),
    processed: new LocalDriver(path.join(root, 'processed')),
  };
}

export * from './types';
export * from './keys';
export { LocalDriver } from './local.driver';
export { S3Driver } from './s3.driver';
