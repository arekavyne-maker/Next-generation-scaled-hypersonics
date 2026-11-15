import { useMemo } from 'react';
import { fetchPlatformCapabilities, fetchPlatformStatus } from '../api/client';
import type { CapabilityRow, InterfaceRow, PlatformServiceStatus } from '../api/types';
import { Panel } from '../components/Panel';
import { useAsync } from '../lib/useAsync';
import { useDataSource } from '../lib/useDataSource';

const PILLAR_NAMES: Record<string, string> = {
  A: 'MBSE & Digital Thread Core',
  B: 'Smart Manufacturing & Materials Process Intelligence',
  C: 'Test, Evaluation & Flight Demonstration Data Platform',
  D: 'Supply Chain & Production Scaling',
  E: 'Cleared Workforce Pipeline of Record',
  F: 'Counter-Hypersonic Kill-Chain Engineering',
  G: 'Test Enterprise & M&S Federation',
  H: 'Industrial Surge & Affordability',
};

const PILLAR_ORDER = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];

const STATUS_BADGE: Record<string, string> = {
  IMPLEMENTED: 'badge-ok',
  ADAPTER: 'badge-warn',
  INBOUND_ONLY: 'badge-info',
};

function ServiceRow({ service }: { service: PlatformServiceStatus }): JSX.Element {
  return (
    <tr>
      <td className="mono-id">{service.name}</td>
      <td className="mono-id text-xs truncate">{service.url}</td>
      <td>
        <span className={`badge ${service.status === 'ok' ? 'badge-ok' : 'badge-danger'}`}>
          {service.status}
        </span>
      </td>
      <td className="num">{service.statusCode || '—'}</td>
    </tr>
  );
}

