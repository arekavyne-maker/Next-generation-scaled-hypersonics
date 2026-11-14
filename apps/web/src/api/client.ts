/**
 * NGSH Control Console — API client.
 *
 * Resolution order for every call:
 *   1. `VITE_USE_MOCK=true` short-circuits to the deterministic mock dataset.
 *   2. Otherwise the live service is called. If the service is unreachable
 *      (connection refused, DNS failure, timeout, 5xx) the console degrades to
 *      the mock dataset and records why, so the operator is never shown a
 *      blank screen with no explanation.
 *
 * URL layout:
 *   proxy mode (default in dev)  ->  /api/<service>/v1/...   (see vite.config.ts)
 *   direct mode                  ->  http://<host>:<port>/v1/...
 */

import type {
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
  TraceResponse,
} from './types';
import { SERVICE_PORTS } from './types';
import * as mock from './mock';
import { MOCK_EPOCH_MS } from './mock-data';
import { setClockSource } from '../lib/clock';

/* ------------------------------------------------------------------ */
/* Configuration                                                        */
/* ------------------------------------------------------------------ */

const DEFAULT_API_BASE = 'http://localhost:8082';
const PROXY_PREFIX = '/api';
const REQUEST_TIMEOUT_MS = 8000;

const env = import.meta.env;

const FORCED_MOCK = String(env.VITE_USE_MOCK ?? '').toLowerCase() === 'true';

// In forced mock mode the dataset clock is the reference clock from the start.
if (FORCED_MOCK) {
  setClockSource(() => MOCK_EPOCH_MS);
}

const API_MODE: 'proxy' | 'direct' =
  env.VITE_API_MODE === 'direct' || env.VITE_API_MODE === 'proxy'
    ? env.VITE_API_MODE
    : env.DEV
      ? 'proxy'
      : 'direct';

function envValue(key: string): string | undefined {
  const value = (env as Record<string, string | undefined>)[key];
  return value && value.length > 0 ? value : undefined;
}

function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

/**
 * Resolves the base URL for a service.
 *
 * proxy mode : `/api/<service>` (or `VITE_API_BASE` when it is a path)
 * direct mode: `VITE_API_<SERVICE>` → `VITE_API_BASE` (gateway layout) →
 *              the documented default `http://localhost:<port>`
 */
export function serviceBaseUrl(service: ServiceName): string {
  const override = envValue(`VITE_API_${service.toUpperCase()}`);
  if (override) return stripTrailingSlash(override);

  const base = envValue('VITE_API_BASE');

  if (API_MODE === 'proxy') {
    if (base && base.startsWith('/')) return `${stripTrailingSlash(base)}/${service}`;
    return `${PROXY_PREFIX}/${service}`;
  }

  if (base) {
    const isDefault = base === DEFAULT_API_BASE;
    if (isDefault) return service === 'fabric' ? DEFAULT_API_BASE : `http://localhost:${SERVICE_PORTS[service]}`;
    return `${stripTrailingSlash(base)}/${service}`;
  }

  return service === 'fabric' ? DEFAULT_API_BASE : `http://localhost:${SERVICE_PORTS[service]}`;
}

export function apiMode(): 'proxy' | 'direct' {
  return API_MODE;
}

export function isForcedMock(): boolean {
  return FORCED_MOCK;
}

/* ------------------------------------------------------------------ */
/* Data source tracking                                                 */
/* ------------------------------------------------------------------ */

export interface DataSourceState {
  mode: 'live' | 'mock' | 'degraded';
  liveCalls: number;
  mockCalls: number;
  lastFallbackReason: string | null;
  lastFallbackAt: string | null;
  forcedMock: boolean;
}

const counters = { live: 0, mock: 0 };
let lastFallbackReason: string | null = null;
let lastFallbackAt: string | null = null;
const listeners = new Set<(state: DataSourceState) => void>();

function currentState(): DataSourceState {
  const mode: DataSourceState['mode'] =
    counters.mock === 0 ? 'live' : counters.live === 0 ? 'mock' : 'degraded';
  return {
    mode,
    liveCalls: counters.live,
    mockCalls: counters.mock,
    lastFallbackReason,
    lastFallbackAt,
    forcedMock: FORCED_MOCK,
  };
}

function notify(): void {
  const state = currentState();
  for (const listener of listeners) listener(state);
}

export function getDataSourceState(): DataSourceState {
  return currentState();
}

export function subscribeDataSource(listener: (state: DataSourceState) => void): () => void {
  listeners.add(listener);
  listener(currentState());
  return () => {
    listeners.delete(listener);
  };
}

function markLive(): void {
  counters.live += 1;
  setClockSource(() => Date.now());
  notify();
}

