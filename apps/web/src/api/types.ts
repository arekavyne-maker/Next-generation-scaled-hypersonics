/**
 * NGSH Control Console — API contract types.
 *
 * These mirror the NGSH service contracts exactly:
 *   contracts/events/event-envelope.schema.json
 *   contracts/ontology/common.schema.json
 *   contracts/ontology/registry.json
 *   contracts/ontology/relations.schema.json
 *
 * Every shape here is what the console expects to receive from the backend.
 * The mock layer in `./mock.ts` produces byte-compatible responses.
 */

/* ------------------------------------------------------------------ */
/* Shared vocabulary                                                    */
/* ------------------------------------------------------------------ */

export type ClassificationLevel =
  | 'UNCLASSIFIED'
  | 'CUI'
  | 'CUI//REL'
  | 'CUI//FOUO'
  | 'RESTRICTED'
  | 'SECRET'
  | 'TOP SECRET';

export interface Classification {
  level: ClassificationLevel;
  caveats?: string[];
  origins?: string[];
  derivedFromClassified?: boolean;
}

export type ClearanceLevel = 'NONE' | 'SECRET' | 'TOP SECRET' | 'SCI-CLEARED';

export type Citizenship = 'US' | 'ALLIED' | 'FOREIGN' | 'UNKNOWN';

export type ActorKind = 'user' | 'service' | 'device' | 'edge-agent' | 'anonymous';

export interface Actor {
  subjectId: string;
  kind: ActorKind;
  displayName?: string;
  clearance?: ClearanceLevel;
  citizenship?: Citizenship;
  programs?: string[];
  needToKnow?: string[];
  org?: string;
}

export interface Attachment {
  uri: string;
  sha256: string;
  sizeBytes?: number;
  mediaType?: string;
  classification?: Classification;
  encrypted?: boolean;
  retentionUntil?: string;
}

export interface Measurement {
  name: string;
  value: number;
  unit?: string;
  uncertainty?: number;
  min?: number;
  max?: number;
  method?: string;
  channel?: string;
}

/* ------------------------------------------------------------------ */
/* Event envelope (fabric)                                              */
/* ------------------------------------------------------------------ */

export interface EventEnvelope {
  eventId: string;
  eventType: string;
  eventVersion: number;
  aggregateType: string;
  aggregateId: string;
  sequence: number;
  causationId?: string;
  correlationId?: string;
  transactionId?: string;
  occurredAt: string;
  recordedAt: string;
  tenant: string;
  program?: string;
  actor: Actor;
  classification?: Classification;
  payload: Record<string, unknown>;
  attachments?: Attachment[];
  idempotencyKey?: string;
  schemaRef?: string;
}

export interface EventPage {
  events: EventEnvelope[];
  cursor: string;
}

/* ------------------------------------------------------------------ */
/* Ontology (ontology-service)                                          */
/* ------------------------------------------------------------------ */

export type PillarId = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'FOUNDATION';

export interface OntologyEntityDef {
  type: string;
  idPrefix: string;
  description: string;
  pillars: PillarId[];
  classificationFloor: ClassificationLevel;
  pii: boolean;
}

export type Cardinality = 'ONE_TO_ONE' | 'ONE_TO_MANY' | 'MANY_TO_ONE' | 'MANY_TO_MANY';

export interface OntologyRelationDef {
  type: string;
  fromTypes: string[];
  toTypes: string[];
  cardinality: Cardinality;
  description: string;
  mayCrossClassification: boolean;
}

export interface OntologyRegistry {
  ontologyVersion: string;
  entities: OntologyEntityDef[];
  relations: OntologyRelationDef[];
}

export interface OntologyTypeDetail {
  type: string;
  schema: unknown;
  attributes: Record<string, unknown>;
}

/* ------------------------------------------------------------------ */
/* Entities and relations (thread-service)                              */
/* ------------------------------------------------------------------ */

export interface EntityReference {
  type: string;
  id: string;
}

export interface Relation {
  id: string;
  type: string;
  from: EntityReference;
  to: EntityReference;
  classification?: Classification;
  assertedAt: string;
  assertedBy?: string;
  confidence?: number;
  attributes?: Record<string, unknown>;
}

