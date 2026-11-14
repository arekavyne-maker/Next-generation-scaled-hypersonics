import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { apiMode, fetchHealth, type DataSourceState } from '../api/client';
import { SERVICE_LABELS, SERVICE_NAMES, type HealthStatus, type ServiceName } from '../api/types';
import { useDataSource } from '../lib/useDataSource';
import { Icon, type IconName } from './Icon';

interface RouteDef {
  path: string;
  label: string;
  icon: IconName;
  group: string;
  description: string;
}

export const ROUTES: RouteDef[] = [
  { path: '/', label: 'Overview', icon: 'overview', group: 'Platform', description: 'Service health, ontology coverage and throughput' },
  { path: '/events', label: 'Event Stream', icon: 'stream', group: 'Fabric', description: 'The append-only event log' },
  { path: '/thread', label: 'Digital Thread', icon: 'thread', group: 'Fabric', description: 'Trace the graph across the ontology' },
  { path: '/requirements', label: 'Requirements', icon: 'requirements', group: 'Assurance', description: 'Verification coverage and gaps' },
  { path: '/audit', label: 'Audit Ledger', icon: 'audit', group: 'Assurance', description: 'Tamper-evident decision chain' },
  { path: '/access', label: 'Access Decisions', icon: 'access', group: 'Assurance', description: 'Policy decision point explorer' },
];

const GROUPS = ['Platform', 'Fabric', 'Assurance'];

function useServiceHealth(): Record<ServiceName, HealthStatus> {  const [health, setHealth] = useState<Record<ServiceName, HealthStatus>>(() => {
    const initial = {} as Record<ServiceName, HealthStatus>;
    for (const service of SERVICE_NAMES) {
      initial[service] = { service, status: 'down', latencyMs: 0 };
    }
    return initial;
  });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const poll = async (): Promise<void> => {
      const results = await Promise.all(
        SERVICE_NAMES.map((service) => fetchHealth(service, controller.signal).catch(() => null)),
      );
      if (!active) return;
      const next = {} as Record<ServiceName, HealthStatus>;
      SERVICE_NAMES.forEach((service, index) => {
        next[service] = results[index] ?? { service, status: 'down', latencyMs: 0, detail: 'unreachable' };
      });
      setHealth(next);
    };

    void poll();
    const interval = window.setInterval(() => void poll(), 30_000);

    return () => {
      active = false;
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  return health;
}

function DataSourceBadge({ state }: { state: DataSourceState }): JSX.Element {
  if (state.forcedMock) {
    return (
      <span className="badge badge-warn" title="VITE_USE_MOCK=true — the console is serving the deterministic mock dataset.">
        mock dataset
      </span>
    );
  }
  if (state.mode === 'live') {
    return (
      <span className="badge badge-ok" title="All requests are being served by the live NGSH services.">
        live
      </span>
    );
  }
  if (state.mode === 'degraded') {
    return (
      <span
        className="badge badge-warn"
        title={`Some services are unreachable; those calls fall back to the mock dataset. Last fallback: ${state.lastFallbackReason ?? 'unknown'}`}
      >
        partial — mock fallback
      </span>
    );
  }
  return (
    <span
      className="badge badge-warn"
      title={`The backend is unreachable; the console is serving the deterministic mock dataset. Last fallback: ${state.lastFallbackReason ?? 'unknown'}`}
    >
      mock fallback
    </span>
  );
}

export function Layout(): JSX.Element {
  const location = useLocation();
  const health = useServiceHealth();
  const dataSource = useDataSource();

  const active = useMemo(
    () => ROUTES.find((route) => (route.path === '/' ? location.pathname === '/' : location.pathname.startsWith(route.path))),
    [location.pathname],
  );

  const mocked = dataSource.mode !== 'live';

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Icon name="database" size={14} />
          </span>
          <span className="brand-text">
            <span className="brand-title">NGSH</span>
            <span className="brand-subtitle">Control Console</span>
          </span>
        </div>

        <nav aria-label="Primary">
          {GROUPS.map((group) => (
            <div className="nav-section" key={group}>
              <div className="nav-section-label">{group}</div>
              <ul className="nav-list">
                {ROUTES.filter((route) => route.group === group).map((route) => (
                  <li key={route.path}>
                    <NavLink
                      to={route.path}
                      end={route.path === '/'}
                      className={({ isActive }) => (isActive ? 'nav-item is-active' : 'nav-item')}
                    >
                      <span className="nav-item-icon" aria-hidden="true">
                        <Icon name={route.icon} size={14} />
                      </span>
                      <span className="nav-item-label">{route.label}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer-row">
            <span>Data source</span>
            <DataSourceBadge state={dataSource} />
          </div>
          <div className="sidebar-footer-row">
            <span>API</span>
            <span className="mono" title={apiMode() === 'proxy' ? 'Requests are routed through the dev proxy at /api/<service>.' : 'Requests go directly to the service base URLs.'}>
              {apiMode()}
            </span>
          </div>
          <div className="sidebar-footer-row">
            <span>Tenant</span>
            <span className="mono">ngsh</span>
          </div>
          <div className="sidebar-footer-row">
            <span>Console</span>
            <span className="mono">0.1.0</span>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div className="topbar-title">
            <h1>{active?.label ?? 'NGSH'}</h1>
            <span>{active?.description ?? ''}</span>
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-group">
            <div className="health-strip" role="status" aria-label="Service health">
              {SERVICE_NAMES.map((service) => (
                <span className="health-dot" key={service} data-status={health[service].status} title={`${SERVICE_LABELS[service]}: ${health[service].status}`}>
                  {service.slice(0, 4)}
                </span>
              ))}
            </div>
            {mocked ? (
              <span className="chip" title="Some panels are served by the deterministic mock dataset because a service is unreachable.">
                mock
              </span>
            ) : null}
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