function markMock(reason: string): void {
  counters.mock += 1;
  lastFallbackReason = reason;
  lastFallbackAt = new Date().toISOString();
  setClockSource(() => MOCK_EPOCH_MS);
  notify();
}

/* ------------------------------------------------------------------ */
/* Errors                                                               */
/* ------------------------------------------------------------------ */

export class ApiError extends Error {
  readonly status: number;
  readonly service: ServiceName;
  readonly url: string;

  constructor(service: ServiceName, status: number, url: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.service = service;
    this.url = url;
  }
}

/* ------------------------------------------------------------------ */
/* Core request                                                         */
/* ------------------------------------------------------------------ */

type QueryValue = string | number | boolean | undefined | null;

export interface RequestSpec<T> {
  service: ServiceName;
  path: string;
  method?: 'GET' | 'POST';
  query?: Record<string, QueryValue>;
  body?: unknown;
  /** Produces the deterministic response used when the live service is unavailable. */
  mock: () => T;
  /** Treat HTTP 404 as "endpoint not implemented" and fall back to the mock. */
  fallbackOn404?: boolean;
  signal?: AbortSignal;
}

function buildUrl(service: ServiceName, path: string, query?: Record<string, QueryValue>): string {
  const base = serviceBaseUrl(service);
  const search = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') continue;
      search.set(key, String(value));
    }
  }
  const suffix = search.toString();
  return `${base}${path}${suffix ? `?${suffix}` : ''}`;
}

/** Statuses that mean "the backend is not available" rather than "your request was wrong". */
function isUnavailableStatus(status: number): boolean {
  return status >= 500;
}

async function request<T>(spec: RequestSpec<T>): Promise<T> {
  const service = spec.service;
  const method = spec.method ?? 'GET';
  const url = buildUrl(service, spec.path, spec.query);

  if (FORCED_MOCK) {
    markMock('mock mode forced by VITE_USE_MOCK');
    return spec.mock();
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const onAbort = (): void => controller.abort();
  spec.signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(spec.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: spec.body === undefined ? undefined : JSON.stringify(spec.body),
      signal: controller.signal,
    });

    if (response.ok) {
      markLive();
      return (await response.json()) as T;
    }

    const detail = await response.text().catch(() => '');
    const unreachable = isUnavailableStatus(response.status) || (response.status === 404 && spec.fallbackOn404);
    if (unreachable) {
      markMock(`${service} responded ${response.status} ${response.statusText || ''}`.trim());
      return spec.mock();
    }

    throw new ApiError(
      service,
      response.status,
      url,
      `${service} rejected the request (${response.status})${detail ? `: ${detail.slice(0, 240)}` : ''}`,
    );
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const reason = error instanceof Error ? error.message : String(error);
    markMock(`${service} unreachable (${reason})`);
    return spec.mock();
  } finally {
    clearTimeout(timeout);
    spec.signal?.removeEventListener('abort', onAbort);
  }
}

/* ------------------------------------------------------------------ */
/* Health                                                               */
/* ------------------------------------------------------------------ */

