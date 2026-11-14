import { useEffect, useMemo, useState } from 'react';
import { fetchCoverage, listEntities } from '../api/client';
import type { CoverageResponse, NgsHEntity, VerifyingResult } from '../api/types';
import { ClassificationBadge } from '../components/ClassificationBadge';
import { Meter } from '../components/Meter';
import { Panel } from '../components/Panel';
import { useAsync } from '../lib/useAsync';
import { formatDate } from '../lib/format';

const OUTCOME_BADGE: Record<VerifyingResult['outcome'], string> = {
  PASS: 'badge-ok',
  FAIL: 'badge-danger',
  MARGINAL: 'badge-warn',
  INCONCLUSIVE: 'badge-info',
  NOT_RUN: 'badge-neutral',
};

function attributesOf(entity: NgsHEntity | undefined): Record<string, unknown> {
  return (entity?.attributes ?? {}) as Record<string, unknown>;
}

function textOf(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map((item) => String(item)).join(', ');
  if (value === undefined || value === null) return '—';
  return JSON.stringify(value);
}

export function RequirementsPage(): JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const requirements = useAsync(() => listEntities({ type: 'Requirement', limit: 200 }), []);
  const coverage = useAsync(() => fetchCoverage(selectedId ?? ''), [selectedId]);

  const list = requirements.data?.entities ?? [];

  useEffect(() => {
    if (selectedId === null && list.length > 0) setSelectedId(list[0]!.id);
  }, [list, selectedId]);

  const selected = useMemo(() => list.find((entity) => entity.id === selectedId), [list, selectedId]);
  const attrs = attributesOf(selected);
  const coverageData: CoverageResponse | null = coverage.data;

  return (
    <div className="grid grid-thread">
      <div className="stack">
        <Panel
          title="Verification coverage"
          subtitle={selectedId ? `${selectedId} · ${textOf(attrs['verificationMethod'])}` : 'select a requirement'}
          actions={
            coverageData ? (
              coverageData.verified ? (
                <span className="badge badge-ok">verified</span>
              ) : (
                <span className="badge badge-warn">not verified</span>
              )
            ) : null
          }
        >
          {coverage.error ? (
            <div className="notice" data-tone="danger">{coverage.error.message}</div>
          ) : coverage.loading && !coverageData ? (
            <div className="list-plain">
              {Array.from({ length: 4 }).map((_, index) => (
                <div className="skeleton" key={index} style={{ height: 18 }} />
              ))}
            </div>
          ) : coverageData ? (
            <div className="split-pane">
              <Meter
                value={coverageData.coverage}
                label="Evidence coverage"
                detail={`${coverageData.verifyingResults.length} verifying result${
                  coverageData.verifyingResults.length === 1 ? '' : 's'
                } · ${coverageData.gaps.length} gap${coverageData.gaps.length === 1 ? '' : 's'}`}
              />

              <div>
                <div className="status-tile-label" style={{ marginBottom: 6 }}>
                  Verifying test results
                </div>
                {coverageData.verifyingResults.length === 0 ? (
                  <div className="text-muted text-sm">
                    No test result verifies this requirement yet. The verification chain is open.
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table className="data-table">
                      <caption className="sr-only">Test results that verify the selected requirement</caption>
                      <thead>
                        <tr>
                          <th scope="col">Test result</th>
                          <th scope="col">Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coverageData.verifyingResults.map((result) => (
                          <tr key={result.id}>
                            <td className="mono-id">{result.id}</td>
                            <td>
                              <span className={`badge ${OUTCOME_BADGE[result.outcome]}`}>{result.outcome}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div>
                <div className="status-tile-label" style={{ marginBottom: 6 }}>
                  Coverage gaps
                </div>
                {coverageData.gaps.length === 0 ? (
                  <div className="notice" data-tone="ok">
                    No gaps: the requirement is discharged by passing, admissible test evidence.
                  </div>
                ) : (
                  <ul className="list-plain">
                    {coverageData.gaps.map((gap) => (
                      <li key={gap}>{gap}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <div className="text-muted text-sm">Select a requirement to compute its verification coverage.</div>
          )}
        </Panel>

        <Panel title="Requirement" subtitle={selectedId ?? '—'}>
          {!selected ? (
            <div className="text-muted text-sm">Loading requirement record…</div>
          ) : (
            <dl className="kv">
              <dt>Statement</dt>
              <dd>{textOf(attrs['statement'])}</dd>
              <dt>Type</dt>
              <dd>{textOf(attrs['reqType'])}</dd>
              <dt>Method</dt>
              <dd>{textOf(attrs['verificationMethod'])}</dd>
              <dt>Lifecycle</dt>
              <dd>
                <span className="badge badge-neutral">{textOf(attrs['status'])}</span>{' '}
                <span className="badge badge-neutral">{textOf(attrs['verificationStatus'])}</span>
              </dd>
              <dt>Allocated to</dt>
              <dd className="mono-id">{textOf(attrs['allocatedToIds'])}</dd>
              <dt>Parent</dt>
              <dd className="mono-id">{textOf(attrs['parentId'])}</dd>
              <dt>Acceptance</dt>
              <dd>{textOf(attrs['acceptanceCriteria'])}</dd>
              <dt>Cost drivers</dt>
              <dd className="mono-id">{textOf(attrs['costDrivers'])}</dd>
              <dt>Classification</dt>
              <dd>
                <ClassificationBadge level={selected.classification?.level} caveats={selected.classification?.caveats} />
              </dd>
              <dt>Baselined</dt>
              <dd>{formatDate(selected.createdAt)}</dd>
            </dl>
          )}
        </Panel>
      </div>

      <Panel title="Requirements" subtitle={`${list.length} baselined`} flush>
        {requirements.loading ? (
          <div className="panel-body">
            <div className="list-plain">
              {Array.from({ length: 8 }).map((_, index) => (
                <div className="skeleton" key={index} style={{ height: 16 }} />
              ))}
            </div>
          </div>
        ) : requirements.error ? (
          <div className="panel-body">
            <div className="notice" data-tone="danger">{requirements.error.message}</div>
          </div>
        ) : list.length === 0 ? (
          <div className="panel-body text-muted text-sm">No requirements are registered for this tenant.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">Requirements in the shared ontology</caption>
              <thead>
                <tr>
                  <th scope="col">Id</th>
                  <th scope="col">Statement</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {list.map((requirement) => {
                  const requirementAttrs = attributesOf(requirement);
                  const isSelected = requirement.id === selectedId;
                  return (
                    <tr key={requirement.id} className={isSelected ? 'is-selected' : undefined}>
                      <td className="nowrap">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          aria-pressed={isSelected}
                          onClick={() => setSelectedId(requirement.id)}
                          style={{ fontFamily: 'var(--font-mono)', padding: 0, minHeight: 0 }}
                        >
                          {requirement.id}
                        </button>
                      </td>
                      <td className="truncate" style={{ maxWidth: 320 }} title={textOf(requirementAttrs['statement'])}>
                        {textOf(requirementAttrs['statement'])}
                      </td>
                      <td className="nowrap">
                        <span className="badge badge-neutral">{textOf(requirementAttrs['verificationStatus'])}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
