/**
 * NGSH Control Console — mock API.
 *
 * Every function here is a drop-in replacement for a live service call and
 * returns exactly the shape documented in `types.ts`. The dataset behind it is
 * deterministic (see `./mock-data.ts`), so the console is fully demonstrable
 * without the backend running.
 */

import type {
  AuditEntry,
  CoverageResponse,
  EntityWithRelations,
  EventEnvelope,
  EventPage,
  GraphStats,
  HealthStatus,
  IngestRequest,
  IngestResponse,
  LedgerPage,
  LedgerVerification,
  NgsHEntity,
  OntologyRegistry,
  OntologyTypeDetail,
  PolicyDecisionRequest,
  PolicyDecisionResponse,
  PolicyList,
  ServiceName,
  TraceEdge,
  TraceNode,
  TraceResponse,
  VerifyingResult,
} from './types';
import {
  MOCK_ENTITIES,
  MOCK_EVENTS,
  MOCK_GRAPH_STATS,
  MOCK_LEDGER,
  MOCK_LEDGER_HEAD,
  MOCK_POLICIES,
  MOCK_REGISTRY,
  MOCK_RELATIONS,
  evaluateMockPolicy,
  mockEntityWithRelations,
} from './mock-data';
import { sha256Hex } from '../lib/sha256';

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

/**
 * Matches a dot-delimited event type against a glob.
 *
 * `entity.*` matches by wildcard, `test.result.recorded` matches exactly and
 * `test` / `test.` match every type under that prefix.
 */
export function matchesEventTypeGlob(eventType: string, glob: string): boolean {
  const pattern = glob.trim();
  if (pattern === '' || pattern === '*') return true;
  if (pattern.includes('*')) {
    const expression = pattern
      .split('*')
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
      .join('.*');
    return new RegExp(`^${expression}$`).test(eventType);
  }
  if (eventType === pattern) return true;
  const prefix = pattern.endsWith('.') ? pattern : `${pattern}.`;
  return eventType.startsWith(prefix);
}

/** Splits a comma-separated type filter and keeps events matching any glob. */
function filterByTypes(events: EventEnvelope[], types: string | undefined): EventEnvelope[] {
  if (!types) return events;
  const globs = types.split(',').map((t) => t.trim()).filter(Boolean);
  if (globs.length === 0) return events;
  return events.filter((event) => globs.some((glob) => matchesEventTypeGlob(event.eventType, glob)));
}

function entityLabel(entity: NgsHEntity): string {
  const attrs = entity.attributes as Record<string, unknown> | undefined;
  const name = attrs?.['name'];
  return typeof name === 'string' && name.length > 0 ? name : entity.id;
}

function parseRoot(root: string): { type: string; id: string } | null {
  const separator = root.indexOf(':');
  if (separator <= 0) return null;
  return { type: root.slice(0, separator), id: root.slice(separator + 1) };
}

/* ------------------------------------------------------------------ */
/* Health                                                               */
/* ------------------------------------------------------------------ */

const MOCK_HEALTH: Record<ServiceName, { status: HealthStatus['status']; latencyMs: number; detail: string }> = {
  ontology: { status: 'ok', latencyMs: 4, detail: 'registry v1.0.0, 23 entity types' },
  fabric: { status: 'ok', latencyMs: 7, detail: `${MOCK_EVENTS.length} events retained` },
  policy: { status: 'ok', latencyMs: 5, detail: `${MOCK_POLICIES.length} policies loaded` },
  audit: { status: 'ok', latencyMs: 3, detail: `head ${MOCK_LEDGER_HEAD.slice(0, 12)}` },
  thread: { status: 'ok', latencyMs: 11, detail: `${MOCK_GRAPH_STATS.totalEntities} entities projected` },
  ingest: { status: 'degraded', latencyMs: 214, detail: 'edge queue backlog 1,284 batches' },
};

export function mockHealth(service: ServiceName): HealthStatus {
  const entry = MOCK_HEALTH[service];
  return { service, status: entry.status, latencyMs: entry.latencyMs, detail: entry.detail };
}