export interface NgsHEntity {
  id: string;
  type: string;
  tenant: string;
  program?: string;
  version: number;
  classification?: Classification;
  createdAt: string;
  updatedAt: string;
  createdBy?: string;
  updatedBy?: string;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  deleted?: boolean;
  attributes?: Record<string, unknown>;
  relations?: Relation[];
}

export interface EntityWithRelations {
  entity: NgsHEntity;
  relations: Relation[];
}

export interface TraceNode {
  id: string;
  type: string;
  label: string;
  classification?: Classification;
}

export interface TraceEdge {
  from: string;
  to: string;
  type: string;
  confidence?: number;
}

export interface TraceResponse {
  root: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  paths: string[][];
}

export interface GraphStats {
  entityCounts: Record<string, number>;
  relationCounts: Record<string, number>;
  totalEntities: number;
  totalRelations: number;
}

/* ------------------------------------------------------------------ */
/* Requirement coverage (thread-service)                                */
/* ------------------------------------------------------------------ */

export interface VerifyingResult {
  id: string;
  outcome: 'PASS' | 'FAIL' | 'MARGINAL' | 'INCONCLUSIVE' | 'NOT_RUN';
}

export interface CoverageResponse {
  requirement: string;
  verified: boolean;
  verifyingResults: VerifyingResult[];
  coverage: number;
  gaps: string[];
}

/* ------------------------------------------------------------------ */
/* Audit ledger (audit-service)                                         */
/* ------------------------------------------------------------------ */

export type AuditDecision = 'ALLOW' | 'DENY' | 'INDETERMINATE';

export interface AuditEntry {
  seq: number;
  hash: string;
  prevHash: string;
  timestamp: string;
  eventType: string;
  subject: string;
  action: string;
  resource: string;
  decision: AuditDecision;
  reason: string;
}

export interface LedgerPage {
  entries: AuditEntry[];
  cursor: string;
  head: string;
}

export interface LedgerVerification {
  valid: boolean;
  checked: number;
  brokenAt: number | null;
  head: string;
}

/* ------------------------------------------------------------------ */
/* Policy (policy-service)                                              */
/* ------------------------------------------------------------------ */

export interface PolicySubject {
  subjectId: string;
  kind: ActorKind;
  clearance: ClearanceLevel;
  citizenship: Citizenship;
  programs: string[];
}

export interface PolicyResource {
  type: string;
  id: string;
  classification: ClassificationLevel;
}

export interface PolicyDecisionRequest {
  subject: PolicySubject;
  resource: PolicyResource;
  action: string;
  context: Record<string, unknown>;
}

export interface PolicyDecisionResponse {
  decision: AuditDecision;
  policyId: string;
  obligations: string[];
  reason: string;
}

export interface PolicySummary {
  id: string;
  description: string;
  effect: 'ALLOW' | 'DENY';
  priority: number;
}

export interface PolicyList {
  policies: PolicySummary[];
}

/* ------------------------------------------------------------------ */
/* Ingest (ingest-service)                                              */
/* ------------------------------------------------------------------ */

export type IngestFormat = 'NDJSON' | 'CSV' | 'JSON';

export interface IngestRequest {
  source: string;
  format: IngestFormat;
  payload: string;
  classification: { level: ClassificationLevel };
}

export interface IngestResponse {
  batchId: string;
  recordsAccepted: number;
  recordsRejected: number;
  entityIds: string[];
}

/* ------------------------------------------------------------------ */
/* Health                                                               */
/* ------------------------------------------------------------------ */

export type ServiceName = 'ontology' | 'fabric' | 'policy' | 'audit' | 'thread' | 'ingest';

export const SERVICE_NAMES: readonly ServiceName[] = [
  'ontology',
  'fabric',
  'policy',
  'audit',
  'thread',
  'ingest',
];

export const SERVICE_LABELS: Record<ServiceName, string> = {
  ontology: 'ontology-service',
  fabric: 'fabric-service',
  policy: 'policy-service',
  audit: 'audit-service',
  thread: 'thread-service',
  ingest: 'ingest-service',
};

export const SERVICE_PORTS: Record<ServiceName, number> = {
  ontology: 8081,
  fabric: 8082,
  policy: 8083,
  audit: 8084,
  thread: 8085,
  ingest: 8086,
};

export interface HealthStatus {
  service: ServiceName;
  status: 'ok' | 'degraded' | 'down';
  latencyMs: number;
  detail?: string;
}
