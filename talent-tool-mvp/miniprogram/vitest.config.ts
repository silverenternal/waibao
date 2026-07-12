import { defineConfig } from 'vitest/config';
import uni from '@dcloudio/vite-plugin-uni';
import path from 'node:path';

// T1203 — Vitest config. Runs in jsdom with the uni-app plugin to provide
// the `uni.*` global stub used by the request helper.
export default defineConfig({
  plugins: [uni()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    setupFiles: ['./tests/setup.ts'],
  },
});