/* ------------------------------------------------------------------ */
/* Fabric                                                               */
/* ------------------------------------------------------------------ */

export interface MockEventQuery {
  after?: string;
  limit?: number;
  types?: string;
  tenant?: string;
}

export function mockFetchEvents(query: MockEventQuery = {}): EventPage {
  const limit = Math.min(Math.max(query.limit ?? 100, 1), 500);
  let events = MOCK_EVENTS.slice();

  if (query.tenant) {
    events = events.filter((event) => event.tenant === query.tenant);
  }
  events = filterByTypes(events, query.types);

  // Newest first: the console opens on the tail of the log.
  events = events
    .slice()
    .sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt) || (a.eventId < b.eventId ? 1 : -1));

  if (query.after) {
    const cursor = query.after;
    const index = events.findIndex((event) => event.eventId === cursor);
    if (index >= 0) {
      // The cursor points at the oldest event of the previous page: continue backwards.
      events = events.slice(index + 1);
    } else {
      events = events.filter((event) => event.eventId < cursor);
    }
  }

  const page = events.slice(0, limit);
  const cursor = page.length > 0 ? page[page.length - 1]!.eventId : (query.after ?? '');
  return { events: page, cursor };
}

export function mockFetchEvent(eventId: string): EventEnvelope | null {
  return MOCK_EVENTS.find((event) => event.eventId === eventId) ?? null;
}

/* ------------------------------------------------------------------ */
/* Ontology                                                             */
/* ------------------------------------------------------------------ */

export function mockFetchRegistry(): OntologyRegistry {
  return MOCK_REGISTRY;
}

export function mockFetchType(type: string): OntologyTypeDetail | null {
  const definition = MOCK_REGISTRY.entities.find((entity) => entity.type === type);
  if (!definition) return null;
  const instances = MOCK_ENTITIES.filter((entity) => entity.type === type);
  return {
    type,
    schema: {
      $ref: `contracts/ontology/entities.schema.json#/$defs/${type}Attributes`,
      title: `${type} entity`,
      ontologyVersion: MOCK_REGISTRY.ontologyVersion,
    },
    attributes: {
      idPrefix: definition.idPrefix,
      classificationFloor: definition.classificationFloor,
      pii: definition.pii,
      pillars: definition.pillars,
      description: definition.description,
      instanceCount: instances.length,
      sample: instances.slice(0, 3).map((entity) => ({ id: entity.id, attributes: entity.attributes })),
    },
  };
}

/* ------------------------------------------------------------------ */
/* Thread                                                               */
/* ------------------------------------------------------------------ */

export function mockListEntities(type?: string, limit = 100): { entities: NgsHEntity[]; cursor: string } {
  const all = type ? MOCK_ENTITIES.filter((entity) => entity.type === type) : MOCK_ENTITIES;
  const page = all.slice(0, Math.min(Math.max(limit, 1), 500));
  return { entities: page, cursor: page.length > 0 ? page[page.length - 1]!.id : '' };
}

export function mockFetchEntity(type: string, id: string): EntityWithRelations | null {
  return mockEntityWithRelations(type, id);
}

export interface MockTraceQuery {
  root: string;
  depth?: number;
  relationTypes?: string[];
}

