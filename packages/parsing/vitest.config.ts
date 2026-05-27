import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

const pkg = (name: string) => resolve(__dirname, '..', name, 'src', 'index.ts');

export default defineConfig({
  resolve: {
    alias: {
      '@bhashai/shared': pkg('shared'),
      '@bhashai/db': pkg('db'),
      '@bhashai/storage': pkg('storage'),
      '@bhashai/engines': pkg('engines'),
      '@bhashai/parsing': pkg('parsing'),
    },
  },
});
