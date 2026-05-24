import { Injectable } from '@nestjs/common';
import { createStorage, type Storage } from '@bhashai/storage';
import { env } from './env';

@Injectable()
export class StorageService {
  readonly storage: Storage = createStorage(
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
}
