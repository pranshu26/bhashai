export interface PutResult {
  key: string;
  size: number;
}

export interface PresignResult {
  url: string;
  method: 'GET' | 'PUT';
  key: string;
  expiresSeconds: number;
}

export interface StorageDriver {
  /** S3 supports presigned URLs; the local driver does not (the API streams instead). */
  readonly supportsPresign: boolean;
  put(key: string, body: Buffer | string, contentType?: string): Promise<PutResult>;
  get(key: string): Promise<Buffer>;
  exists(key: string): Promise<boolean>;
  delete(key: string): Promise<void>;
  presignGet(key: string, expiresSeconds?: number): Promise<PresignResult>;
  presignPut(key: string, contentType?: string, expiresSeconds?: number): Promise<PresignResult>;
}

/** Two logical buckets per ARCHITECTURE.md §11: immutable source (raw) + derived (processed). */
export interface Storage {
  kind: 'local' | 's3';
  raw: StorageDriver;
  processed: StorageDriver;
}

export interface StorageConfig {
  driver: 'local' | 's3';
  local?: { rootDir: string };
  s3?: {
    region: string;
    rawBucket: string;
    processedBucket: string;
    accessKeyId?: string;
    secretAccessKey?: string;
    endpoint?: string;
  };
}
