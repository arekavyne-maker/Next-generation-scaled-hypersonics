import { defineConfig, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * NGSH Control Console dev configuration.
 *
 * The console talks to the platform through one origin. Every `/api/<service>/...`
 * request goes to the gateway, which owns the service map and forwards the
 * call without rewriting the domain:
 *
 *   /api/ontology/v1/registry   -> gateway -> http://ontology-service:8081/v1/registry
 *   /api/thread/v1/trace        -> gateway -> http://thread-service:8085/v1/trace
 *   /api/gateway/v1/platform/status -> the gateway's own platform status
 *
 * Keeping the console on the gateway in development means the same URL layout
 * works in the container topology, where nginx does the same job.
 */
const GATEWAY_TARGET = process.env.NGSH_GATEWAY_URL ?? 'http://127.0.0.1:8080';

const proxy: Record<string, ProxyOptions> = {
  // The gateway's own endpoints are mounted at its root, so the console's
  // `/api/gateway/...` prefix is stripped before forwarding.
  '/api/gateway': {
    target: GATEWAY_TARGET,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api\/gateway/, ''),
  },
  '/api': {
    target: GATEWAY_TARGET,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy,
  },
  preview: {
    port: 4173,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    chunkSizeWarningLimit: 900,
  },
});
