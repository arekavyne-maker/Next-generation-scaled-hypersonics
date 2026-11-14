import { useEffect, useMemo, useState } from 'react';
import { fetchEntity, fetchRegistry, fetchTrace, listEntities } from '../api/client';
import type { EntityWithRelations, TraceEdge, TraceNode, TraceResponse } from '../api/types';
import { ClassificationBadge } from '../components/ClassificationBadge';
import { JsonViewer } from '../components/JsonViewer';
import { Panel } from '../components/Panel';
import { TraceGraph } from '../components/TraceGraph';
import { useAsync } from '../lib/useAsync';
import { entityColor, relationColor } from '../lib/palette';

const DEFAULT_ROOT = 'TestResult:TR:01J8ZW4C7T2';

function splitRoot(value: string): { type: string; id: string } {
  const trimmed = value.trim();
  const separator = trimmed.indexOf(':');
  if (separator <= 0) return { type: '', id: trimmed };
  return { type: trimmed.slice(0, separator), id: trimmed.slice(separator + 1) };
}

export function ThreadPage(): JSX.Element {
  const [rootInput, setRootInput] = useState(DEFAULT_ROOT);
  const [depth, setDepth] = useState(3);
  const [relationTypes, setRelationTypes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<TraceNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<TraceEdge | null>(null);
  const [appliedRoot, setAppliedRoot] = useState(DEFAULT_ROOT);

  const registry = useAsync(() => fetchRegistry(), []);
  const entities = useAsync(() => listEntities({ limit: 500 }), []);

  const trace = useAsync(() => fetchTrace({ root: appliedRoot, depth, relationTypes }), [appliedRoot, depth, relationTypes]);

  const suggestions = useMemo(() => {
    const list = entities.data?.entities ?? [];
    return list
      .map((entity) => `${entity.type}:${entity.id}`)
      .sort((a, b) => a.localeCompare(b))
      .slice(0, 250);
  }, [entities.data]);

  const selectedEntity = useAsync<EntityWithRelations | null>(async () => {
    if (!selectedNode) return null;
    const parsed = splitRoot(`${selectedNode.type}:${selectedNode.id}`);
    if (!parsed.id) return null;
    return fetchEntity(parsed.type, parsed.id);
  }, [selectedNode?.id, selectedNode?.type]);

  useEffect(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, [appliedRoot, depth, relationTypes]);

  const toggleRelation = (type: string): void => {
    setRelationTypes((previous) =>
      previous.includes(type) ? previous.filter((item) => item !== type) : [...previous, type],
    );
  };

  const relationTypesAvailable = registry.data?.relations.map((relation) => relation.type) ?? [];

  const nodeDetail = selectedNode;
  const nodeRelations = useMemo(() => {
    const relations = selectedEntity.data?.relations ?? [];
    if (!nodeDetail) return [];
    return relations.filter(
      (relation) => relation.from.id === nodeDetail.id || relation.to.id === nodeDetail.id,
    );
  }, [selectedEntity.data, nodeDetail]);

  const traceData: TraceResponse | null = trace.data;

  return (
    <div className="grid grid-thread">
      <div className="stack">
        <Panel title="Trace explorer" subtitle={`root ${appliedRoot} · depth ${depth}`}>
          <div className="row" style={{ alignItems: 'flex-end' }}>
            <label className="field" style={{ flex: '1 1 320px' }}>
              <span className="field-label">Root entity</span>
              <input
                type="text"
                list="ngsh-entity-suggestions"
                placeholder="Type:id — e.g. TestResult:TR:01J8ZW4C7T2"
                value={rootInput}
                onChange={(event) => setRootInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') setAppliedRoot(rootInput.trim());
                }}
              />
              <datalist id="ngsh-entity-suggestions">
                {suggestions.map((suggestion) => (
                  <option key={suggestion} value={suggestion} />
                ))}
              </datalist>
            </label>

            <label className="field" style={{ flex: '0 0 150px' }}>
              <span className="field-label">
                Depth <span className="mono">{depth}</span>
              </span>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={depth}
                onChange={(event) => setDepth(Number(event.target.value))}
                aria-label="Trace depth in hops"
              />
            </label>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setAppliedRoot(rootInput.trim())}
              disabled={rootInput.trim().length === 0}
            >
              trace
            </button>
          </div>

          <div style={{ marginTop: 12 }}>
            <div className="status-tile-label" style={{ marginBottom: 6 }}>
              Relation types
            </div>
            <div className="row row-tight" role="group" aria-label="Relation type filter">
              {relationTypesAvailable.map((type) => {
                const active = relationTypes.length === 0 || relationTypes.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    className="toggle"
                    aria-pressed={relationTypes.includes(type)}
                    style={active ? { borderColor: relationColor(type) } : { opacity: 0.55 }}
                    onClick={() => toggleRelation(type)}
                    title={
                      relationTypes.length === 0
                        ? 'All relation types are included. Activate to restrict.'
                        : relationTypes.includes(type)
                          ? 'Included in the trace'
                          : 'Excluded from the trace'
                    }
                  >
                    <span className="toggle-dot" aria-hidden="true" style={{ background: relationColor(type) }} />
                    {type}
                  </button>
                );
              })}
            </div>
            {relationTypes.length > 0 ? (
              <div className="text-xs text-faint" style={{ marginTop: 6 }}>
                Filtering to {relationTypes.length} relation type{relationTypes.length === 1 ? '' : 's'}.{' '}
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRelationTypes([])}>
                  clear
                </button>
              </div>
            ) : (
              <div className="text-xs text-faint" style={{ marginTop: 6 }}>
                No filter applied — every relation type is traversed.
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title="Digital thread"
          subtitle={traceData ? `${traceData.nodes.length} nodes · ${traceData.edges.length} edges` : 'awaiting trace'}
          actions={
            trace.loading ? (
              <span className="chip">tracing…</span>
            ) : (
              <span className="chip">{traceData?.paths.length ?? 0} paths</span>
            )
          }
          flush
        >
          {trace.error ? (
            <div className="panel-body">
              <div className="notice" data-tone="danger">{trace.error.message}</div>
            </div>
          ) : trace.loading && !traceData ? (
            <div className="panel-body">
              <div className="list-plain">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div className="skeleton" key={index} style={{ height: 18 }} />
                ))}
              </div>
            </div>
          ) : traceData && traceData.nodes.length === 0 ? (
            <div className="panel-body">
              <div className="notice" data-tone="warn">
                No entity matched <span className="mono">{appliedRoot}</span>. Pick a root from the suggestions or widen the relation
                filter.
              </div>
            </div>
          ) : traceData ? (
            <TraceGraph
              trace={traceData}
              selectedNodeId={selectedNode?.id ?? null}
              selectedEdgeKey={selectedEdge ? `${selectedEdge.from}->${selectedEdge.to}:${selectedEdge.type}` : null}
              onSelectNode={(node) => {
                setSelectedNode(node);
                setSelectedEdge(null);
              }}
              onSelectEdge={(edge) => {
                setSelectedEdge(edge);
                setSelectedNode(null);
              }}
            />
          ) : null}
        </Panel>
      </div>

      <div className="stack">
        <Panel title="Selection" subtitle={selectedNode ? 'entity' : selectedEdge ? 'relation' : 'nothing selected'}>
          {selectedNode ? (
            <div className="split-pane">
              <dl className="kv">
                <dt>Type</dt>
                <dd>
                  <span className="chip" style={{ color: entityColor(selectedNode.type), borderColor: entityColor(selectedNode.type) }}>
                    {selectedNode.type}
                  </span>
                </dd>
                <dt>Label</dt>
                <dd>{selectedNode.label}</dd>
                <dt>Id</dt>
                <dd className="mono-id">{selectedNode.id}</dd>
                <dt>Classification</dt>
                <dd>
                  <ClassificationBadge level={selectedNode.classification?.level} caveats={selectedNode.classification?.caveats} />
                </dd>
              </dl>

              <div>
                <div className="status-tile-label" style={{ marginBottom: 6 }}>
                  Relations ({nodeRelations.length})
                </div>
                {nodeRelations.length === 0 ? (
                  <div className="text-muted text-sm">No relations asserted on this entity.</div>
                ) : (
                  <ul className="list-plain">
                    {nodeRelations.map((relation) => (
                      <li key={relation.id}>
                        <span className="chip" style={{ color: relationColor(relation.type), borderColor: relationColor(relation.type) }}>
                          {relation.type}
                        </span>
                        <span className="mono-id">
                          {relation.from.id === selectedNode.id ? `→ ${relation.to.id}` : `← ${relation.from.id}`}
                        </span>
                        {relation.confidence !== undefined ? (
                          <span className="text-faint text-xs">conf {relation.confidence.toFixed(2)}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {selectedEntity.loading ? (
                <div className="skeleton" style={{ height: 90 }} />
              ) : selectedEntity.data ? (
                <div>
                  <div className="status-tile-label" style={{ marginBottom: 6 }}>
                    Entity body
                  </div>
                  <JsonViewer value={selectedEntity.data.entity.attributes} defaultDepth={1} label={`Attributes of ${selectedNode.id}`} />
                </div>
              ) : null}
            </div>
          ) : selectedEdge ? (
            <dl className="kv">
              <dt>Type</dt>
              <dd>
                <span className="chip" style={{ color: relationColor(selectedEdge.type), borderColor: relationColor(selectedEdge.type) }}>
                  {selectedEdge.type}
                </span>
              </dd>
              <dt>From</dt>
              <dd className="mono-id">{selectedEdge.from}</dd>
              <dt>To</dt>
              <dd className="mono-id">{selectedEdge.to}</dd>
              <dt>Confidence</dt>
              <dd className="mono-id">
                {selectedEdge.confidence !== undefined ? selectedEdge.confidence.toFixed(3) : 'not asserted'}
              </dd>
              <dt>Styling</dt>
              <dd>
                {selectedEdge.confidence !== undefined && selectedEdge.confidence < 0.6 ? (
                  <span className="badge badge-warn">dashed · low confidence</span>
                ) : (
                  <span className="badge badge-neutral">solid</span>
                )}
              </dd>
            </dl>
          ) : (
            <div className="text-muted text-sm">
              Select a node or an edge in the graph to inspect it.
            </div>
          )}
        </Panel>

        <Panel title="Trace paths" subtitle={`${traceData?.paths.length ?? 0} root-to-leaf paths`} flush>
          {traceData && traceData.paths.length > 0 ? (
            <div className="table-wrap" style={{ maxHeight: 280 }}>
              <table className="data-table">
                <caption className="sr-only">Root to leaf paths in the current trace</caption>
                <tbody>
                  {traceData.paths.slice(0, 40).map((path, index) => (
                    <tr key={`${path.join('-')}-${index}`}>
                      <td>
                        <span className="mono-id text-xs">
                          {path.map((id) => id.split(':').pop()).join(' → ')}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="panel-body text-muted text-sm">No paths resolved for this root.</div>
          )}
        </Panel>
      </div>
    </div>
  );
}
