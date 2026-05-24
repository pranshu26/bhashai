import {
  S3Client,
  PutObjectCommand,
  GetObjectCommand,
  HeadObjectCommand,
  DeleteObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import type { StorageDriver, PutResult, PresignResult } from './types';

export class S3Driver implements StorageDriver {
  readonly supportsPresign = true;

  constructor(
    private readonly client: S3Client,
    private readonly bucket: string,
  ) {}

  async put(key: string, body: Buffer | string, contentType?: string): Promise<PutResult> {
    const buf = typeof body === 'string' ? Buffer.from(body, 'utf8') : body;
    await this.client.send(
      new PutObjectCommand({ Bucket: this.bucket, Key: key, Body: buf, ContentType: contentType }),
    );
    return { key, size: buf.length };
  }

  async get(key: string): Promise<Buffer> {
    const res = await this.client.send(new GetObjectCommand({ Bucket: this.bucket, Key: key }));
    const bytes = await res.Body!.transformToByteArray();
    return Buffer.from(bytes);
  }

  async exists(key: string): Promise<boolean> {
    try {
      await this.client.send(new HeadObjectCommand({ Bucket: this.bucket, Key: key }));
      return true;
    } catch {
      return false;
    }
  }

  async delete(key: string): Promise<void> {
    await this.client.send(new DeleteObjectCommand({ Bucket: this.bucket, Key: key }));
  }

  async presignGet(key: string, expiresSeconds = 900): Promise<PresignResult> {
    const url = await getSignedUrl(this.client, new GetObjectCommand({ Bucket: this.bucket, Key: key }), {
      expiresIn: expiresSeconds,
    });
    return { url, method: 'GET', key, expiresSeconds };
  }

  async presignPut(key: string, contentType?: string, expiresSeconds = 900): Promise<PresignResult> {
    const url = await getSignedUrl(
      this.client,
      new PutObjectCommand({ Bucket: this.bucket, Key: key, ContentType: contentType }),
      { expiresIn: expiresSeconds },
    );
    return { url, method: 'PUT', key, expiresSeconds };
  }
}
