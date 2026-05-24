// PM2 process map (alternative to Docker Compose). `pm2 start infra/ecosystem.config.js`.
// Split workers by queue group for independent scaling.
module.exports = {
  apps: [
    {
      name: 'api',
      cwd: './apps/api',
      script: 'dist/main.js',
      instances: 2,
      exec_mode: 'cluster',
      env: { NODE_ENV: 'production', PORT: '3001' },
    },
    {
      name: 'web',
      cwd: './apps/web',
      script: 'node_modules/next/dist/bin/next',
      args: 'start -p 3000',
      env: { NODE_ENV: 'production' },
    },
    {
      name: 'extraction-worker',
      cwd: './apps/worker',
      script: 'dist/main.js',
      env: { NODE_ENV: 'production', WORKER_QUEUES: 'document.extract,document.analyze,document.chunk' },
    },
    {
      name: 'translation-worker',
      cwd: './apps/worker',
      script: 'dist/main.js',
      instances: 2,
      env: { NODE_ENV: 'production', WORKER_QUEUES: 'translation.chunk,translation.postedit' },
    },
    {
      name: 'qa-worker',
      cwd: './apps/worker',
      script: 'dist/main.js',
      env: { NODE_ENV: 'production', WORKER_QUEUES: 'translation.qa' },
    },
    {
      name: 'reconstruction-worker',
      cwd: './apps/worker',
      script: 'dist/main.js',
      env: { NODE_ENV: 'production', WORKER_QUEUES: 'document.reconstruct,document.export,cleanup' },
    },
  ],
};