function CapabilityGroup({ pillar, rows }: { pillar: string; rows: CapabilityRow[] }): JSX.Element {
  return (
    <div className="pillar-group">
      <div className="row row-tight">
        <span className="pillar-id">{pillar}</span>
        <span className="pillar-name">{PILLAR_NAMES[pillar] ?? `Pillar ${pillar}`}</span>
        <span className="chip">{rows.length}</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <caption className="sr-only">Capabilities in pillar {pillar}</caption>
          <thead>
            <tr>
              <th scope="col">Id</th>
              <th scope="col">Capability</th>
              <th scope="col">Service</th>
              <th scope="col">Status</th>
              <th scope="col">Runnable path</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="mono-id">{row.id}</td>
                <td>{row.name}</td>
                <td className="mono-id text-xs">{row.service}</td>
                <td>
                  <span className={`badge ${STATUS_BADGE[row.status] ?? 'badge-neutral'}`}>{row.status}</span>
                </td>
                <td className="mono text-xs">
                  {row.endpoints.length === 0 ? '—' : row.endpoints.join(' · ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function InterfaceRowView({ row }: { row: InterfaceRow }): JSX.Element {
  return (
    <tr>
      <td className="mono-id">{row.id}</td>
      <td>{row.name}</td>
      <td className="mono text-xs">{row.direction}</td>
      <td className="text-xs">{row.counterpart}</td>
      <td>
        <span className={`badge ${STATUS_BADGE[row.status] ?? 'badge-neutral'}`}>{row.status}</span>
      </td>
    </tr>
  );
}

export function PlatformPage(): JSX.Element {
  const dataSource = useDataSource();
  const mocked = dataSource.mode !== 'live';

  const status = useAsync((signal) => fetchPlatformStatus(signal), []);
  const capabilities = useAsync((signal) => fetchPlatformCapabilities(signal), []);

  const grouped = useMemo(() => {
    const rows = capabilities.data?.capabilities ?? [];
    const groups = new Map<string, CapabilityRow[]>();
    for (const row of rows) {
      groups.set(row.pillar, [...(groups.get(row.pillar) ?? []), row]);
    }
    return PILLAR_ORDER.filter((pillar) => groups.has(pillar)).map((pillar) => ({
      pillar,
      rows: groups.get(pillar) ?? [],
    }));
  }, [capabilities.data]);

  const platformStatus = status.data;
  const matrix = capabilities.data;

  return (
    <div className="stack">
      {mocked ? (
        <div className="notice" data-tone="warn">
          Some platform data is coming from the deterministic mock dataset. Start the stack and open
          through the gateway (<code>/api/gateway</code>) to see live values.
        </div>
      ) : null}

      <section aria-label="Platform summary" className="grid grid-metrics">
        <article className="status-tile" data-status={platformStatus?.status === 'ok' ? 'ok' : 'down'}>
          <div className="status-tile-head">
            <span className="status-tile-name">Platform</span>
            <span className="chip">gateway</span>
          </div>
          <div className="status-tile-metric">{platformStatus?.status ?? '—'}</div>
          <div className="status-tile-label">
            {platformStatus
              ? `${platformStatus.healthyCount}/${platformStatus.serviceCount} services healthy`
              : 'probing services'}
          </div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Capabilities</span>
            <span className="chip">PSDD scope</span>
          </div>
          <div className="status-tile-metric">{matrix?.count ?? '—'}</div>
          <div className="status-tile-label">{matrix ? `${matrix.pillarCount} pillars` : 'loading matrix'}</div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">External interfaces</span>
            <span className="chip">IF-1 … IF-7</span>
          </div>
          <div className="status-tile-metric">{matrix?.interfaceCount ?? '—'}</div>
          <div className="status-tile-label">register, direction and adapter status</div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Deployable services</span>
            <span className="chip">independently licensable</span>
          </div>
          <div className="status-tile-metric">{platformStatus?.serviceCount ?? '—'}</div>
          <div className="status-tile-label">plus the gateway in front of them</div>
        </article>
      </section>

      <div className="grid grid-two">
        <Panel
          title="Service health"
          subtitle={platformStatus ? `checked ${platformStatus.checkedAt}` : 'probing'}
          actions={
            <button className="btn btn-ghost btn-sm" type="button" onClick={status.reload}>
              refresh
            </button>
          }
          flush
        >
          {status.error ? (
            <div className="notice" data-tone="danger">{status.error.message}</div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Live health of every platform service</caption>
                <thead>
                  <tr>
                    <th scope="col">Service</th>
                    <th scope="col">Resolved address</th>
                    <th scope="col">Status</th>
                    <th scope="col">HTTP</th>
                  </tr>
                </thead>
                <tbody>
                  {(platformStatus?.services ?? []).map((service) => (
                    <ServiceRow key={service.name} service={service} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title="External interfaces"
          subtitle={matrix ? `${matrix.interfaceCount} declared in the register` : 'loading'}
          actions={
            <button className="btn btn-ghost btn-sm" type="button" onClick={capabilities.reload}>
              refresh
            </button>
          }
          flush
        >
          {capabilities.error ? (
            <div className="notice" data-tone="danger">{capabilities.error.message}</div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">PSDD external interfaces and their v1 status</caption>
                <thead>
                  <tr>
                    <th scope="col">Id</th>
                    <th scope="col">Interface</th>
                    <th scope="col">Direction</th>
                    <th scope="col">Counterpart</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(matrix?.interfaces ?? []).map((row) => (
                    <InterfaceRowView key={row.id} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {matrix ? <div className="panel-footer text-muted text-sm">{matrix.note}</div> : null}
        </Panel>
      </div>

      <Panel
        title="Capability matrix"
        subtitle="Every PSDD capability, its owning service and the runnable path that exercises it"
      >
        {capabilities.error ? (
          <div className="notice" data-tone="danger">{capabilities.error.message}</div>
        ) : grouped.length === 0 ? (
          <div className="list-plain">
            {Array.from({ length: 5 }).map((_, index) => (
              <div className="skeleton" key={index} style={{ height: 22 }} />
            ))}
          </div>
        ) : (
          <div className="stack">
            {grouped.map((group) => (
              <CapabilityGroup key={group.pillar} pillar={group.pillar} rows={group.rows} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
