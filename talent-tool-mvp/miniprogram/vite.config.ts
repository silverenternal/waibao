import { defineConfig } from 'vite';
import uni from '@dcloudio/vite-plugin-uni';

// T1203 — uni-app (Vue 3 + Vite) cross-platform config.
// Output targets: mp-weixin (default), h5, app. Switch with `npm run dev:<target>`.
export default defineConfig({
  plugins: [uni()],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    port: 5173,
  },
  build: {
    target: 'es2015',
    cssCodeSplit: false,
    // The mini-program platform doesn't tolerate dynamic chunks — bundle as IIFE.
    rollupOptions: {
      output: {
        manualChunks: undefined,
      },
    },
  },
});