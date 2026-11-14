/**
 * NGSH Control Console — headless render smoke test.
 *
 * Renders every route inside a JSDOM document with the API layer pointed at
 * an unreachable backend, which forces the deterministic mock fallback. The
 * test then asserts that each route produced meaningful content.
 *
 *   node scripts/smoke.mjs
 */

import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');

const ROUTES = [
  { path: '/', expect: ['Ontology version', 'Event rate', 'entity.created'] },
  { path: '/events', expect: ['Event stream', 'entity.created', 'test.result.recorded'] },
  { path: '/thread', expect: ['Trace explorer', 'Digital thread', 'Relation types'] },
  { path: '/requirements', expect: ['Verification coverage', 'Verifying test results', 'REQ:'] },
  { path: '/audit', expect: ['Audit ledger', 'Chain verified', 'prevHash'] },
  { path: '/access', expect: ['Policy decision', 'Subject', 'Resource'] },
];

async function bundle(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'ngsh-smoke-'));
  const outfile = join(dir, 'entry.mjs');
  await build({
    entryPoints: [join(root, 'scripts', 'smoke-entry.tsx')],
    outfile,
    bundle: true,
    format: 'esm',
    platform: 'browser',
    jsx: 'automatic',
    target: 'es2022',
    define: {
      'import.meta.env': JSON.stringify(FORCE_MOCK ? { VITE_USE_MOCK: 'true' } : {}),
      'process.env.NODE_ENV': '"development"',
    },
    logLevel: 'error',
  });
  return outfile;
}

function installDom(): JSDOM {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost:5173/',
    pretendToBeVisual: true,
  });

  const { window } = dom;
  const define = (key: string, value: unknown): void => {
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  };

  define('window', window);
  define('document', window.document);
  define('navigator', window.navigator);
  define('location', window.location);
  define('history', window.history);
  define('HTMLElement', window.HTMLElement);
  define('Element', window.Element);
  define('Node', window.Node);
  define('Event', window.Event);
  define('CustomEvent', window.CustomEvent);
  define('MutationObserver', window.MutationObserver);
  define('getComputedStyle', window.getComputedStyle.bind(window));
  define('requestAnimationFrame', window.requestAnimationFrame?.bind(window) ?? ((cb: FrameRequestCallback) => setTimeout(() => cb(Date.now()), 16)));
  define('cancelAnimationFrame', window.cancelAnimationFrame?.bind(window) ?? clearTimeout);
  define('AbortController', window.AbortController ?? AbortController);

  // No backend in the smoke environment: every call must fall back to the mock.
  window.fetch = () => Promise.reject(new TypeError('Failed to fetch'));
  globalThis.fetch = window.fetch;

  return dom;
}

const DUMP = process.argv.includes('--dump');
const FORCE_MOCK = process.argv.includes('--mock');

async function main(): Promise<void> {
  const outfile = await bundle();
  const dom = installDom();

  try {
    const entry = await import(pathToFileURL(outfile).href);
    const { renderRoute, cleanup } = entry;
    await renderRoute('/');

    let failures = 0;

    for (const route of ROUTES) {
      cleanup();
      await renderRoute(route.path);
      await new Promise((resolve) => setTimeout(resolve, 450));

      const text = dom.window.document.body.textContent ?? '';
      const missing = route.expect.filter((needle) => !text.includes(needle));

      if (DUMP) {
        console.log(`\n===== ${route.path} =====`);
        console.log(text.replace(/([a-z0-9])([A-Z])/g, '$1 | $2').slice(0, 2600));
      }

      if (missing.length === 0) {
        console.log(`  PASS  ${route.path.padEnd(14)} ${text.length} chars of content`);
      } else {
        failures += 1;
        console.log(`  FAIL  ${route.path.padEnd(14)} missing: ${missing.join(', ')}`);
        console.log(`        got: ${text.slice(0, 400).replace(/\s+/g, ' ')}`);
      }
    }

    console.log(failures === 0 ? '\nAll routes rendered.' : `\n${failures} route(s) failed.`);
    process.exitCode = failures === 0 ? 0 : 1;
  } finally {
    dom.window.close();
    await rm(dirname(outfile), { recursive: true, force: true });
  }
}

await main();
