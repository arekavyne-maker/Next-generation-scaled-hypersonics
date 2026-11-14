import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchEvents } from '../api/client';
import type { EventEnvelope, EventPage } from '../api/types';
import { ClassificationBadge } from '../components/ClassificationBadge';
import { DataTable, type Column } from '../components/DataTable';
import { EventDetail, EventPayloadSummary, EventTypeBadge } from '../components/EventRow';
import { Panel } from '../components/Panel';
import { useAsync } from '../lib/useAsync';
import { formatRelative, formatTimestamp } from '../lib/format';

const QUICK_FILTERS = [
  'entity.*',
  'entity.relation.asserted',
  'test.*',
  'process.*',
  'model.*',
  'ingest.*',
  'access.*',
];

const PAGE_SIZE = 50;

export function EventStreamPage(): JSX.Element {
  const [textFilter, setTextFilter] = useState('');
  const [globs, setGlobs] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [olderPages, setOlderPages] = useState<EventPage[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<Error | null>(null);

  const typeFilter = useMemo(() => {
    const parts = [...globs];
    const text = textFilter.trim();
    if (text) parts.push(text);
    return parts.length > 0 ? parts.join(',') : undefined;
  }, [globs, textFilter]);

  const firstPage = useAsync(() => fetchEvents({ limit: PAGE_SIZE, types: typeFilter }), [typeFilter]);

  // A filter change invalidates the cursor chain: drop every page after the first.
  useEffect(() => {
    setOlderPages([]);
    setExpanded(null);
    setOlderError(null);
  }, [typeFilter]);

  const rows = useMemo(() => {
    const seen = new Map<string, EventEnvelope>();
    for (const event of [...(firstPage.data?.events ?? []), ...olderPages.flatMap((page) => page.events)]) {
      seen.set(event.eventId, event);
    }
    // Newest first regardless of the order the backend paginates in.
    return Array.from(seen.values()).sort(
      (a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt) || (a.eventId < b.eventId ? 1 : -1),
    );
  }, [firstPage.data, olderPages]);

  const cursor = olderPages.length > 0 ? olderPages[olderPages.length - 1]!.cursor : firstPage.data?.cursor;
  const lastPage = olderPages.length > 0 ? olderPages[olderPages.length - 1] : firstPage.data;
  const exhausted = !lastPage || lastPage.events.length < PAGE_SIZE;

  const toggleGlob = useCallback((glob: string) => {
    setGlobs((previous) => (previous.includes(glob) ? previous.filter((item) => item !== glob) : [...previous, glob]));
  }, []);

  const loadMore = useCallback(() => {
    if (!cursor || exhausted) return;
    setLoadingOlder(true);
    setOlderError(null);
    void fetchEvents({ after: cursor, limit: PAGE_SIZE, types: typeFilter })
      .then((page) => {
        setOlderPages((previous) => [...previous, page]);
      })
      .catch((cause: unknown) => {
        setOlderError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => setLoadingOlder(false));
  }, [cursor, exhausted, typeFilter]);

  const columns: Column<EventEnvelope>[] = [
    {
      key: 'recorded',
      header: 'Recorded',
      className: 'nowrap',
      render: (event) => <span title={formatTimestamp(event.recordedAt)}>{formatRelative(event.recordedAt)}</span>,
    },
    {
      key: 'type',
      header: 'Event type',
      render: (event) => <EventTypeBadge eventType={event.eventType} />,
    },
    {
      key: 'aggregate',
      header: 'Aggregate',
      render: (event) => (
        <span className="mono-id">
          {event.aggregateType}:<span className="text-muted">{event.aggregateId}</span>
        </span>
      ),
    },
    {
      key: 'actor',
      header: 'Actor',
      render: (event) => (
        <span className="mono-id">
          {event.actor.subjectId}
          {event.actor.displayName ? <span className="text-faint"> · {event.actor.displayName}</span> : null}
        </span>
      ),
    },
    {
      key: 'payload',
      header: 'Payload',
      render: (event) => <EventPayloadSummary event={event} />,
    },
    {
      key: 'classification',
      header: 'Classification',
      render: (event) => <ClassificationBadge level={event.classification?.level} caveats={event.classification?.caveats} />,
    },
  ];

  return (
    <div className="stack">
      <Panel
        title="Event stream"
        subtitle={typeFilter ? `filtered by ${typeFilter}` : 'every event type for tenant ngsh'}
        actions={
          <>
            <span className="chip">{rows.length} loaded</span>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                setTextFilter('');
                setGlobs([]);
              }}
              disabled={!typeFilter}
            >
              clear filters
            </button>
            <button type="button" className="btn btn-sm btn-primary" onClick={loadMore} disabled={!cursor || exhausted || loadingOlder}>
              {loadingOlder ? 'loading…' : 'load more'}
            </button>
          </>
        }
        flush
      >
        <div className="panel-body" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
          <div className="row">
            <label className="field" style={{ flex: '0 0 auto' }}>
              <span className="field-label">Type filter</span>
              <input
                type="search"
                className="filter-input"
                placeholder="test.*  ·  entity.relation"
                value={textFilter}
                onChange={(event) => setTextFilter(event.target.value)}
              />
            </label>

            <div className="row row-tight" role="group" aria-label="Quick type filters">
              {QUICK_FILTERS.map((glob) => (
                <button
                  key={glob}
                  type="button"
                  className="toggle"
                  aria-pressed={globs.includes(glob)}
                  onClick={() => toggleGlob(glob)}
                >
                  <span className="toggle-dot" aria-hidden="true" />
                  {glob}
                </button>
              ))}
            </div>
          </div>
          <p className="text-xs text-faint" style={{ marginTop: 8 }}>
            The fabric accepts a comma-separated glob list in <span className="mono">types</span>. Pages are chained with the{' '}
            <span className="mono">after</span> cursor returned by the previous response.
          </p>
          {olderError ? (
            <div className="notice" data-tone="danger" style={{ marginTop: 8 }}>
              {olderError.message}
            </div>
          ) : null}
        </div>

        <DataTable
          caption="Event log for tenant ngsh"
          columns={columns}
          rows={rows}
          rowKey={(event) => event.eventId}
          loading={firstPage.loading && rows.length === 0}
          error={firstPage.error}
          renderDetail={(event) => <EventDetail event={event} />}
          isExpanded={(event) => expanded === event.eventId}
          onToggle={(event) => setExpanded((previous) => (previous === event.eventId ? null : event.eventId))}
          emptyTitle="No events match this filter"
          emptyDetail="Adjust the type filter or clear it to see the full log for tenant ngsh."
        />
      </Panel>
    </div>
  );
}