export function mockTrace(query: MockTraceQuery): TraceResponse {
  const parsed = parseRoot(query.root);
  const depth = Math.min(Math.max(query.depth ?? 3, 1), 6);
  const allowed = query.relationTypes && query.relationTypes.length > 0 ? new Set(query.relationTypes) : null;

  const rootEntity = parsed
    ? MOCK_ENTITIES.find((entity) => entity.id === parsed.id && entity.type === parsed.type)
    : undefined;

  if (!rootEntity || !parsed) {
    return { root: query.root, nodes: [], edges: [], paths: [] };
  }

  const nodeMap = new Map<string, TraceNode>();
  const edgeMap = new Map<string, TraceEdge>();
  const adjacency = new Map<string, string[]>();
  const visited = new Set<string>([rootEntity.id]);

  const addNode = (entity: NgsHEntity): void => {
    if (nodeMap.has(entity.id)) return;
    nodeMap.set(entity.id, {
      id: entity.id,
      type: entity.type,
      label: entityLabel(entity),
      classification: entity.classification,
    });
  };
  const addEdge = (edge: TraceEdge): void => {
    const key = `${edge.from}->${edge.to}:${edge.type}`;
    if (!edgeMap.has(key)) edgeMap.set(key, edge);
  };

  addNode(rootEntity);

  let frontier: string[] = [rootEntity.id];
  for (let level = 0; level < depth; level += 1) {
    const next: string[] = [];
    for (const nodeId of frontier) {
      const neighbours: string[] = [];
      for (const relation of MOCK_RELATIONS) {
        if (allowed && !allowed.has(relation.type)) continue;
        const touchesFrom = relation.from.id === nodeId;
        const touchesTo = relation.to.id === nodeId;
        if (!touchesFrom && !touchesTo) continue;

        const otherId = touchesFrom ? relation.to.id : relation.from.id;
        const other = MOCK_ENTITIES.find((entity) => entity.id === otherId);
        if (!other) continue;

        addEdge({
          from: relation.from.id,
          to: relation.to.id,
          type: relation.type,
          confidence: relation.confidence,
        });
        neighbours.push(otherId);

        if (!visited.has(otherId)) {
          visited.add(otherId);
          addNode(other);
          next.push(otherId);
        }
      }
      adjacency.set(nodeId, neighbours);
    }
    frontier = next;
    if (frontier.length === 0) break;
  }

  // Build the paths from the root outward for every discovered leaf.
  const paths: string[][] = [];
  const walk = (nodeId: string, trail: string[]): void => {
    const neighbours = adjacency.get(nodeId) ?? [];
    const unvisited = neighbours.filter((n) => !trail.includes(n));
    if (unvisited.length === 0) {
      if (trail.length > 1) paths.push(trail);
      return;
    }
    for (const neighbour of unvisited) {
      walk(neighbour, [...trail, neighbour]);
    }
  };
  walk(rootEntity.id, [rootEntity.id]);

  return {
    root: `${rootEntity.type}:${rootEntity.id}`,
    nodes: Array.from(nodeMap.values()),
    edges: Array.from(edgeMap.values()),
    paths: paths.slice(0, 64),
  };
}

export function mockGraphStats(): GraphStats {
  return MOCK_GRAPH_STATS;
}

export function mockCoverage(requirementId: string): CoverageResponse {
  const requirement = MOCK_ENTITIES.find((entity) => entity.id === requirementId);
  const verifyingRelations = MOCK_RELATIONS.filter(
    (relation) => relation.type === 'verifies' && relation.to.id === requirementId,
  );
  const verifyingResults: VerifyingResult[] = [];
  for (const relation of verifyingRelations) {
    const result = MOCK_ENTITIES.find((entity) => entity.id === relation.from.id);
    if (!result || result.type !== 'TestResult') continue;
    const outcome = (result.attributes as Record<string, unknown> | undefined)?.['outcome'];
    verifyingResults.push({
      id: result.id,
      outcome: (outcome as VerifyingResult['outcome']) ?? 'NOT_RUN',
    });
  }

  const satisfied = MOCK_RELATIONS.filter(
    (relation) => relation.type === 'satisfies' && relation.to.id === requirementId,
  );

  const gaps: string[] = [];
  if (verifyingResults.length === 0) {
    gaps.push('No verifying test result is asserted against this requirement.');
  }
  for (const result of verifyingResults) {
    if (result.outcome === 'FAIL') {
      gaps.push(`Verifying result ${result.id} recorded FAIL — the requirement is not discharged.`);
    }
    if (result.outcome === 'MARGINAL') {
      gaps.push(`Verifying result ${result.id} recorded MARGINAL — acceptance criteria met only within uncertainty.`);
    }
    if (result.outcome === 'INCONCLUSIVE') {
      gaps.push(`Verifying result ${result.id} recorded INCONCLUSIVE — the run did not produce admissible evidence.`);
    }
    if (result.outcome === 'NOT_RUN') {
      gaps.push(`Verifying result ${result.id} has not been executed.`);
    }
  }
  if (satisfied.length === 0) {
    gaps.push('No design element is allocated to this requirement.');
  }

  const allocationCoverage = satisfied.length > 0 ? 1 : 0;
  const evidenceCoverage =
    verifyingResults.length > 0
      ? verifyingResults.filter((result) => result.outcome === 'PASS' || result.outcome === 'MARGINAL').length /
        verifyingResults.length
      : 0;
  const coverage = Math.round((allocationCoverage * 0.4 + evidenceCoverage * 0.6) * 100) / 100;
  const verified = verifyingResults.some((result) => result.outcome === 'PASS') && !verifyingResults.some((result) => result.outcome === 'FAIL');

  return {
    requirement: requirement?.id ?? requirementId,
    verified,
    verifyingResults,
    coverage,
    gaps,
  };
}

