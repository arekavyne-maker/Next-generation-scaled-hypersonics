import type { HealthStatus } from '../api/types';

interface StatusTileProps {
  name: string;
  status: HealthStatus['status'];
  metric?: string;
  metricLabel?: string;
  detail?: string;
  /** Renders the "mock" marker when the value came from the fallback dataset. */
  mocked?: boolean;
}

/**
 * A single status tile. The left rule encodes the state (ok / degraded / down)
 * so the tile stays readable without relying on colour alone.
 */
export function StatusTile({ name, status, metric, metricLabel, detail, mocked = false }: StatusTileProps): JSX.Element {
  const statusLabel = status === 'ok' ? 'operational' : status;
  return (
    <article className="status-tile" data-status={status}>
      {mocked ? <span className="status-tile-mock">mock</span> : null}
      <div className="status-tile-head">
        <span className="status-tile-name">{name}</span>
        <span className={`badge ${status === 'ok' ? 'badge-ok' : status === 'degraded' ? 'badge-warn' : 'badge-danger'}`}>
          {statusLabel}
        </span>
      </div>
      {metric !== undefined ? (
        <div className="status-tile-metric">{metric}</div>
      ) : null}
      {metricLabel ? <div className="status-tile-label">{metricLabel}</div> : null}
      {detail ? (
        <div className="status-tile-detail" title={detail}>
          {detail}
        </div>
      ) : null}
    </article>
  );
}
