import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OverviewPage } from './pages/OverviewPage';
import { EventStreamPage } from './pages/EventStreamPage';
import { ThreadPage } from './pages/ThreadPage';
import { RequirementsPage } from './pages/RequirementsPage';
import { AuditPage } from './pages/AuditPage';
import { AccessPage } from './pages/AccessPage';
import { PlatformPage } from './pages/PlatformPage';

export function App(): JSX.Element {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="events" element={<EventStreamPage />} />
        <Route path="thread" element={<ThreadPage />} />
        <Route path="requirements" element={<RequirementsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="access" element={<AccessPage />} />
        <Route path="platform" element={<PlatformPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