/* ------------------------------------------------------------------ */
/* Audit                                                                */
/* ------------------------------------------------------------------ */

export function mockLedger(after?: string, limit = 100): LedgerPage {
  const bounded = Math.min(Math.max(limit, 1), 500);
  let entries: AuditEntry[] = MOCK_LEDGER.slice();
  if (after) {
    const index = entries.findIndex((entry) => String(entry.seq) === after);
    entries = index >= 0 ? entries.slice(index + 1) : entries.filter((entry) => String(entry.seq) > after);
  }
  const page = entries.slice(0, bounded);
  const cursor = page.length > 0 ? String(page[page.length - 1]!.seq) : (after ?? '0');
  return { entries: page, cursor, head: MOCK_LEDGER_HEAD };
}

export function mockVerifyLedger(): LedgerVerification {
  let prevHash = '0'.repeat(64);
  for (const entry of MOCK_LEDGER) {
    const digest = sha256Hex(
      [prevHash, entry.seq, entry.timestamp, entry.eventType, entry.subject, entry.action, entry.resource, entry.decision, entry.reason].join('|'),
    );
    if (entry.prevHash !== prevHash || entry.hash !== digest) {
      return { valid: false, checked: entry.seq, brokenAt: entry.seq, head: MOCK_LEDGER_HEAD };
    }
    prevHash = entry.hash;
  }
  return { valid: true, checked: MOCK_LEDGER.length, brokenAt: null, head: MOCK_LEDGER_HEAD };
}

/* ------------------------------------------------------------------ */
/* Policy                                                               */
/* ------------------------------------------------------------------ */

export function mockPolicies(): PolicyList {
  return { policies: MOCK_POLICIES };
}

export function mockPolicyDecision(request: PolicyDecisionRequest): PolicyDecisionResponse {
  return evaluateMockPolicy(request.subject, request.resource, request.action);
}

/* ------------------------------------------------------------------ */
/* Ingest                                                               */
/* ------------------------------------------------------------------ */

export function mockIngest(request: IngestRequest): IngestResponse {
  const lines = request.payload.split('\n').map((line) => line.trim()).filter(Boolean);
  const recordCount = request.format === 'NDJSON' ? lines.length : Math.max(lines.length, 1);
  const rejected = request.format === 'CSV' && recordCount > 0 ? 1 : 0;
  const accepted = Math.max(recordCount - rejected, 0);
  const batchId = `BATCH:${sha256Hex(`${request.source}:${request.payload.length}`).slice(0, 16).toUpperCase()}`;
  const entityIds = MOCK_ENTITIES.filter((entity) => entity.type === 'TestResult')
    .slice(0, Math.min(accepted, 3))
    .map((entity) => entity.id);
  return {
    batchId,
    recordsAccepted: accepted,
    recordsRejected: rejected,
    entityIds,
  };
}
