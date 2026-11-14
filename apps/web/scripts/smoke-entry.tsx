/**
 * Smoke-test entry point. Bundled by `scripts/smoke.mjs` and executed inside
 * a JSDOM document. Not part of the application bundle.
 */

import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { OverviewPage } from '../src/pages/OverviewPage';
import { EventStreamPage } from '../src/pages/EventStreamPage';
import { ThreadPage } from '../src/pages/ThreadPage';
import { RequirementsPage } from '../src/pages/RequirementsPage';
import { AuditPage } from '../src/pages/AuditPage';
import { AccessPage } from '../src/pages/AccessPage';

let currentRoot: Root | null = null;
let currentContainer: HTMLElement | null = null;

export async function renderRoute(path: string): Promise<void> {
  const container = document.createElement('div');
  document.body.appendChild(container);
  currentContainer = container;
  currentRoot = createRoot(container);

  currentRoot.render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/events" element={<EventStreamPage />} />
        <Route path="/thread" element={<ThreadPage />} />
        <Route path="/requirements" element={<RequirementsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/access" element={<AccessPage />} />
      </Routes>
    </MemoryRouter>,
  );

  await new Promise((resolve) => setTimeout(resolve, 0));
}

export function cleanup(): void {
  if (currentRoot) {
    currentRoot.unmount();
    currentRoot = null;
  }
  if (currentContainer) {
    currentContainer.remove();
    currentContainer = null;
  }
}
