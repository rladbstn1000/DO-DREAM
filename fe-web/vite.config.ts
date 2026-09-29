import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // The phase-1 path never loads existing deployment .env files.
  envDir: mode === 'phase1' ? path.resolve(__dirname, 'local-env') : undefined,
  define: mode === 'phase1' ? {
    'import.meta.env.VITE_API_BASE': JSON.stringify(''),
    'import.meta.env.VITE_RAG_BASE': JSON.stringify('/ai'),
  } : undefined,
  server: mode === 'phase1' ? {
    strictPort: true,
    headers: {
      'Content-Security-Policy': "default-src 'self'; connect-src 'self' ws://127.0.0.1:5173; font-src 'self' data:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'",
    },
    proxy: {
      '/api': { target: 'http://127.0.0.1:18082' },
      '/ai': {
        target: 'http://127.0.0.1:18000',
        rewrite: (requestPath) => requestPath.replace(/^\/ai/, ''),
      },
    },
  } : undefined,
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') }
  },
}));
