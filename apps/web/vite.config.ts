import { defineConfig, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * NGSH Control Console dev configuration.
 *
 * The console talks to six independent microservices. In development we proxy a
 * single origin (`/api/<service>/...`) to each service's real port so the
 * browser never has to deal with CORS or with six absolute origins.
 *
 *   /api/ontology -> http://localhost:8081
 *   /api/fabric   -> http://localhost:8082
 *   /api/policy   -> http://localhost:8083
 *   /api/audit    -> http://localhost:8084
 *   /api/thread   -> http://localhost:8085
 *   /api/ingest   -> http://localhost:8086
 */
const SERVICE_TARGETS: Record<string, string> = {
  ontology: 'http://localhost:8081',
  fabric: 'http://localhost:8082',
  policy: 'http://localhost:8083',
  audit: 'http://localhost:8084',
  thread: 'http://localhost:8085',
  ingest: 'http://localhost:8086',
};

const proxy: Record<string, ProxyOptions> = {};
for (const [service, target] of Object.entries(SERVICE_TARGETS)) {
  proxy[`/api/${service}`] = {
    target,
    changeOrigin: true,
    rewrite: (path: string) => path.replace(new RegExp(`^/api/${service}`), ''),
  };
}

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
