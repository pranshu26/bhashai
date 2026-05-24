// S3/local key builders. `source` lives in the raw store; the rest in the processed store.
export const StorageKeys = {
  source: (jobId: string, filename: string) => `jobs/${jobId}/source/${sanitize(filename)}`,
  extracted: (jobId: string) => `jobs/${jobId}/extracted/document.json`,
  asset: (jobId: string, assetId: string, ext: string) => `jobs/${jobId}/assets/${assetId}.${ext}`,
  exportFile: (jobId: string, mode: string, format: string) =>
    `jobs/${jobId}/exports/${mode.toLowerCase()}.${format}`,
  reference: (refId: string, filename: string) => `references/${refId}/${sanitize(filename)}`,
};

function sanitize(name: string): string {
  return name.replace(/[^\w.\-]+/g, '_').slice(0, 200);
}