export function fetchHealth(service: ServiceName, signal?: AbortSignal): Promise<HealthStatus> {
  return request<HealthStatus>({
    service,
    path: '/healthz',
    mock: () => mock.mockHealth(service),
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Fabric — event log                                                   */
/* ------------------------------------------------------------------ */

export interface EventQuery {
  after?: string;
  limit?: number;
  types?: string;
  tenant?: string;
}

export function fetchEvents(query: EventQuery = {}, signal?: AbortSignal): Promise<EventPage> {
  return request<EventPage>({
    service: 'fabric',
    path: '/v1/events',
    query: {
      after: query.after,
      limit: query.limit ?? 100,
      types: query.types,
      tenant: query.tenant ?? 'ngsh',
    },
    mock: () => mock.mockFetchEvents(query),
    signal,
  });
}

export function fetchEvent(eventId: string, signal?: AbortSignal): Promise<EventEnvelope> {
  return request<EventEnvelope>({
    service: 'fabric',
    path: `/v1/events/${encodeURIComponent(eventId)}`,
    mock: () => {
      const event = mock.mockFetchEvent(eventId);
      if (!event) throw new ApiError('fabric', 404, eventId, `Event ${eventId} was not found.`);
      return event;
    },
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Ontology                                                             */
/* ------------------------------------------------------------------ */

export function fetchRegistry(signal?: AbortSignal): Promise<OntologyRegistry> {
  return request<OntologyRegistry>({
    service: 'ontology',
    path: '/v1/ontology/registry',
    mock: () => mock.mockFetchRegistry(),
    signal,
  });
}

export function fetchOntologyType(type: string, signal?: AbortSignal): Promise<OntologyTypeDetail> {
  return request<OntologyTypeDetail>({
    service: 'ontology',
    path: `/v1/ontology/types/${encodeURIComponent(type)}`,
    mock: () => {
      const detail = mock.mockFetchType(type);
      if (!detail) throw new ApiError('ontology', 404, type, `Ontology type ${type} is not registered.`);
      return detail;
    },
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Thread — entities, trace, coverage                                   */
/* ------------------------------------------------------------------ */

export interface EntityListQuery {
  type?: string;
  limit?: number;
}

/**
 * Lists entities of a type.
 *
 * NOTE: the NGSH contract does not define a collection endpoint on the thread
 * service. The console assumes `GET /v1/entities?type=&limit=` and falls back
 * to the mock dataset when the service answers 404.
 */
export function listEntities(query: EntityListQuery = {}, signal?: AbortSignal): Promise<{ entities: NgsHEntity[]; cursor: string }> {
  return request<{ entities: NgsHEntity[]; cursor: string }>({
    service: 'thread',
    path: '/v1/entities',
    query: { type: query.type, limit: query.limit ?? 100 },
    mock: () => mock.mockListEntities(query.type, query.limit ?? 100),
    fallbackOn404: true,
    signal,
  });
}

export function fetchEntity(type: string, id: string, signal?: AbortSignal): Promise<EntityWithRelations> {
  return request<EntityWithRelations>({
    service: 'thread',
    path: `/v1/entities/${encodeURIComponent(type)}/${encodeURIComponent(id)}`,
    mock: () => {
      const result = mock.mockFetchEntity(type, id);
      if (!result) throw new ApiError('thread', 404, `${type}:${id}`, `Entity ${type}:${id} was not found.`);
      return result;
    },
    signal,
  });
}

export interface TraceQuery {
  root: string;
  depth?: number;
  relationTypes?: string[];
}

export function fetchTrace(query: TraceQuery, signal?: AbortSignal): Promise<TraceResponse> {
  return request<TraceResponse>({
    service: 'thread',
    path: '/v1/trace',
    query: {
      root: query.root,
      depth: query.depth ?? 3,
      relationTypes: query.relationTypes && query.relationTypes.length > 0 ? query.relationTypes.join(',') : undefined,
    },
    mock: () => mock.mockTrace(query),
    signal,
  });
}

export function fetchGraphStats(signal?: AbortSignal): Promise<GraphStats> {
  return request<GraphStats>({
    service: 'thread',
    path: '/v1/graph/stats',
    mock: () => mock.mockGraphStats(),
    signal,
  });
}

export function fetchCoverage(requirementId: string, signal?: AbortSignal): Promise<CoverageResponse> {
  return request<CoverageResponse>({
    service: 'thread',
    path: `/v1/trace/requirements/${encodeURIComponent(requirementId)}/coverage`,
    method: 'POST',
    body: {},
    mock: () => mock.mockCoverage(requirementId),
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Audit — tamper evident ledger                                        */
/* ------------------------------------------------------------------ */

export interface LedgerQuery {
  after?: string;
  limit?: number;
}

export function fetchLedger(query: LedgerQuery = {}, signal?: AbortSignal): Promise<LedgerPage> {
  return request<LedgerPage>({
    service: 'audit',
    path: '/v1/ledger',
    query: { after: query.after, limit: query.limit ?? 100 },
    mock: () => mock.mockLedger(query.after, query.limit ?? 100),
    signal,
  });
}

export function verifyLedger(signal?: AbortSignal): Promise<LedgerVerification> {
  return request<LedgerVerification>({
    service: 'audit',
    path: '/v1/ledger/verify',
    mock: () => mock.mockVerifyLedger(),
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Policy                                                               */
/* ------------------------------------------------------------------ */

export function fetchPolicies(signal?: AbortSignal): Promise<PolicyList> {
  return request<PolicyList>({
    service: 'policy',
    path: '/v1/policies',
    mock: () => mock.mockPolicies(),
    signal,
  });
}

export function submitDecision(
  request_: PolicyDecisionRequest,
  signal?: AbortSignal,
): Promise<PolicyDecisionResponse> {
  return request<PolicyDecisionResponse>({
    service: 'policy',
    path: '/v1/decisions',
    method: 'POST',
    body: request_,
    mock: () => mock.mockPolicyDecision(request_),
    signal,
  });
}

/* ------------------------------------------------------------------ */
/* Ingest                                                               */
/* ------------------------------------------------------------------ */

export function submitIngest(payload: IngestRequest, signal?: AbortSignal): Promise<IngestResponse> {
  return request<IngestResponse>({
    service: 'ingest',
    path: '/v1/ingest',
    method: 'POST',
    body: payload,
    mock: () => mock.mockIngest(payload),
    signal,
  });
}
