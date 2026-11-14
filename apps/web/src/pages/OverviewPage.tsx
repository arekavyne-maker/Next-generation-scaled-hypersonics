import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { fetchEvents, fetchGraphStats, fetchHealth, fetchRegistry } from '../api/client';
import { SERVICE_LABELS, SERVICE_NAMES, type HealthStatus, type ServiceName } from '../api/types';
import { ClassificationBadge } from '../components/ClassificationBadge';
import { EventTypeBadge } from '../components/EventRow';
import { Panel } from '../components/Panel';
import { StatusTile } from '../components/StatusTile';
import { useAsync } from '../lib/useAsync';
import { useDataSource } from '../lib/useDataSource';
import { formatCount, formatRelative, formatTimestamp } from '../lib/format';

const PILLAR_NAMES: Record<string, string> = {
  A: 'MBSE & Digital Thread Core',
  B: 'Smart Manufacturing & Materials Process Intelligence',
  C: 'Test, Evaluation & Flight Demonstration Data Platform',
  D: 'Supply Chain & Production Scaling',
  E: 'Cleared Workforce Pipeline of Record',
  F: 'Counter-Hypersonic Kill-Chain Engineering',
  G: 'Test Enterprise & M&S Federation',
  H: 'Industrial Surge & Affordability',
  FOUNDATION: 'Shared fabric, ontology and governance services',
};

const PILLAR_ORDER = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'FOUNDATION'];

