import { useEffect, useMemo, useState } from 'react';
import { fetchLedger, verifyLedger } from '../api/client';
import type { AuditEntry, LedgerPage } from '../api/types';
import { CopyableText } from '../components/CopyableText';
import { DataTable, type Column } from '../components/DataTable';
import { Panel } from '../components/Panel';
import { useAsync } from '../lib/useAsync';
import { formatTimestamp } from '../lib/format';

const DECISION_BADGE: Record<AuditEntry['decision'], string> = {
  ALLOW: 'badge-ok',
  DENY: 'badge-danger',
  INDETERMINATE: 'badge-warn',
};

const PAGE_SIZE = 50;

export function AuditPage(): JSX.Element {
  const [olderPages, setOlderPages] = useState<LedgerPage[]>([]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<Error | null>(null);

  const verification = useAsync(() => verifyLedger(), []);
  const ledger = useAsync(() => fetchLedger({ limit: PAGE_SIZE }), []);

  useEffect(() => {
    setOlderPages([]);
    setOlderError(null);
  }, []);

  const rows = useMemo(() => {
    const head = ledger.data?.entries ?? [];
    const tail = olderPages.flatMap((page) => page.entries);
    return [...head, ...tail];
  }, [ledger.data, olderPages]);

  const cursor = olderPages.length > 0 ? olderPages[olderPages.length - 1]!.cursor : ledger.data?.cursor;
  const lastPage = olderPages.length > 0 ? olderPages[olderPages.length - 1] : ledger.data;
  const exhausted = !lastPage || lastPage.entries.length < PAGE_SIZE;

  const loadMore = (): void => {
    if (!cursor || exhausted) return;
    setLoadingOlder(true);
    setOlderError(null);
    void fetchLedger({ after: cursor, limit: PAGE_SIZE })
      .then((page) => setOlderPages((previous) => [...previous, page]))
      .catch((cause: unknown) => setOlderError(cause instanceof Error ? cause : new Error(String(cause))))
      .finally(() => setLoadingOlder(false));
  };

  const columns: Column<AuditEntry>[] = [
    {
      key: 'seq',
      header: 'Seq',
      className: 'num',
      render: (entry) => entry.seq,
    },
    {
      key: 'timestamp',
      header: 'Timestamp',
      className: 'nowrap',
      render: (entry) => formatTimestamp(entry.timestamp),
    },
    {
      key: 'eventType',
      header: 'Event',
      render: (entry) => <span className="mono-id text-xs">{entry.eventType}</span>,
    },
    {
      key: 'subject',
      header: 'Subject',
      render: (entry) => <span className="mono-id">{entry.subject}</span>,
    },
    {
      key: 'action',
      header: 'Action',
      render: (entry) => <span className="chip">{entry.action}</span>,
    },
    {
      key: 'resource',
      header: 'Resource',
      render: (entry) => <span className="mono-id">{entry.resource}</span>,
    },
    {
      key: 'decision',
      header: 'Decision',
      render: (entry) => <span className={`badge ${DECISION_BADGE[entry.decision]}`}>{entry.decision}</span>,
    },
    {
      key: 'hash',
      header: 'Hash',
      render: (entry) => (
        <CopyableText value={entry.hash} display={`${entry.hash.slice(0, 10)}…${entry.hash.slice(-4)}`} label={`Hash of ledger entry ${entry.seq}`} />
      ),
    },
    {
      key: 'prevHash',
      header: 'Prev hash',
      render: (entry) => (
        <CopyableText
          value={entry.prevHash}
          display={entry.prevHash === '0'.repeat(64) ? 'genesis' : `${entry.prevHash.slice(0, 10)}…${entry.prevHash.slice(-4)}`}
          label={`Previous hash of ledger entry ${entry.seq}`}
        />
      ),
    },
  ];

  const verificationData = verification.data;
  const bannerTone = verification.error ? 'danger' : verificationData?.valid ? 'ok' : 'danger';
  const bannerText = verification.error
    ? `Chain verification failed: ${verification.error.message}`
    : verificationData?.valid
      ? `Chain verified — ${verificationData.checked} entries, head ${verificationData.head.slice(0, 16)}…`
      : `Chain broken at seq ${verificationData?.brokenAt ?? '?'} — head ${verificationData?.head.slice(0, 16) ?? '—'}…`;

  return (
    <div className="stack">
      <div className="notice" data-tone={bannerTone} role="status">
        <span>
          {verification.loading && !verificationData ? 'Verifying ledger chain…' : bannerText}
        </span>
        <span className="topbar-spacer" />
        <button type="button" className="btn btn-sm" onClick={verification.reload} aria-label="Re-run chain verification">
          re-verify
        </button>
      </div>

      <Panel
        title="Audit ledger"
        subtitle="hash-chained, append-only record of every decision"
        actions={
          <>
            <span className="chip">{rows.length} entries</span>
            <button type="button" className="btn btn-sm btn-primary" onClick={loadMore} disabled={!cursor || exhausted || loadingOlder}>
              {loadingOlder ? 'loading…' : 'load more'}
            </button>
          </>
        }
        flush
      >
        {olderError ? (
          <div className="panel-body">
            <div className="notice" data-tone="danger">{olderError.message}</div>
          </div>
        ) : null}
        <DataTable
          caption="Audit ledger entries in sequence order"
          columns={columns}
          rows={rows}
          rowKey={(entry) => String(entry.seq)}
          loading={ledger.loading && rows.length === 0}
          error={ledger.error}
          emptyTitle="The ledger is empty"
          emptyDetail="No entries have been written for this deployment."
        />
      </Panel>

      <div className="grid grid-two">
        <Panel title="Chain model" subtitle="how each entry is bound to the previous one">
          <dl className="kv">
            <dt>Genesis</dt>
            <dd className="mono-id">{'0'.repeat(64)}</dd>
            <dt>Binding</dt>
            <dd className="text-sm text-muted">
              Each entry stores <span className="mono">prevHash</span>, the digest of the entry before it, together with its own{' '}
              <span className="mono">hash</span>. Any edit to an historical entry invalidates every digest after it.
            </dd>
            <dt>Head</dt>
            <dd className="mono-id">{verificationData?.head ?? '—'}</dd>
            <dt>Checked</dt>
            <dd className="mono-id">{verificationData?.checked ?? '—'}</dd>
          </dl>
        </Panel>

        <Panel title="Most recent decisions" subtitle="tail of the chain">
          {rows.length === 0 ? (
            <div className="text-muted text-sm">No entries loaded.</div>
          ) : (
            <ul className="list-plain">
              {rows
                .slice()
                .reverse()
                .slice(0, 6)
                .map((entry) => (
                  <li key={entry.seq}>
                    <span className={`badge ${DECISION_BADGE[entry.decision]}`}>{entry.decision}</span>
                    <span className="mono-id text-xs">
                      {entry.subject} {entry.action} {entry.resource}
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
