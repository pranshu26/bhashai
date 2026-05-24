import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { promises as fs } from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { createStorage, StorageKeys } from './index';

let root: string;

beforeAll(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'bhashai-storage-'));
});
afterAll(async () => {
  await fs.rm(root, { recursive: true, force: true });
});

describe('local storage driver', () => {
  it('round-trips a file: put → exists → get → delete', async () => {
    const storage = createStorage({ driver: 'local', local: { rootDir: root } });
    expect(storage.kind).toBe('local');

    const key = StorageKeys.source('job123', 'thesis.docx');
    const put = await storage.raw.put(key, Buffer.from('hello बहास'), 'application/octet-stream');
    expect(put.key).toBe(key);
    expect(await storage.raw.exists(key)).toBe(true);

    const got = await storage.raw.get(key);
    expect(got.toString('utf8')).toBe('hello बहास');

    await storage.raw.delete(key);
    expect(await storage.raw.exists(key)).toBe(false);
  });

  it('isolates the raw and processed stores', async () => {
    const storage = createStorage({ driver: 'local', local: { rootDir: root } });
    const key = StorageKeys.extracted('job123');
    await storage.processed.put(key, '{"pages":[]}');
    expect(await storage.processed.exists(key)).toBe(true);
    expect(await storage.raw.exists(key)).toBe(false);
  });

  it('rejects path traversal keys', async () => {
    const storage = createStorage({ driver: 'local', local: { rootDir: root } });
    await expect(storage.raw.put('../../escape.txt', 'x')).rejects.toThrow(/Invalid storage key/);
  });

  it('reports that local presign is unsupported', async () => {
    const storage = createStorage({ driver: 'local', local: { rootDir: root } });
    expect(storage.raw.supportsPresign).toBe(false);
    await expect(storage.processed.presignGet('jobs/x/exports/reflowed.docx')).rejects.toThrow();
  });
});
