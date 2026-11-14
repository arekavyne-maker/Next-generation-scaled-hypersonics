import { useMemo, useState } from 'react';
import { fetchLedger, fetchPolicies, submitDecision } from '../api/client';
import type {
  ActorKind,
  ClassificationLevel,
  ClearanceLevel,
  Citizenship,
  PolicyDecisionRequest,
  PolicyDecisionResponse,
  PolicySummary,
} from '../api/types';
import { DataTable, type Column } from '../components/DataTable';
import { Panel } from '../components/Panel';
import { useAsync } from '../lib/useAsync';
import { formatTimestamp } from '../lib/format';

const CLEARANCES: ClearanceLevel[] = ['NONE', 'SECRET', 'TOP SECRET', 'SCI-CLEARED'];
const CITIZENSHIPS: Citizenship[] = ['US', 'ALLIED', 'FOREIGN', 'UNKNOWN'];
const KINDS: ActorKind[] = ['user', 'service', 'device', 'edge-agent', 'anonymous'];
const CLASSIFICATIONS: ClassificationLevel[] = ['UNCLASSIFIED', 'CUI', 'RESTRICTED', 'SECRET', 'TOP SECRET'];
const ACTIONS = ['read', 'write', 'export', 'train'];

const DECISION_BADGE: Record<PolicyDecisionResponse['decision'], string> = {
  ALLOW: 'badge-ok',
  DENY: 'badge-danger',
  INDETERMINATE: 'badge-warn',
};

interface DecisionRecord {
  timestamp: string;
  subject: string;
  action: string;
  resource: string;
  decision: PolicyDecisionResponse['decision'];
  policyId: string;
  obligations: string[];
  reason: string;
  origin: 'session' | 'ledger';
}

const INITIAL_FORM = {
  subjectId: 'PER:01J8ZV8Q4B',
  kind: 'user' as ActorKind,
  clearance: 'TOP SECRET' as ClearanceLevel,
  citizenship: 'US' as Citizenship,
  programs: 'NGSH-SHY',
  resourceType: 'TestResult',
  resourceId: 'TR:01J8ZW4C7T2',
  resourceClassification: 'CUI' as ClassificationLevel,
  action: 'read',
};

