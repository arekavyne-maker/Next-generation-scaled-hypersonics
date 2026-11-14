import type { EventEnvelope } from '../api/types';
import { ClassificationBadge } from './ClassificationBadge';
import { CopyableText } from './CopyableText';
import { JsonViewer } from './JsonViewer';
import { formatBytes, formatRelative, formatTimestamp } from '../lib/format';

const EVENT_FAMILY_COLORS: Record<string, string> = {
  entity: 'badge-info',
  test: 'badge-ok',
  process: 'badge-warn',
  model: 'badge-violet',
  ingest: 'badge-neutral',
  access: 'badge-accent',
};

function familyOf(eventType: string): string {
  return eventType.split('.')[0] ?? 'entity';
}

/** Compact badge for an event type, coloured by family. */
export function EventTypeBadge({ eventType }: { eventType: string }): JSX.Element {
  const family = familyOf(eventType);
  return <span className={`badge ${EVENT_FAMILY_COLORS[family] ?? 'badge-neutral'}`}>{eventType}</span>;
}

/** One-line summary of an event payload, used in the table body. */
export function EventPayloadSummary({ event }: { event: EventEnvelope }): JSX.Element {
  const payload = event.payload ?? {};
  const keys = Object.keys(payload);
  const head = keys.slice(0, 3).join(', ');
  return (
    <span className="text-muted text-xs truncate" title={keys.join(', ')}>
      {head || 'empty payload'}
    </span>
  );
}

/** The expandable body of an event row: envelope metadata plus the raw payload. */
export function EventDetail({ event }: { event: EventEnvelope }): JSX.Element {
  const attachments = event.attachments ?? [];
  return (
    <div className="split-pane">
      <div>
        <dl className="kv">
          <dt>Event ID</dt>
          <dd>
            <CopyableText value={event.eventId} label="Event ID" />
          </dd>
          <dt>Event type</dt>
          <dd>
            <EventTypeBadge eventType={event.eventType} /> <span className="text-faint text-xs">v{event.eventVersion}</span>
          </dd>
          <dt>Aggregate</dt>
          <dd className="mono-id">
            {event.aggregateType}:{event.aggregateId}
          </dd>
          <dt>Sequence</dt>
          <dd className="mono-id">{event.sequence}</dd>
          <dt>Occurred</dt>
          <dd>
            {formatTimestamp(event.occurredAt)} <span className="text-faint text-xs">({formatRelative(event.occurredAt)})</span>
          </dd>
          <dt>Recorded</dt>
          <dd>
            {formatTimestamp(event.recordedAt)} <span className="text-faint text-xs">({formatRelative(event.recordedAt)})</span>
          </dd>
          <dt>Actor</dt>
          <dd>
            <span className="mono-id">{event.actor.subjectId}</span>
            {event.actor.displayName ? <span className="text-muted"> · {event.actor.displayName}</span> : null}
            <span className="chip" style={{ marginLeft: 6 }}>
              {event.actor.kind}
            </span>
            {event.actor.clearance ? <span className="chip">{event.actor.clearance}</span> : null}
          </dd>
          <dt>Classification</dt>
          <dd>
            <ClassificationBadge level={event.classification?.level} caveats={event.classification?.caveats} />
          </dd>
          <dt>Tenant</dt>
          <dd className="mono-id">
            {event.tenant}
            {event.program ? ` / ${event.program}` : ''}
          </dd>
          {event.correlationId ? (
            <>
              <dt>Correlation</dt>
              <dd className="mono-id">{event.correlationId}</dd>
            </>
          ) : null}
        </dl>
      </div>

      <div>
        <div className="status-tile-label" style={{ marginBottom: 6 }}>
          Payload
        </div>
        <JsonViewer value={event.payload} defaultDepth={2} label={`Payload of ${event.eventId}`} />
      </div>

      {attachments.length > 0 ? (
        <div>
          <div className="status-tile-label" style={{ marginBottom: 6 }}>
            Attachments
          </div>
          <ul className="list-plain">
            {attachments.map((attachment) => (
              <li key={attachment.uri}>
                <span className="mono-list">{attachment.uri}</span>
                <span className="text-faint text-xs">
                  {attachment.mediaType ?? 'application/octet-stream'} · {formatBytes(attachment.sizeBytes)}
                </span>
                <CopyableText value={attachment.sha256} display={attachment.sha256.slice(0, 16)} label="Attachment digest" />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
