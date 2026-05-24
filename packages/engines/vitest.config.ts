import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

// Resolve @bhashai/* workspace imports to source so tests run without a build step.
const pkg = (name: string) => resolve(__dirname, '..', name, 'src', 'index.ts');

export default defineConfig({
  resolve: {
    alias: {
      '@bhashai/shared': pkg('shared'),
      '@bhashai/db': pkg('db'),
      '@bhashai/storage': pkg('storage'),
      '@bhashai/engines': pkg('engines'),
      '@bhashai/parsing': pkg('parsing'),
      '@bhashai/glossary': pkg('glossary'),
      '@bhashai/qa': pkg('qa'),
      '@bhashai/reconstruct': pkg('reconstruct'),
    },
  },
});