export function AccessPage(): JSX.Element {
  const [form, setForm] = useState(INITIAL_FORM);
  const [decision, setDecision] = useState<PolicyDecisionResponse | null>(null);
  const [submitted, setSubmitted] = useState<PolicyDecisionRequest | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [history, setHistory] = useState<DecisionRecord[]>([]);

  const policies = useAsync(() => fetchPolicies(), []);
  // The ledger tail is the platform's own access history.
  const ledger = useAsync(() => fetchLedger({ limit: 50 }), []);

  const ledgerDecisions = useMemo<DecisionRecord[]>(
    () =>
      (ledger.data?.entries ?? [])
        .filter((entry) => entry.eventType === 'access.decision.recorded')
        .slice()
        .reverse()
        .map((entry) => ({
          timestamp: entry.timestamp,
          subject: entry.subject,
          action: entry.action,
          resource: entry.resource,
          decision: entry.decision,
          policyId: '—',
          obligations: entry.decision === 'ALLOW' ? ['log-access', 'no-export'] : [],
          reason: entry.reason,
          origin: 'ledger' as const,
        })),
    [ledger.data],
  );

  const recentDecisions = useMemo(
    () => [...history, ...ledgerDecisions].slice(0, 60),
    [history, ledgerDecisions],
  );

  const update = <K extends keyof typeof INITIAL_FORM>(key: K, value: (typeof INITIAL_FORM)[K]): void => {
    setForm((previous) => ({ ...previous, [key]: value }));
  };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const request: PolicyDecisionRequest = {
      subject: {
        subjectId: form.subjectId.trim(),
        kind: form.kind,
        clearance: form.clearance,
        citizenship: form.citizenship,
        programs: form.programs
          .split(',')
          .map((program) => program.trim())
          .filter(Boolean),
      },
      resource: {
        type: form.resourceType.trim(),
        id: form.resourceId.trim(),
        classification: form.resourceClassification,
      },
      action: form.action,
      context: { tenant: 'ngsh', program: 'NGSH-SHY', evaluatedBy: 'ngsh-control-console' },
    };

    setSubmitting(true);
    setError(null);
    void submitDecision(request)
      .then((result) => {
        setDecision(result);
        setSubmitted(request);
        setHistory((previous) => [
          {
            timestamp: new Date().toISOString(),
            subject: request.subject.subjectId,
            action: request.action,
            resource: `${request.resource.type}:${request.resource.id}`,
            decision: result.decision,
            policyId: result.policyId,
            obligations: result.obligations,
            reason: result.reason,
            origin: 'session',
          },
          ...previous,
        ]);
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause : new Error(String(cause))))
      .finally(() => setSubmitting(false));
  };

  const policyRows = policies.data?.policies ?? [];

  const columns: Column<DecisionRecord>[] = [
    {
      key: 'timestamp',
      header: 'Evaluated',
      className: 'nowrap',
      render: (record) => formatTimestamp(record.timestamp),
    },
    { key: 'subject', header: 'Subject', render: (record) => <span className="mono-id">{record.subject}</span> },
    { key: 'action', header: 'Action', render: (record) => <span className="chip">{record.action}</span> },
    { key: 'resource', header: 'Resource', render: (record) => <span className="mono-id">{record.resource}</span> },
    {
      key: 'decision',
      header: 'Decision',
      render: (record) => <span className={`badge ${DECISION_BADGE[record.decision]}`}>{record.decision}</span>,
    },
    { key: 'policy', header: 'Policy', render: (record) => <span className="mono-id text-xs">{record.policyId}</span> },
    {
      key: 'origin',
      header: 'Source',
      render: (record) => (
        <span className="chip">{record.origin === 'session' ? 'this console' : 'audit ledger'}</span>
      ),
    },
    { key: 'reason', header: 'Reason', render: (record) => <span className="text-muted text-xs">{record.reason}</span> },
  ];

  const obligationList = useMemo(() => decision?.obligations ?? [], [decision]);

  return (
    <div className="grid grid-thread">
      <div className="stack">
        <Panel title="Policy decision" subtitle="evaluate a subject against a resource">
          <form onSubmit={submit}>
            <div className="split-pane">
              <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
                <legend className="status-tile-label" style={{ marginBottom: 8 }}>
                  Subject
                </legend>
                <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                  <label className="field">
                    <span className="field-label">Subject id</span>
                    <input
                      type="text"
                      value={form.subjectId}
                      onChange={(event) => update('subjectId', event.target.value)}
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Kind</span>
                    <select value={form.kind} onChange={(event) => update('kind', event.target.value as ActorKind)}>
                      {KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Clearance</span>
                    <select
                      value={form.clearance}
                      onChange={(event) => update('clearance', event.target.value as ClearanceLevel)}
                    >
                      {CLEARANCES.map((clearance) => (
                        <option key={clearance} value={clearance}>
                          {clearance}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Citizenship</span>
                    <select
                      value={form.citizenship}
                      onChange={(event) => update('citizenship', event.target.value as Citizenship)}
                    >
                      {CITIZENSHIPS.map((citizenship) => (
                        <option key={citizenship} value={citizenship}>
                          {citizenship}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field" style={{ gridColumn: '1 / -1' }}>
                    <span className="field-label">Programs</span>
                    <input
                      type="text"
                      value={form.programs}
                      onChange={(event) => update('programs', event.target.value)}
                      placeholder="comma separated program tags"
                    />
                  </label>
                </div>
              </fieldset>

              <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
                <legend className="status-tile-label" style={{ marginBottom: 8 }}>
                  Resource
                </legend>
                <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                  <label className="field">
                    <span className="field-label">Type</span>
                    <input
                      type="text"
                      value={form.resourceType}
                      onChange={(event) => update('resourceType', event.target.value)}
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Id</span>
                    <input
                      type="text"
                      value={form.resourceId}
                      onChange={(event) => update('resourceId', event.target.value)}
                      required
                    />
                  </label>
                  <label className="field">
                    <span className="field-label">Classification</span>
                    <select
                      value={form.resourceClassification}
                      onChange={(event) => update('resourceClassification', event.target.value as ClassificationLevel)}
                    >
                      {CLASSIFICATIONS.map((level) => (
                        <option key={level} value={level}>
                          {level}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span className="field-label">Action</span>
                    <select value={form.action} onChange={(event) => update('action', event.target.value)}>
                      {ACTIONS.map((action) => (
                        <option key={action} value={action}>
                          {action}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </fieldset>

              <div className="row row-end">
                <button type="button" className="btn" onClick={() => setForm(INITIAL_FORM)}>
                  reset
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'evaluating…' : 'evaluate decision'}
                </button>
              </div>
            </div>
          </form>
        </Panel>

        <Panel
          title="Outcome"
          subtitle={submitted ? `${submitted.subject.subjectId} · ${submitted.action} ${submitted.resource.type}:${submitted.resource.id}` : 'no evaluation yet'}
          actions={
            decision ? (
              <span className={`badge ${DECISION_BADGE[decision.decision]}`}>{decision.decision}</span>
            ) : null
          }
        >
          {error ? (
            <div className="notice" data-tone="danger">{error.message}</div>
          ) : !decision ? (
            <div className="text-muted text-sm">
              Submit the form to evaluate the subject against the policy set. The decision, the matched policy and any obligations are
              returned by the policy service.
            </div>
          ) : (
            <div className="split-pane">
              <dl className="kv">
                <dt>Decision</dt>
                <dd>
                  <span className={`badge ${DECISION_BADGE[decision.decision]}`}>{decision.decision}</span>
                </dd>
                <dt>Policy</dt>
                <dd className="mono-id">{decision.policyId}</dd>
                <dt>Reason</dt>
                <dd>{decision.reason}</dd>
                <dt>Obligations</dt>
                <dd>
                  {obligationList.length === 0 ? (
                    <span className="text-muted text-sm">None attached to this outcome.</span>
                  ) : (
                    <div className="row row-tight">
                      {obligationList.map((obligation) => (
                        <span className="chip" key={obligation}>
                          {obligation}
                        </span>
                      ))}
                    </div>
                  )}
                </dd>
              </dl>
            </div>
          )}
        </Panel>

        <Panel
          title="Recent decisions"
          subtitle={`${recentDecisions.length} recorded — ${history.length} from this session`}
          flush
        >
          <DataTable
            caption="Access decisions recorded by the platform and by this console"
            columns={columns}
            rows={recentDecisions}
            rowKey={(record) => `${record.origin}-${record.timestamp}-${record.resource}`}
            loading={ledger.loading && recentDecisions.length === 0}
            error={ledger.error}
            emptyTitle="No access decisions recorded"
            emptyDetail="Submit the policy form to record a decision, or wait for the audit ledger to accumulate entries."
          />
        </Panel>
      </div>

      <Panel title="Policy set" subtitle={`${policyRows.length} rules`} flush>
        {policies.loading ? (
          <div className="panel-body">
            <div className="list-plain">
              {Array.from({ length: 5 }).map((_, index) => (
                <div className="skeleton" key={index} style={{ height: 16 }} />
              ))}
            </div>
          </div>
        ) : policies.error ? (
          <div className="panel-body">
            <div className="notice" data-tone="danger">{policies.error.message}</div>
          </div>
        ) : policyRows.length === 0 ? (
          <div className="panel-body text-muted text-sm">The policy service returned no rules.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <caption className="sr-only">Policies loaded from the policy service</caption>
              <thead>
                <tr>
                  <th scope="col">Policy</th>
                  <th scope="col">Effect</th>
                  <th scope="col">Priority</th>
                </tr>
              </thead>
              <tbody>
                {policyRows.map((policy: PolicySummary) => (
                  <tr key={policy.id}>
                    <td>
                      <div className="mono-id text-xs">{policy.id}</div>
                      <div className="text-muted text-xs">{policy.description}</div>
                    </td>
                    <td>
                      <span className={`badge ${policy.effect === 'ALLOW' ? 'badge-ok' : 'badge-danger'}`}>{policy.effect}</span>
                    </td>
                    <td className="num">{policy.priority}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
