import { promises as fs } from 'node:fs';
import * as path from 'node:path';
import type { StorageDriver, PutResult, PresignResult } from './types';

/** Filesystem-backed driver for dev/CI. Mirrors the S3 key layout under a root dir. */
export class LocalDriver implements StorageDriver {
  readonly supportsPresign = false;

  constructor(private readonly root: string) {}

  private full(key: string): string {
    // prevent path traversal out of the root
    const resolved = path.resolve(this.root, key);
    if (!resolved.startsWith(path.resolve(this.root))) {
      throw new Error(`Invalid storage key: ${key}`);
    }
    return resolved;
  }

  async put(key: string, body: Buffer | string): Promise<PutResult> {
    const p = this.full(key);
    await fs.mkdir(path.dirname(p), { recursive: true });
    const buf = typeof body === 'string' ? Buffer.from(body, 'utf8') : body;
    await fs.writeFile(p, buf);
    return { key, size: buf.length };
  }

  async get(key: string): Promise<Buffer> {
    return fs.readFile(this.full(key));
  }

  async exists(key: string): Promise<boolean> {
    try {
      await fs.access(this.full(key));
      return true;
    } catch {
      return false;
    }
  }

  async delete(key: string): Promise<void> {
    try {
      await fs.unlink(this.full(key));
    } catch (e: unknown) {
      if ((e as NodeJS.ErrnoException).code !== 'ENOENT') throw e;
    }
  }

  async presignGet(): Promise<PresignResult> {
    throw new Error('LocalDriver has no presigned URLs; stream the file through the API.');
  }

  async presignPut(): Promise<PresignResult> {
    throw new Error('LocalDriver has no presigned URLs; upload via the API multipart endpoint.');
  }
}