export function OverviewPage(): JSX.Element {
  const dataSource = useDataSource();
  const mocked = dataSource.mode !== 'live';

  const health = useAsync<Record<ServiceName, HealthStatus>>(
    async (signal) => {
      const results = await Promise.all(
        SERVICE_NAMES.map((service) => fetchHealth(service, signal).catch(() => null)),
      );
      const record = {} as Record<ServiceName, HealthStatus>;
      SERVICE_NAMES.forEach((service, index) => {
        record[service] = results[index] ?? { service, status: 'down', latencyMs: 0, detail: 'unreachable' };
      });
      return record;
    },
    [],
  );

  const registry = useAsync(() => fetchRegistry(), []);
  const stats = useAsync(() => fetchGraphStats(), []);
  const recent = useAsync(() => fetchEvents({ limit: 100 }), []);

  const eventRate = useMemo(() => {
    const events = recent.data?.events ?? [];
    if (events.length === 0) return { perMinute: 0, window: 0, latest: null as string | null };
    const times = events.map((event) => new Date(event.recordedAt).getTime()).filter((value) => !Number.isNaN(value));
    if (times.length === 0) return { perMinute: 0, window: 0, latest: null };
    const latest = Math.max(...times);
    const windowMs = 60 * 60 * 1000;
    const inWindow = times.filter((value) => value >= latest - windowMs);
    const minutes = windowMs / 60_000;
    return {
      perMinute: Math.round((inWindow.length / minutes) * 10) / 10,
      window: inWindow.length,
      latest: new Date(latest).toISOString(),
    };
  }, [recent.data]);

  const latestEvents = useMemo(
    () =>
      (recent.data?.events ?? [])
        .slice()
        .sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt))
        .slice(0, 12),
    [recent.data],
  );

  const coverage = useMemo(() => {
    const entities = registry.data?.entities ?? [];
    const counts = stats.data?.entityCounts ?? {};
    const groups = new Map<string, typeof entities>();
    for (const entity of entities) {
      const primary = entity.pillars[0] ?? 'FOUNDATION';
      groups.set(primary, [...(groups.get(primary) ?? []), entity]);
    }
    return PILLAR_ORDER.filter((pillar) => groups.has(pillar)).map((pillar) => ({
      pillar,
      name: PILLAR_NAMES[pillar] ?? pillar,
      entities: groups.get(pillar) ?? [],
      counts,
    }));
  }, [registry.data, stats.data]);

  const totalTypes = registry.data?.entities.length ?? 0;

  return (
    <div className="stack">
      <section aria-label="Service status">
        <div className="grid grid-status">
          {SERVICE_NAMES.map((service) => {
            const status = health.data?.[service];
            return (
              <StatusTile
                key={service}
                name={SERVICE_LABELS[service]}
                status={status?.status ?? 'down'}
                metric={status ? `${status.latencyMs} ms` : '—'}
                metricLabel="health check latency"
                detail={status?.detail ?? 'awaiting health check'}
                mocked={mocked}
              />
            );
          })}
        </div>
      </section>

      <section aria-label="Platform metrics" className="grid grid-metrics">
        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Ontology version</span>
            <Link className="text-xs" to="/thread">
              explore
            </Link>
          </div>
          <div className="status-tile-metric">{registry.data?.ontologyVersion ?? '—'}</div>
          <div className="status-tile-label">{totalTypes} entity types · {registry.data?.relations.length ?? 0} relation types</div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Entities</span>
            <span className="chip">graph projection</span>
          </div>
          <div className="status-tile-metric">{stats.data ? formatCount(stats.data.totalEntities) : '—'}</div>
          <div className="status-tile-label">distinct ontology instances</div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Relations</span>
            <span className="chip">digital thread edges</span>
          </div>
          <div className="status-tile-metric">{stats.data ? formatCount(stats.data.totalRelations) : '—'}</div>
          <div className="status-tile-label">
            {stats.data ? Object.keys(stats.data.relationCounts).length : 0} relation types in use
          </div>
        </article>

        <article className="status-tile" data-status="ok">
          <div className="status-tile-head">
            <span className="status-tile-name">Event rate</span>
            <Link className="text-xs" to="/events">
              stream
            </Link>
          </div>
          <div className="status-tile-metric">{eventRate.perMinute.toFixed(1)}</div>
          <div className="status-tile-label">events / minute over the last hour</div>
          <div className="status-tile-detail">
            {eventRate.window} events in window
            {eventRate.latest ? ` · latest ${formatRelative(eventRate.latest)}` : ''}
          </div>
        </article>
      </section>

      <div className="grid grid-two">
        <Panel
          title="Ontology coverage"
          subtitle={`${totalTypes} entity types across ${PILLAR_ORDER.length} pillars`}
          actions={
            registry.error ? (
              <span className="badge badge-danger">registry unavailable</span>
            ) : (
              <span className="badge badge-neutral">v{registry.data?.ontologyVersion ?? '—'}</span>
            )
          }
        >
          {registry.loading ? (
            <div className="list-plain">
              {Array.from({ length: 6 }).map((_, index) => (
                <div className="skeleton" key={index} style={{ height: 22 }} />
              ))}
            </div>
          ) : registry.error ? (
            <div className="notice" data-tone="danger">
              {registry.error.message}
            </div>
          ) : coverage.length === 0 ? (
            <div className="text-muted">The ontology registry returned no entity types.</div>
          ) : (
            <div>
              {coverage.map((group) => (
                <div className="pillar-group" key={group.pillar}>
                  <div className="pillar-key">
                    <span className="pillar-id">{group.pillar}</span>
                    <span className="pillar-name">{group.name}</span>
                  </div>
                  <div className="entity-type-list">
                    {group.entities.map((entity) => (
                      <span className="entity-type" key={entity.type} title={entity.description}>
                        <span className="entity-type-name">{entity.type}</span>
                        <ClassificationBadge level={entity.classificationFloor} />
                        {entity.pii ? <span className="badge badge-warn">PII</span> : null}
                        <span className="entity-type-count">{group.counts[entity.type] ?? 0}</span>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Latest events"
          subtitle="most recently recorded in the fabric"
          actions={
            <Link className="btn btn-sm" to="/events">
              open stream
            </Link>
          }
          flush
        >
          {recent.loading ? (
            <div className="panel-body">
              <div className="list-plain">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div className="skeleton" key={index} style={{ height: 18 }} />
                ))}
              </div>
            </div>
          ) : recent.error ? (
            <div className="panel-body">
              <div className="notice" data-tone="danger">{recent.error.message}</div>
            </div>
          ) : (recent.data?.events.length ?? 0) === 0 ? (
            <div className="panel-body">
              <div className="text-muted">No events have been recorded for this tenant.</div>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Latest recorded events</caption>
                <thead>
                  <tr>
                    <th scope="col">Recorded</th>
                    <th scope="col">Type</th>
                    <th scope="col">Aggregate</th>
                    <th scope="col">Classification</th>
                  </tr>
                </thead>
                <tbody>
                  {latestEvents.map((event) => (
                    <tr key={event.eventId}>
                      <td className="nowrap" title={formatTimestamp(event.recordedAt)}>
                        {formatRelative(event.recordedAt)}
                      </td>
                      <td>
                        <EventTypeBadge eventType={event.eventType} />
                      </td>
                      <td className="mono-id truncate" style={{ maxWidth: 260 }}>
                        {event.aggregateType}:{event.aggregateId}
                      </td>
                      <td>
                        <ClassificationBadge level={event.classification?.level} caveats={event.classification?.caveats} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
