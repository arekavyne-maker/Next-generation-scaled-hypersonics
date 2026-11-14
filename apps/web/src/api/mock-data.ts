/**
 * NGSH Control Console — deterministic mock dataset.
 *
 * Everything in this module is generated from a fixed seed and a fixed
 * reference clock, so every reload produces byte-identical data. That keeps
 * screenshots, demos and regression checks stable.
 *
 * The content models a realistic NGSH-SHY program slice: a hypersonic glide
 * vehicle, its CMC supply chain, a wind-tunnel qualification campaign, the
 * requirements it discharges, and the threat side of the digital thread.
 */

import type {
  Actor,
  AuditEntry,
  ClassificationLevel,
  EntityWithRelations,
  EventEnvelope,
  GraphStats,
  NgsHEntity,
  OntologyRegistry,
  PolicyDecisionResponse,
  PolicySummary,
  Relation,
} from './types';
import { sha256Hex } from '../lib/sha256';

/* ------------------------------------------------------------------ */
/* Deterministic primitives                                             */
/* ------------------------------------------------------------------ */

/** Reference clock for the mock dataset (2026-11-14T18:42:00Z). */
export const MOCK_EPOCH_MS = Date.parse('2026-11-14T18:42:00Z');

/** Program-wide identifiers used throughout the mock data set. */
export const MOCK_TENANT = 'ngsh';
export const MOCK_PROGRAM = 'NGSH-SHY';

/** mulberry32 — small, fast, fully deterministic PRNG. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(0x4e475348); // "NGSH"

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

/** Encodes a millisecond timestamp as the 10-character ULID time component. */
function encodeTime(ms: number): string {
  let value = Math.floor(ms);
  let out = '';
  for (let i = 0; i < 10; i += 1) {
    out = CROCKFORD[value % 32] + out;
    value = Math.floor(value / 32);
  }
  return out;
}

/** Produces a ULID (lexicographically sortable, time ordered) for a timestamp. */
function ulid(ms: number): string {
  let suffix = '';
  for (let i = 0; i < 16; i += 1) {
    suffix += CROCKFORD[Math.floor(rand() * 32)];
  }
  return encodeTime(ms) + suffix;
}

/** Short, human-referenceable ULID fragment used inside entity ids. */
function shortUlid(ms: number): string {
  return ulid(ms).slice(0, 16);
}

function isoAt(ms: number): string {
  return new Date(ms).toISOString();
}

function daysAgo(days: number, jitterHours = 0): number {
  return MOCK_EPOCH_MS - days * 86_400_000 - jitterHours * 3_600_000;
}

function between(min: number, max: number): number {
  return min + rand() * (max - min);
}

/* ------------------------------------------------------------------ */
/* Ontology registry (mirror of contracts/ontology/registry.json)       */
/* ------------------------------------------------------------------ */

export const MOCK_REGISTRY: OntologyRegistry = {
  ontologyVersion: '1.0.0',
  entities: [
    { type: 'System', idPrefix: 'SYS', description: 'Any engineered system of interest, at any level of the digital thread.', pillars: ['A', 'F', 'G', 'FOUNDATION'], classificationFloor: 'CUI', pii: false },
    { type: 'Variant', idPrefix: 'VAR', description: 'A configuration-specific instance of a System; the unit of family-of-systems generation (PSDD A-2).', pillars: ['A'], classificationFloor: 'CUI', pii: false },
    { type: 'Subsystem', idPrefix: 'SUB', description: 'Decomposition node beneath a System.', pillars: ['A'], classificationFloor: 'CUI', pii: false },
    { type: 'Part', idPrefix: 'PART', description: 'A discrete hardware article.', pillars: ['A', 'B', 'D', 'H'], classificationFloor: 'CUI', pii: false },
    { type: 'Material', idPrefix: 'MAT', description: 'CMC lot, prepreg batch or billet. The join point between strike-side materials and shield-side supply-chain risk.', pillars: ['B', 'D'], classificationFloor: 'CUI', pii: false },
    { type: 'ProcessPlan', idPrefix: 'PP', description: 'Qualified recipe for producing a Part from Material.', pillars: ['B'], classificationFloor: 'CUI', pii: false },
    { type: 'ProcessRun', idPrefix: 'PR', description: 'A single execution of a ProcessPlan against a Material lot.', pillars: ['B'], classificationFloor: 'CUI', pii: false },
    { type: 'TestArticle', idPrefix: 'TA', description: 'As-built configuration subject to test.', pillars: ['B', 'C', 'G'], classificationFloor: 'CUI', pii: false },
    { type: 'TestCampaign', idPrefix: 'TC', description: 'A planned, coordinated body of tests against one or more articles.', pillars: ['C', 'G'], classificationFloor: 'CUI', pii: false },
    { type: 'TestResult', idPrefix: 'TR', description: 'Outcome of a test, with full configuration context. Immutable once recorded (PSDD 6.3).', pillars: ['C', 'G', 'A'], classificationFloor: 'CUI', pii: false },
    { type: 'Requirement', idPrefix: 'REQ', description: 'A baselined engineering requirement; the root of the verification chain.', pillars: ['A', 'E', 'F'], classificationFloor: 'CUI', pii: false },
    { type: 'Interface', idPrefix: 'IF', description: 'Controlled interface between two systems, versioned by ICD.', pillars: ['A', 'F'], classificationFloor: 'CUI', pii: false },
    { type: 'Model', idPrefix: 'MDL', description: 'A simulation or ML model with provenance and a fidelity score (PSDD G-4).', pillars: ['B', 'C', 'F', 'G', 'H'], classificationFloor: 'CUI', pii: false },
    { type: 'ThreatSystem', idPrefix: 'THR', description: 'An adversarial system reconstructed from observations; versioned and confidence-scored.', pillars: ['F'], classificationFloor: 'RESTRICTED', pii: false },
    { type: 'ThreatObservation', idPrefix: 'TOBS', description: 'A single sensor observation of a threat system.', pillars: ['F'], classificationFloor: 'RESTRICTED', pii: false },
    { type: 'EngagementScenario', idPrefix: 'ESC', description: 'A composed detect-to-engage scenario for simulation and analysis.', pillars: ['F'], classificationFloor: 'RESTRICTED', pii: false },
    { type: 'Supplier', idPrefix: 'SUP', description: 'An external or internal supply node, scored for risk and dependency.', pillars: ['D', 'H'], classificationFloor: 'CUI', pii: false },
    { type: 'PartProvenance', idPrefix: 'PROV', description: 'Chain-of-custody record for a Part across facilities and transfers.', pillars: ['D', 'B'], classificationFloor: 'CUI', pii: false },
    { type: 'Skill', idPrefix: 'SKL', description: 'A defined occupational or technical skill.', pillars: ['E', 'B'], classificationFloor: 'UNCLASSIFIED', pii: false },
    { type: 'Credential', idPrefix: 'CRD', description: 'Evidence that a Person holds a Skill, with expiry and authority.', pillars: ['E'], classificationFloor: 'CUI', pii: true },
    { type: 'Person', idPrefix: 'PER', description: 'A cleared individual; PII-bearing, so subject to strict retention.', pillars: ['E'], classificationFloor: 'CUI', pii: true },
    { type: 'Facility', idPrefix: 'FAC', description: 'A manufacturing, test, range or training site with surge capability.', pillars: ['B', 'D', 'E', 'G', 'H'], classificationFloor: 'CUI', pii: false },
    { type: 'RangeSlot', idPrefix: 'RS', description: 'A bookable window of range capacity with instrumentation coverage.', pillars: ['C', 'G'], classificationFloor: 'CUI', pii: false },
  ],
  relations: [
    { type: 'satisfies', fromTypes: ['Part', 'Variant', 'Subsystem', 'Model', 'System'], toTypes: ['Requirement'], cardinality: 'MANY_TO_MANY', description: 'A design element discharges a requirement.', mayCrossClassification: false },
    { type: 'verifies', fromTypes: ['TestResult', 'TestCampaign'], toTypes: ['Requirement'], cardinality: 'MANY_TO_MANY', description: 'Test evidence verifies a requirement (PSDD A-3).', mayCrossClassification: false },
    { type: 'manufacturedBy', fromTypes: ['Part', 'Material'], toTypes: ['Facility', 'Supplier'], cardinality: 'MANY_TO_MANY', description: 'Article is produced at a facility or supplied by a supplier.', mayCrossClassification: false },
    { type: 'characterizedBy', fromTypes: ['Material', 'ProcessRun', 'Part'], toTypes: ['Model', 'TestResult'], cardinality: 'MANY_TO_MANY', description: 'Physics or ML characterisation of a material, run or part.', mayCrossClassification: false },
    { type: 'derivedFrom', fromTypes: ['Model', 'ThreatSystem', 'TestResult'], toTypes: ['Model', 'TestResult', 'ThreatObservation'], cardinality: 'MANY_TO_MANY', description: 'Derivation lineage between models, results and reconstructions.', mayCrossClassification: true },
    { type: 'threatens', fromTypes: ['ThreatSystem'], toTypes: ['System', 'Facility', 'Part'], cardinality: 'MANY_TO_MANY', description: 'Adversarial system poses a threat to a defended asset.', mayCrossClassification: false },
    { type: 'engages', fromTypes: ['EngagementScenario'], toTypes: ['ThreatSystem'], cardinality: 'MANY_TO_MANY', description: 'Scenario exercises an engagement against a threat system.', mayCrossClassification: false },
    { type: 'requiresSkill', fromTypes: ['ProcessPlan', 'TestCampaign', 'Facility', 'RangeSlot'], toTypes: ['Skill'], cardinality: 'MANY_TO_MANY', description: 'Activity demands a skill; drives workforce gap analysis (PSDD E-4).', mayCrossClassification: true },
    { type: 'supplies', fromTypes: ['Supplier'], toTypes: ['Part', 'Facility', 'Material'], cardinality: 'MANY_TO_MANY', description: 'Supplier provides a part, material or facility capability.', mayCrossClassification: false },
    { type: 'reconstitutes', fromTypes: ['Facility', 'Supplier', 'Part'], toTypes: ['Part', 'Facility', 'Supplier'], cardinality: 'MANY_TO_MANY', description: 'Recovery path that restores a lost critical node (PSDD H-2).', mayCrossClassification: false },
  ],
};

/* ------------------------------------------------------------------ */
/* Actors                                                               */
/* ------------------------------------------------------------------ */

const ACTORS: Record<string, Actor> = {
  vasquez: { subjectId: 'PER:01J8ZV7M2A', kind: 'user', displayName: 'R. Vasquez', clearance: 'SECRET', citizenship: 'US', programs: [MOCK_PROGRAM], org: 'NGSH/Thread Ops' },
  lindqvist: { subjectId: 'PER:01J8ZV8Q4B', kind: 'user', displayName: 'J. Lindqvist', clearance: 'TOP SECRET', citizenship: 'US', programs: [MOCK_PROGRAM, 'NGSH-FALCON'], org: 'NGSH/Test Enterprise' },
  bhatt: { subjectId: 'PER:01J8ZV9R6C', kind: 'user', displayName: 'A. Bhatt', clearance: 'SECRET', citizenship: 'ALLIED', programs: [MOCK_PROGRAM], org: 'AFRL/RD' },
  osei: { subjectId: 'PER:01J8ZWA1S8D', kind: 'user', displayName: 'M. Osei', clearance: 'NONE', citizenship: 'US', programs: [], org: 'NGSH/Supplier Quality' },
  svcFabric: { subjectId: 'svc:fabric-writer', kind: 'service', displayName: 'fabric-writer', programs: [MOCK_PROGRAM] },
  svcIngest: { subjectId: 'svc:ingest-adapter', kind: 'service', displayName: 'ingest-adapter', programs: [MOCK_PROGRAM] },
  svcPolicy: { subjectId: 'svc:policy-engine', kind: 'service', displayName: 'policy-engine' },
  svcReduce: { subjectId: 'svc:reduction-pipeline', kind: 'service', displayName: 'reduction-pipeline', programs: [MOCK_PROGRAM] },
  svcMdl: { subjectId: 'svc:model-validator', kind: 'service', displayName: 'model-validator', programs: [MOCK_PROGRAM] },
  edgeWt: { subjectId: 'edge:wt-03-node-2', kind: 'edge-agent', displayName: 'wt-03 edge node 2', clearance: 'SECRET', citizenship: 'US', programs: [MOCK_PROGRAM] },
};

/* ------------------------------------------------------------------ */
/* Entities                                                             */
/* ------------------------------------------------------------------ */

interface EntitySeed {
  id: string;
  type: string;
  name: string;
  level: ClassificationLevel;
  ageDays: number;
  /** Overrides `ageDays` for entities that belong to the recent-activity burst. */
  ageHours?: number;
  attrs: Record<string, unknown>;
  labels?: Record<string, string>;
}

const PERSON_IDS = {
  vasquez: 'PER:01J8ZV7M2A',
  lindqvist: 'PER:01J8ZV8Q4B',
  bhatt: 'PER:01J8ZV9R6C',
  osei: 'PER:01J8ZWA1S8D',
} as const;

const ENTITY_SEEDS: EntitySeed[] = [
  /* ---- Program structure ---- */
  {
    id: 'SYS:HGV-A1', type: 'System', name: 'HGV-A1 Hypersonic Glide Vehicle', level: 'CUI', ageDays: 214,
    attrs: {
      name: 'HGV-A1 Hypersonic Glide Vehicle',
      systemType: 'HYPERSONIC_WEAPON',
      mission: 'Air-launched prompt strike within 15 minutes of target designation.',
      lifecycleState: 'QUALIFICATION',
      platform: 'SHY-COMMON-CORE',
      interfaceIds: ['IF:ICD-GNC-05', 'IF:ICD-TPS-02'],
      costEstimate: { amount: 28_400_000, currency: 'USD', basis: 'PARAMETRIC', confidence: 0.62, productionRate: 120 },
    },
    labels: { program: MOCK_PROGRAM, role: 'airframe' },
  },
  {
    id: 'SYS:BOOSTER-LR', type: 'System', name: 'Low-Rate Boosted Glide Vehicle Booster', level: 'CUI', ageDays: 198,
    attrs: {
      name: 'Low-Rate Boosted Glide Vehicle Booster',
      systemType: 'BOOSTER',
      mission: 'Boost-and-glide insertion to Mach 5.8 for long-range strike.',
      lifecycleState: 'DEVELOPMENT',
      platform: 'SHY-COMMON-CORE',
      costEstimate: { amount: 11_900_000, currency: 'USD', basis: 'LEARNED_CURVE', confidence: 0.44, productionRate: 60 },
    },
  },
  {
    id: 'SYS:SENSOR-HBTSS', type: 'System', name: 'HBTSS Space Based Infrared Sensor', level: 'CUI', ageDays: 176,
    attrs: {
      name: 'HBTSS Space Based Infrared Sensor',
      systemType: 'SENSOR',
      mission: 'strategic layer persistent threat detection from MEO.',
      lifecycleState: 'DEVELOPMENT',
      platform: 'GOLDEN-DOME-REF',
    },
  },
  {
    id: 'VAR:HGV-B1', type: 'Variant', name: 'Variant HGV-B1 (Block 1)', level: 'CUI', ageDays: 150,
    attrs: {
      systemId: 'SYS:HGV-A1',
      variantId: 'HGV-B1',
      configurationVersion: 'CFG-2026-014',
      familyId: 'FAM:HGV',
      distinguishingCharacteristics: ['Mach 5.4 ceiling', 'Block 1 seeker', 'Al-2211 keel'],
    },
  },
  {
    id: 'VAR:HGV-B2', type: 'Variant', name: 'Variant HGV-B2 (Block 2)', level: 'CUI', ageDays: 96,
    attrs: {
      systemId: 'SYS:HGV-A1',
      variantId: 'HGV-B2',
      configurationVersion: 'CFG-2026-031',
      familyId: 'FAM:HGV',
      distinguishingCharacteristics: ['Mach 6.1 ceiling', 'Block 2 seeker', 'Enhanced G-sensitivity'],
    },
  },
  {
    id: 'SUB:TPS-01', type: 'Subsystem', name: 'Thermal Protection Segment', level: 'CUI', ageDays: 190,
    attrs: { parentSystemId: 'SYS:HGV-A1', name: 'Thermal Protection Segment', subsystemType: 'TPS', maturity: 'TRL_6', interfaceIds: ['IF:ICD-TPS-02'] },
  },
  {
    id: 'SUB:SEAKER-01', type: 'Subsystem', name: 'Seeker and Guidance Payload', level: 'CUI', ageDays: 180,
    attrs: { parentSystemId: 'SYS:HGV-A1', name: 'Seeker and Guidance Payload', subsystemType: 'PAYLOAD', maturity: 'TRL_5' },
  },
  {
    id: 'SUB:GNC-01', type: 'Subsystem', name: 'Guidance Navigation and Control', level: 'CUI', ageDays: 180,
    attrs: { parentSystemId: 'SYS:HGV-A1', name: 'Guidance Navigation and Control', subsystemType: 'GNC', maturity: 'TRL_5', interfaceIds: ['IF:ICD-GNC-05'] },
  },

  /* ---- Hardware articles ---- */
  {
    id: 'PART:NSN-4472', type: 'Part', name: 'CMC Nose Cone Assembly 4472', level: 'CUI', ageDays: 171,
    attrs: {
      partNumber: 'NSN-4472', name: 'CMC Nose Cone Assembly 4472', partType: 'CMC_NOSECAP', revision: 'C',
      criticality: 'CRITICAL', isSingleSource: true, exportControlled: true, leadTimeDays: 420,
      materialIds: ['MAT:LOT-CMC-2291'], processPlanIds: ['PP:AUTOCLAVE-01'],
      unitCost: { amount: 1_840_000, currency: 'USD', basis: 'QUOTE', confidence: 0.81 },
    },
    labels: { supplyRisk: 'critical' },
  },
  {
    id: 'PART:LEAD-1180', type: 'Part', name: 'UHTC Leading Edge Panel 1180', level: 'CUI', ageDays: 168,
    attrs: {
      partNumber: 'LEAD-1180', name: 'UHTC Leading Edge Panel 1180', partType: 'TPS', revision: 'B',
      criticality: 'CRITICAL', isSingleSource: true, exportControlled: true, leadTimeDays: 395,
      materialIds: ['MAT:LOT-CMC-4470'], processPlanIds: ['PP:PYROLYYSIS-02'],
      unitCost: { amount: 940_000, currency: 'USD', basis: 'PARAMETRIC', confidence: 0.55 },
    },
  },
  {
    id: 'PART:FIN-2207', type: 'Part', name: 'Control Fin Assembly 2207', level: 'CUI', ageDays: 140,
    attrs: {
      partNumber: 'FIN-2207', name: 'Control Fin Assembly 2207', partType: 'STRUCTURAL', revision: 'A',
      criticality: 'KEY', isSingleSource: false, leadTimeDays: 210,
      processPlanIds: ['PP:MACH-COAT-04'],
      unitCost: { amount: 312_000, currency: 'USD', basis: 'ANALOG', confidence: 0.48 },
    },
  },
  {
    id: 'PART:SEAKER-A3', type: 'Part', name: 'Hypersonic Seeker Head A3', level: 'CUI', ageDays: 132,
    attrs: {
      partNumber: 'SEAKER-A3', name: 'Hypersonic Seeker Head A3', partType: 'AVIONICS', revision: 'D',
      criticality: 'CRITICAL', isSingleSource: true, exportControlled: true, leadTimeDays: 540,
      unitCost: { amount: 4_150_000, currency: 'USD', basis: 'QUOTE', confidence: 0.74 },
    },
  },
  {
    id: 'PART:AVIONICS-77', type: 'Part', name: 'Avionics Rack Gen 7', level: 'CUI', ageDays: 118,
    attrs: {
      partNumber: 'AVIONICS-77', name: 'Avionics Rack Gen 7', partType: 'AVIONICS', revision: 'B',
      criticality: 'KEY', isSingleSource: false, leadTimeDays: 165,
      unitCost: { amount: 1_120_000, currency: 'USD', basis: 'ACTUAL', confidence: 0.88 },
    },
  },
  {
    id: 'PART:FAST-0092', type: 'Part', name: 'High Temp Fastener Set 0092', level: 'CUI', ageDays: 105,
    attrs: {
      partNumber: 'FAST-0092', name: 'High Temp Fastener Set 0092', partType: 'FASTENER', revision: 'A',
      criticality: 'STANDARD', isSingleSource: false, leadTimeDays: 45,
      unitCost: { amount: 18_400, currency: 'USD', basis: 'ACTUAL', confidence: 0.91 },
    },
  },
  {
    id: 'PART:ACT-3320', type: 'Part', name: 'Actuation Assembly 3320', level: 'CUI', ageDays: 92,
    attrs: {
      partNumber: 'ACT-3320', name: 'Actuation Assembly 3320', partType: 'PROPULSION', revision: 'A',
      criticality: 'KEY', isSingleSource: false, leadTimeDays: 190,
      unitCost: { amount: 226_000, currency: 'USD', basis: 'ANALOG', confidence: 0.52 },
    },
  },

  /* ---- Materials ---- */
  {
    id: 'MAT:LOT-CMC-2291', type: 'Material', name: 'CMC Prepreg Lot 2291', level: 'CUI', ageDays: 168,
    attrs: {
      materialType: 'CMC_PREG', lotNumber: 'LOT-2291', batchId: 'B-2291-A',
      supplierId: 'SUP:ARCLITE-07', processPlanIds: ['PP:AUTOCLAVE-01'], characterizationIds: ['MDL:THERM-3.1'],
      certifications: ['ISO-13314', 'CMMC-L2'], receivedAt: isoAt(daysAgo(168)),
      microstructureSummary: 'Dense 2D weave, 6 ply carbon/carbon, porosity 3.1% (spec <4.5%).',
    },
  },
  {
    id: 'MAT:LOT-CMC-4470', type: 'Material', name: 'UHTC Prepreg Lot 4470', level: 'CUI', ageDays: 120,
    attrs: {
      materialType: 'CMC_PREG', lotNumber: 'LOT-4470', batchId: 'B-4470-C',
      supplierId: 'SUP:NANOFAB-03', processPlanIds: ['PP:PYROLYYSIS-02'], characterizationIds: ['MDL:THERM-3.1'],
      certifications: ['ISO-13314'], receivedAt: isoAt(daysAgo(120)),
      microstructureSummary: 'C/SiC with CVI silicon infiltration depth 0.42 mm (spec >0.35 mm).',
    },
  },
  {
    id: 'MAT:BILLET-0088', type: 'Material', name: 'UHTC Billet 0088', level: 'CUI', ageDays: 134,
    attrs: {
      materialType: 'CMC_BILLET', lotNumber: 'BILLET-0088', batchId: 'B-0088-A',
      supplierId: 'SUP:KYTEC-22', processPlanIds: ['PP:PYROLYSIS-02'], characterizationIds: ['MDL:AERO-6.2'],
      certifications: ['CMMC-L2'], receivedAt: isoAt(daysAgo(134)),
      microstructureSummary: 'Pyrolysis core with residual porosity 5.8% (spec <6.0%, marginal).',
    },
  },

  /* ---- Process definition and execution ---- */
  {
    id: 'PP:AUTOCLAVE-01', type: 'ProcessPlan', name: 'Autoclave Cure Cycle A', level: 'CUI', ageDays: 200,
    attrs: {
      name: 'Autoclave Cure Cycle A', processType: 'AUTOCLAVE', revision: 'A3', qualificationStatus: 'QUALIFIED',
      qualifiedFacilityIds: ['FAC:MR-01'],
      operations: [
        { opId: 'OP-010', name: 'Tool release and layup', parameters: { layupTempC: 22, humidityPct: 38 }, requiredSkillIds: ['SKL:CMC-LAM-3'], equipmentTags: ['TOOL-04', 'TOOL-07'] },
        { opId: 'OP-020', name: 'Vacuum debulk', parameters: { vacuumInHg: 28, durationMin: 90 }, requiredSkillIds: ['SKL:CMC-LAM-3'], equipmentTags: ['DEBULK-01'] },
        { opId: 'OP-030', name: 'Autoclave cure', parameters: { tempC: 1820, pressurePsi: 185, holdMin: 240 }, specLimits: { tempC: [1800, 1840], pressurePsi: [180, 190] }, requiredSkillIds: ['SKL:CMC-LAM-3'], equipmentTags: ['AC-02'] },
      ],
    },
  },
  {
    id: 'PP:PYROLYSIS-02', type: 'ProcessPlan', name: 'Carbon Pyrolysis and Infiltration', level: 'CUI', ageDays: 188,
    attrs: {
      name: 'Carbon Pyrolysis and Infiltration', processType: 'PYROLYSIS', revision: 'B1', qualificationStatus: 'QUALIFIED',
      qualifiedFacilityIds: ['FAC:MR-01'],
      operations: [
        { opId: 'OP-010', name: 'Green body densification', parameters: { pressMPa: 25 }, requiredSkillIds: ['SKL:PYRO-OP-1'], equipmentTags: ['HP-01'] },
        { opId: 'OP-020', name: 'Pyrolysis', parameters: { tempC: 1650, hours: 42, atmo: 'N2' }, specLimits: { tempC: [1620, 1680] }, requiredSkillIds: ['SKL:PYRO-OP-1'], equipmentTags: ['FUR-03'] },
        { opId: 'OP-030', name: 'Silicon infiltration', parameters: { hours: 96 }, requiredSkillIds: ['SKL:PYRO-OP-1'], equipmentTags: ['CVI-01'] },
      ],
    },
  },
  {
    id: 'PP:NDT-01', type: 'ProcessPlan', name: 'NDT Inspection Plan CMC-01', level: 'CUI', ageDays: 176,
    attrs: {
      name: 'NDT Inspection Plan CMC-01', processType: 'NDT', revision: 'D2', qualificationStatus: 'QUALIFIED',
      qualifiedFacilityIds: ['FAC:MR-01'],
      operations: [
        { opId: 'OP-010', name: 'Ultrasonic C-scan', parameters: { freqMHz: 10 }, requiredSkillIds: ['SKL:NDT-ET-2'], equipmentTags: ['UT-11'] },
        { opId: 'OP-020', name: 'Eddy current surface scan', parameters: { freqKHz: 120 }, requiredSkillIds: ['SKL:NDT-ET-2'], equipmentTags: ['ET-04'] },
      ],
    },
  },
  {
    id: 'PP:MACH-COAT-04', type: 'ProcessPlan', name: 'Machining and Thermal Spray', level: 'CUI', ageDays: 140,
    attrs: {
      name: 'Machining and Thermal Spray', processType: 'MACHINING', revision: 'A1', qualificationStatus: 'QUALIFICATION_IN_PROGRESS',
      qualifiedFacilityIds: ['FAC:PLANT-02'],
      operations: [
        { opId: 'OP-010', name: '5-axis rough and finish', parameters: { feedMmPerMin: 180 }, requiredSkillIds: ['SKL:MACH-5X-2'], equipmentTags: ['MC-07'] },
        { opId: 'OP-020', name: 'YSZ thermal spray', parameters: { tempC: 980, thicknessUm: 120 }, requiredSkillIds: ['SKL:SPRAY-1'], equipmentTags: ['SPR-02'] },
      ],
    },
  },
  {
    id: 'PR:01J8ZWQ4T7B', type: 'ProcessRun', name: 'Autoclave Run 2291-07', level: 'CUI', ageDays: 164,
    attrs: {
      processPlanId: 'PP:AUTOCLAVE-01', materialId: 'MAT:LOT-CMC-2291', partId: 'PART:NSN-4472', facilityId: 'FAC:MR-01',
      startedAt: isoAt(daysAgo(165)), endedAt: isoAt(daysAgo(164)),
      operatorId: PERSON_IDS.vasquez, disposition: 'ACCEPTED',
      measuredParameters: { peakTempC: 1816, peakPressurePsi: 186, vacuumInHg: 29 },
      driftFlags: [],
    },
  },
  {
    id: 'PR:01J8ZWR9K2M', type: 'ProcessRun', name: 'Pyrolysis Run 0088-03', level: 'CUI', ageDays: 131,
    attrs: {
      processPlanId: 'PP:PYROLYSIS-02', materialId: 'MAT:BILLET-0088', partId: 'PART:LEAD-1180', facilityId: 'FAC:MR-01',
      startedAt: isoAt(daysAgo(132)), endedAt: isoAt(daysAgo(131)),
      operatorId: PERSON_IDS.lindqvist, disposition: 'REWORK', nonconformanceId: 'NCR-2026-0117',
      measuredParameters: { peakTempC: 1668, residualPorosityPct: 5.8 },
      driftFlags: ['RESIDUAL_POROSITY_HIGH'],
    },
  },
  {
    id: 'PR:01J8ZW2N6F9', type: 'ProcessRun', name: 'NDT Run 4472-01', level: 'CUI', ageDays: 158,
    attrs: {
      processPlanId: 'PP:NDT-01', materialId: 'MAT:LOT-CMC-2291', partId: 'PART:NSN-4472', facilityId: 'FAC:MR-01',
      startedAt: isoAt(daysAgo(159)), endedAt: isoAt(daysAgo(158)),
      operatorId: PERSON_IDS.bhatt, disposition: 'ACCEPTED',
      measuredParameters: { indicationsAboveAcceptance: 0, coveragePct: 98.2 },
      driftFlags: [],
    },
  },

  /* ---- Test articles, campaigns, results ---- */
  {
    id: 'TA:TA-0007', type: 'TestArticle', name: 'Airframe TA-0007', level: 'CUI', ageDays: 74,
    attrs: {
      serialNumber: 'TA-0007-SN114', variantId: 'VAR:HGV-B1', partIds: ['PART:NSN-4472', 'PART:LEAD-1180', 'PART:FIN-2207'],
      buildConfigurationId: 'CFG-2026-014', asBuiltStatus: 'DEVIATED',
      deviations: [{ field: 'partIds', detail: 'Leading edge replaced with LEAD-1180 rev B (supernetted).' }],
    },
  },
  {
    id: 'TA:TA-0012', type: 'TestArticle', name: 'Airframe TA-0012', level: 'CUI', ageDays: 38,
    attrs: {
      serialNumber: 'TA-0012-SN118', variantId: 'VAR:HGV-B2', partIds: ['PART:NSN-4472', 'PART:SEAKER-A3', 'PART:ACT-3320'],
      buildConfigurationId: 'CFG-2026-031', asBuiltStatus: 'AS_BUILT', deviations: [],
    },
  },
  {
    id: 'TC:WT-26-04', type: 'TestCampaign', name: 'Wind Tunnel Campaign WT-26-04', level: 'CUI', ageDays: 62,
    attrs: {
      name: 'Wind Tunnel Campaign WT-26-04', campaignType: 'WIND_TUNNEL', status: 'COMPLETE',
      objectives: ['Confirm heating rate at Mach 5.8 transition', 'Capture heat flux on leading edge', 'Correlate to MDL:AERO-6.2'],
      requirementIds: ['REQ:NGH-0012', 'REQ:NGH-0031', 'REQ:NGH-0055'],
      testArticleIds: ['TA:TA-0007'], rangeSlotIds: ['RS:2026-03-14A'],
      instrumentationManifest: [{ sensorId: 'PHOT-PD', sampleRateHz: 5000, channel: 'Qdot' }, { sensorId: 'IR-CAM', sampleRateHz: 200, channel: 'T_surface' }],
      dataSetUris: ['s3://ngsh-testdata/wt-26-04/raw/'],
    },
  },
  {
    id: 'TC:FLT-26-02', type: 'TestCampaign', name: 'Flight Demonstration FLT-26-02', level: 'CUI', ageDays: 21,
    attrs: {
      name: 'Flight Demonstration FLT-26-02', campaignType: 'FLIGHT', status: 'ACTIVE',
      objectives: ['Closed-loop seeker acquisition against a boosting target', 'GNC response to surface heating'],
      requirementIds: ['REQ:NGH-0024', 'REQ:NGH-0074'],
      testArticleIds: ['TA:TA-0012'], rangeSlotIds: ['RS:2026-04-02B'],
      instrumentationManifest: [{ sensorId: 'TELEM-B', sampleRateHz: 100, channel: 'nav' }],
      dataSetUris: ['s3://ngsh-testdata/flt-26-02/raw/'],
    },
  },
  {
    id: 'TC:HMTC-26-01', type: 'TestCampaign', name: 'Manufacturing Test Campaign HMTC-26-01', level: 'CUI', ageDays: 12,
    attrs: {
      name: 'Manufacturing Test Campaign HMTC-26-01', campaignType: 'QUALIFICATION', status: 'PLANNED',
      objectives: ['Qualify autoclave cure cycle at production rate', 'Demonstrate NDT throughput for surge'],
      requirementIds: ['REQ:NGH-0042', 'REQ:NGH-0093'],
      testArticleIds: ['TA:TA-0012'], rangeSlotIds: [],
      instrumentationManifest: [{ sensorId: 'AC-LOG', sampleRateHz: 10, channel: 'cycle' }],
      dataSetUris: [],
    },
  },
  {
    id: 'TR:01J8ZW4C7T2', type: 'TestResult', name: 'Cp-DAT-042 Heating Rate', level: 'CUI', ageDays: 58,
    attrs: {
      campaignId: 'TC:WT-26-04', testArticleId: 'TA:TA-0007', testMethod: 'Cp-DAT-042', outcome: 'PASS',
      measurements: [
        { name: 'peak_heat_flux', value: 1142, unit: 'kW/m2', uncertainty: 41, method: 'Cp-DAT-042' },
        { name: 'stagnation_point_temp', value: 1934, unit: 'K', uncertainty: 28, method: 'Cp-DAT-042' },
      ],
      limits: { peak_heat_flux: 1200 },
      configurationSnapshot: { variant: 'HGV-B1', lot: 'LOT-2291', partRevisions: { 'NSN-4472': 'C' }, softwareBuild: 'GNC-9.4.1', calibration: '2026-02-11' },
      dataSetUris: ['s3://ngsh-testdata/wt-26-04/run/042/'], modelVersionIds: ['MDL:AERO-6.2', 'MDL:THERM-3.1'],
      baselineId: 'BL-2026-03', anomalyFlags: [], reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZW5D8U3', type: 'TestResult', name: 'Cp-DAT-042 Repeat Heating Rate', level: 'CUI', ageDays: 56,
    attrs: {
      campaignId: 'TC:WT-26-04', testArticleId: 'TA:TA-0007', testMethod: 'Cp-DAT-042', outcome: 'MARGINAL',
      measurements: [{ name: 'peak_heat_flux', value: 1218, unit: 'kW/m2', uncertainty: 46 }],
      limits: { peak_heat_flux: 1200 },
      configurationSnapshot: { variant: 'HGV-B1', lot: 'LOT-2291', softwareBuild: 'GNC-9.4.1' },
      modelVersionIds: ['MDL:AERO-6.2'], anomalyFlags: ['HEAT_FLUX_OVER_LIMIT'],
      reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZW6E9V4', type: 'TestResult', name: 'Transition Onset Verification', level: 'CUI', ageDays: 54,
    attrs: {
      campaignId: 'TC:WT-26-04', testArticleId: 'TA:TA-0007', testMethod: 'Cp-TRN-011', outcome: 'PASS',
      measurements: [{ name: 'mach_at_transition', value: 5.42, unit: 'Mach', uncertainty: 0.04 }],
      limits: { mach_at_transition: 5.5 },
      configurationSnapshot: { variant: 'HGV-B1', softwareBuild: 'GNC-9.4.1' },
      modelVersionIds: ['MDL:AERO-6.2'], anomalyFlags: [], reviewedBy: PERSON_IDS.vasquez,
    },
  },
  {
    id: 'TR:01J8ZW7F0W5', type: 'TestResult', name: 'GNC Response to Heated Surface', level: 'CUI', ageDays: 19,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-GNC-118', outcome: 'PASS',
      measurements: [{ name: 'nav_error_rms', value: 1.8, unit: 'm', uncertainty: 0.3 }],
      limits: { nav_error_rms: 3.0 },
      configurationSnapshot: { variant: 'HGV-B2', softwareBuild: 'GNC-9.6.0' },
      modelVersionIds: ['MDL:GNC-9.4'], anomalyFlags: [], reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZW8G1X6', type: 'TestResult', name: 'Seeker Acquisition in Plasma', level: 'CUI', ageDays: 17,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-SEE-207', outcome: 'FAIL',
      measurements: [{ name: 'lock_on_probability', value: 0.61, unit: 'Pk' }],
      limits: { lock_on_probability: 0.8 },
      configurationSnapshot: { variant: 'HGV-B2', softwareBuild: 'SEE-2.1.4' },
      modelVersionIds: ['MDL:DETECT-1.3'], anomalyFlags: ['PLASMA_ATTENUATION'],
      reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZW9H2Y7', type: 'TestResult', name: 'Autoclave Cure Cycle Verification', level: 'CUI', ageDays: 10,
    attrs: {
      campaignId: 'TC:HMTC-26-01', testArticleId: 'TA:TA-0012', testMethod: 'Cp-MFG-003', outcome: 'NOT_RUN',
      measurements: [],
      configurationSnapshot: { variant: 'HGV-B2', lot: 'LOT-4470' },
      anomalyFlags: [], reviewedBy: PERSON_IDS.vasquez,
    },
  },
  {
    id: 'TR:01J8ZWA3J3Z8', type: 'TestResult', name: 'NDT Porosity Inspection', level: 'CUI', ageDays: 26,
    attrs: {
      campaignId: 'TC:HMTC-26-01', testArticleId: 'TA:TA-0012', testMethod: 'Cp-NDT-021', outcome: 'PASS',
      measurements: [{ name: 'porosity_pct', value: 3.1, unit: '%' }],
      limits: { porosity_pct: 4.5 },
      configurationSnapshot: { lot: 'LOT-4470' }, anomalyFlags: [], reviewedBy: PERSON_IDS.bhatt,
    },
  },
  {
    id: 'TR:01J8ZWA4K4A9', type: 'TestResult', name: 'Thermal Cycle Survival', level: 'CUI', ageDays: 23,
    attrs: {
      campaignId: 'TC:WT-26-04', testArticleId: 'TA:TA-0012', testMethod: 'Cp-ENV-030', outcome: 'INCONCLUSIVE',
      measurements: [{ name: 'cycles_completed', value: 6, unit: 'cycles' }],
      limits: { cycles_completed: 10 },
      configurationSnapshot: { variant: 'HGV-B2', lot: 'LOT-4470' },
      anomalyFlags: ['FACILITY_INTERRUPTION'], reviewedBy: PERSON_IDS.vasquez,
    },
  },

  /* ---- Recent activity: flight campaign FLT-26-02, live in the last hours ---- */
  {
    id: 'TR:01J8ZY9A1B2C3', type: 'TestResult', name: 'Flight GNC Response Repeat', level: 'CUI', ageDays: 0, ageHours: 2.6,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-GNC-118', outcome: 'PASS',
      measurements: [{ name: 'nav_error_rms', value: 1.6, unit: 'm', uncertainty: 0.25 }],
      limits: { nav_error_rms: 3.0 },
      configurationSnapshot: { variant: 'HGV-B2', softwareBuild: 'GNC-9.6.0', calibration: '2026-11-12' },
      dataSetUris: ['s3://ngsh-testdata/flt-26-02/run/gnc-r2/'], modelVersionIds: ['MDL:GNC-9.4'],
      baselineId: 'BL-2026-11', anomalyFlags: [], reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZY8B2C3D4', type: 'TestResult', name: 'Seeker Plasma Retest', level: 'CUI', ageDays: 0, ageHours: 2.2,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-SEE-207', outcome: 'MARGINAL',
      measurements: [{ name: 'lock_on_probability', value: 0.77, unit: 'Pk' }],
      limits: { lock_on_probability: 0.8 },
      configurationSnapshot: { variant: 'HGV-B2', softwareBuild: 'SEE-2.1.5' },
      modelVersionIds: ['MDL:DETECT-1.3'], anomalyFlags: ['PLASMA_ATTENUATION'],
      reviewedBy: PERSON_IDS.lindqvist,
    },
  },
  {
    id: 'TR:01J8ZY7C3D4E5', type: 'TestResult', name: 'Navigation Update Rate', level: 'CUI', ageDays: 0, ageHours: 1.9,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-GNC-121', outcome: 'PASS',
      measurements: [{ name: 'update_rate_hz', value: 49.8, unit: 'Hz' }],
      limits: { update_rate_hz: 50 },
      configurationSnapshot: { variant: 'HGV-B2', softwareBuild: 'GNC-9.6.0' },
      anomalyFlags: [], reviewedBy: PERSON_IDS.vasquez,
    },
  },
  {
    id: 'TR:01J8ZY6D4E5F6', type: 'TestResult', name: 'Heat Shield Recession', level: 'CUI', ageDays: 0, ageHours: 1.6,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-TPS-118', outcome: 'PASS',
      measurements: [{ name: 'recession_mm', value: 0.18, unit: 'mm', uncertainty: 0.04 }],
      limits: { recession_mm: 0.25 },
      configurationSnapshot: { variant: 'HGV-B2', lot: 'LOT-4470' },
      modelVersionIds: ['MDL:THERM-3.1'], anomalyFlags: [], reviewedBy: PERSON_IDS.bhatt,
    },
  },
  {
    id: 'TR:01J8ZY5E5F6G7', type: 'TestResult', name: 'Plasma Sheath Telemetry', level: 'CUI', ageDays: 0, ageHours: 1.1,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-TELEM-044', outcome: 'INCONCLUSIVE',
      measurements: [{ name: 'signal_to_noise_db', value: 4.1, unit: 'dB' }],
      limits: { signal_to_noise_db: 6 },
      configurationSnapshot: { variant: 'HGV-B2' },
      anomalyFlags: ['TELEMETRY_GAP'], reviewedBy: PERSON_IDS.vasquez,
    },
  },
  {
    id: 'TR:01J8ZY4F6G7H8', type: 'TestResult', name: 'Thermal Sensor Cross-Check', level: 'CUI', ageDays: 0, ageHours: 0.7,
    attrs: {
      campaignId: 'TC:FLT-26-02', testArticleId: 'TA:TA-0012', testMethod: 'Cp-TELEM-051', outcome: 'PASS',
      measurements: [{ name: 'sensor_delta_c', value: 4.2, unit: 'degC', uncertainty: 1.1 }],
      limits: { sensor_delta_c: 8 },
      configurationSnapshot: { variant: 'HGV-B2', calibration: '2026-11-12' },
      anomalyFlags: [], reviewedBy: PERSON_IDS.bhatt,
    },
  },

  /* ---- Requirements ---- */
  {
    id: 'REQ:NGH-0012', type: 'Requirement', name: 'Sustained heating at Mach 5.8', level: 'CUI', ageDays: 210,
    attrs: {
      statement: 'The vehicle shall sustain flight without structural damage at Mach 5.8 at 30 km altitude.',
      text: 'The vehicle shall sustain flight without structural damage at Mach 5.8 and 30 km altitude for 180 seconds.',
      reqType: 'PERFORMANCE', verificationMethod: 'TEST', status: 'BASELINED', verificationStatus: 'PARTIAL',
      parentId: 'REQ:NGH-0004', allocatedToIds: ['PART:LEAD-1180', 'SUB:TPS-01'],
      acceptanceCriteria: 'No structural damage; peak heat flux below 1200 kW/m2.',
      costDrivers: ['NSN-4472', 'LEAD-1180'],
    },
  },
  {
    id: 'REQ:NGH-0024', type: 'Requirement', name: 'Seeker lock in plasma environment', level: 'CUI', ageDays: 198,
    attrs: {
      statement: 'The seeker shall achieve single-shot lock probability of 0.80 in a Mach 5.8 plasma environment.',
      reqType: 'PERFORMANCE', verificationMethod: 'TEST', status: 'BASELINED', verificationStatus: 'IN_PROGRESS',
      parentId: 'REQ:NGH-0004', allocatedToIds: ['PART:SEAKER-A3', 'SUB:SEAKER-01'],
      acceptanceCriteria: 'Pk >= 0.80 over 20 engagements.',
    },
  },
  {
    id: 'REQ:NGH-0031', type: 'Requirement', name: 'Navigation accuracy under thermal distortion', level: 'CUI', ageDays: 190,
    attrs: {
      statement: 'The GNC shall maintain navigation error RMS below 3.0 m with thermally distorted airframe.',
      reqType: 'PERFORMANCE', verificationMethod: 'TEST', status: 'IMPLEMENTED', verificationStatus: 'PARTIAL',
      parentId: 'REQ:NGH-0004', allocatedToIds: ['SUB:GNC-01'],
      acceptanceCriteria: 'RMS <= 3.0 m over the last 300 s of flight.',
    },
  },
  {
    id: 'REQ:NGH-0042', type: 'Requirement', name: 'Autoclave cycle repeatability at production rate', level: 'CUI', ageDays: 176,
    attrs: {
      statement: 'The cure cycle shall meet porosity specification at 120 articles per year throughput.',
      reqType: 'PERFORMANCE', verificationMethod: 'TEST', status: 'ALLOCATED', verificationStatus: 'NOT_STARTED',
      parentId: 'REQ:NGH-0009', allocatedToIds: ['PP:AUTOCLAVE-01', 'FAC:MR-01'],
      acceptanceCriteria: 'Porosity <= 4.5% on 95% of lots.',
    },
  },
  {
    id: 'REQ:NGH-0055', type: 'Requirement', name: 'Transition onset prediction accuracy', level: 'CUI', ageDays: 166,
    attrs: {
      statement: 'The aerodynamic model shall predict transition onset within Mach 0.1.',
      reqType: 'PERFORMANCE', verificationMethod: 'ANALYSIS', status: 'BASELINED', verificationStatus: 'PARTIAL',
      parentId: 'REQ:NGH-0009', allocatedToIds: ['MDL:AERO-6.2'],
      acceptanceCriteria: 'Abs error <= 0.1 Mach against wind tunnel data.',
    },
  },
  {
    id: 'REQ:NGH-0061', type: 'Requirement', name: 'Supplier continuity for UHTC precursors', level: 'CUI', ageDays: 120,
    attrs: {
      statement: 'The program shall maintain a qualified second source for UHTC precursors within 24 months.',
      reqType: 'CONSTRAINT', verificationMethod: 'INSPECTION', status: 'DRAFT', verificationStatus: 'NOT_STARTED',
      allocatedToIds: ['SUP:NANOFAB-03'],
      acceptanceCriteria: 'Qualified alternate source with an active qualification lot.',
    },
  },
  {
    id: 'REQ:NGH-0074', type: 'Requirement', name: 'Detect-to-custody handover time', level: 'RESTRICTED', ageDays: 110,
    attrs: {
      statement: 'The detect-to-custody handover shall complete within 120 seconds.',
      reqType: 'PERFORMANCE', verificationMethod: 'DEMONSTRATION', status: 'BASELINED', verificationStatus: 'IN_PROGRESS',
      allocatedToIds: ['SYS:SENSOR-HBTSS', 'ESC:DETECT-CUSTODY-02'],
      acceptanceCriteria: 'Handover within 120 s in 90% of Monte Carlo runs.',
    },
  },
  {
    id: 'REQ:NGH-0088', type: 'Requirement', name: 'Cleared workforce coverage for autoclave operations', level: 'CUI', ageDays: 104,
    attrs: {
      statement: 'At least 14 personnel shall hold a current CMC layup level 3 credential per shift.',
      reqType: 'QUALITY', verificationMethod: 'INSPECTION', status: 'ALLOCATED', verificationStatus: 'PARTIAL',
      allocatedToIds: ['SKL:CMC-LAM-3', 'FAC:MR-01'],
      acceptanceCriteria: 'Credentialed headcount meets shift requirement.',
    },
  },
  {
    id: 'REQ:NGH-0093', type: 'Requirement', name: 'Surge reconstitution time for nose cone', level: 'CUI', ageDays: 92,
    attrs: {
      statement: 'Nose cone production shall be reconstituted within 180 days after a single-source loss.',
      reqType: 'CONSTRAINT', verificationMethod: 'ANALYSIS', status: 'DRAFT', verificationStatus: 'NOT_STARTED',
      allocatedToIds: ['PART:NSN-4472', 'FAC:MR-01'],
      acceptanceCriteria: 'Documented reconstitution playbook with qualified alternate facility.',
    },
  },
  {
    id: 'REQ:NGH-0102', type: 'Requirement', name: 'Interface data integrity GNC to avionics', level: 'CUI', ageDays: 78,
    attrs: {
      statement: 'The GNC to avionics interface shall sustain 10 MB/s with end-to-end latency below 5 ms.',
      reqType: 'INTERFACE', verificationMethod: 'TEST', status: 'IMPLEMENTED', verificationStatus: 'COMPLETE',
      allocatedToIds: ['IF:ICD-GNC-05', 'PART:AVIONICS-77'],
      acceptanceCriteria: 'Latency <= 5 ms at 99th percentile over 1 hour.',
    },
  },
  {
    id: 'REQ:NGH-0117', type: 'Requirement', name: 'Threat reconstruction confidence floor', level: 'RESTRICTED', ageDays: 64,
    attrs: {
      statement: 'A threat reconstruction shall not be published with confidence below 0.70 without review.',
      reqType: 'SECURITY', verificationMethod: 'ANALYSIS', status: 'BASELINED', verificationStatus: 'PARTIAL',
      allocatedToIds: ['THR:HGV-X9', 'MDL:THREAT-KIN-2.0'],
      acceptanceCriteria: 'Confidence >= 0.70 or documented analyst review.',
    },
  },

  /* ---- Interfaces, models ---- */
  {
    id: 'IF:ICD-GNC-05', type: 'Interface', name: 'ICD GNC to Avionics Rev 5', level: 'CUI', ageDays: 152,
    attrs: {
      name: 'ICD GNC to Avionics Rev 5', fromSystemId: 'SUB:GNC-01', toSystemId: 'PART:AVIONICS-77', icdVersion: '5.2',
      dataItems: [{ name: 'nav_state', rateHz: 100 }, { name: 'guidance_cmd', rateHz: 50 }],
      characteristics: { rateMbps: 10, latencyMs: 4.2, timingTolerancePpm: 50 },
    },
  },
  {
    id: 'IF:ICD-TPS-02', type: 'Interface', name: 'ICD Thermal Protection Segment Rev 2', level: 'CUI', ageDays: 148,
    attrs: {
      name: 'ICD Thermal Protection Segment Rev 2', fromSystemId: 'SUB:TPS-01', toSystemId: 'PART:LEAD-1180', icdVersion: '2.1',
      dataItems: [{ name: 'surface_state', rateHz: 20 }],
      characteristics: { rateMbps: 2, latencyMs: 18 },
    },
  },
  {
    id: 'MDL:AERO-6.2', type: 'Model', name: 'Aerodynamic Database 6.2', level: 'CUI', ageDays: 128,
    attrs: {
      name: 'Aerodynamic Database 6.2', modelType: 'AERODYNAMIC', modelVersion: '6.2.0', approvedForUse: true,
      codeRef: 'ngsh-mdl/aero@6.2.0', inputSchemaRef: 'schemas/aero-input-6.json', outputSchemaRef: 'schemas/aero-output-6.json',
      modelCard: 'artifacts/model-cards/aero-6.2.md',
      fidelity: { overall: 0.87, method: 'rmse-vs-baseline-normalised', components: { hypersonic: 0.91, transition: 0.79, roll: 0.85 }, evaluatedAt: isoAt(daysAgo(58)), evidenceRefs: ['TR:01J8ZW4C7T2', 'TR:01J8ZW6E9V4'] },
      runtime: { solver: 'CFD-NS, RANS, SA', nodes: 4096 },
    },
  },
  {
    id: 'MDL:THERM-3.1', type: 'Model', name: 'Thermal Response Model 3.1', level: 'CUI', ageDays: 116,
    attrs: {
      name: 'Thermal Response Model 3.1', modelType: 'THERMAL', modelVersion: '3.1.4', approvedForUse: true,
      codeRef: 'ngsh-mdl/therm@3.1.4', modelCard: 'artifacts/model-cards/therm-3.1.md',
      fidelity: { overall: 0.79, method: 'rmse-vs-baseline-normalised', components: { leadingEdge: 0.83, bulk: 0.74 }, evaluatedAt: isoAt(daysAgo(56)), evidenceRefs: ['TR:01J8ZW4C7T2'] },
    },
  },
  {
    id: 'MDL:MLPRED-1.4', type: 'Model', name: 'CMC Quality Surrogate 1.4', level: 'CUI', ageDays: 72,
    attrs: {
      name: 'CMC Quality Surrogate 1.4', modelType: 'SURROGATE_ML', modelVersion: '1.4.2', approvedForUse: false,
      codeRef: 'ngsh-mdl/mlpred@1.4.2', modelCard: 'artifacts/model-cards/mlpred-1.4.md',
      fidelity: { overall: 0.71, method: 'rmse-vs-baseline-normalised', components: { porosity: 0.76 }, evaluatedAt: isoAt(daysAgo(26)), evidenceRefs: ['TR:01J8ZWA3J3Z8'] },
    },
  },
  {
    id: 'MDL:THREAT-KIN-2.0', type: 'Model', name: 'Threat Kinematic Profile 2.0', level: 'RESTRICTED', ageDays: 60,
    attrs: {
      name: 'Threat Kinematic Profile 2.0', modelType: 'THREAT_KINEMATIC', modelVersion: '2.0.1', approvedForUse: true,
      codeRef: 'ngsh-mdl/threatkin@2.0.1',
      fidelity: { overall: 0.68, method: 'rmse-vs-baseline-normalised', components: { mach: 0.74 }, evaluatedAt: isoAt(daysAgo(30)), evidenceRefs: ['TOBS:01J8ZWB5L5C1'] },
    },
  },
  {
    id: 'MDL:GNC-9.4', type: 'Model', name: 'GNC Software Model 9.4', level: 'CUI', ageDays: 44,
    attrs: {
      name: 'GNC Software Model 9.4', modelType: 'GNC', modelVersion: '9.4.1', approvedForUse: true,
      codeRef: 'ngsh-mdl/gnc@9.4.1',
      fidelity: { overall: 0.9, method: 'rmse-vs-baseline-normalised', components: { navigation: 0.92 }, evaluatedAt: isoAt(daysAgo(19)), evidenceRefs: ['TR:01J8ZW7F0W5'] },
    },
  },

  /* ---- Threat side ---- */
  {
    id: 'THR:HGV-X9', type: 'ThreatSystem', name: 'Adversary HGV-X9', level: 'RESTRICTED', ageDays: 54,
    attrs: {
      designation: 'HGV-X9', threatClass: 'HGV', confidence: 0.74,
      kinematicProfile: { mach: [5.1, 5.9], altitudeKm: 28, rangeKm: 1800, accelG: 2.4 },
      observationIds: ['TOBS:01J8ZWB5L5C1', 'TOBS:01J8ZWC6M6D2'],
      modelVersionIds: ['MDL:THREAT-KIN-2.0'],
    },
  },
  {
    id: 'THR:BOOSTGLIDE-3', type: 'ThreatSystem', name: 'Adversary Boost Glide 3', level: 'RESTRICTED', ageDays: 41,
    attrs: {
      designation: 'BOOSTGLIDE-3', threatClass: 'BOOSTED_GLIDE', confidence: 0.61,
      kinematicProfile: { mach: [6.0, 6.6], altitudeKm: 34, rangeKm: 2400 },
      observationIds: ['TOBS:01J8ZWC6M6D2'],
      modelVersionIds: ['MDL:THREAT-KIN-2.0'],
    },
  },
  {
    id: 'TOBS:01J8ZWB5L5C1', type: 'ThreatObservation', name: 'Observation HGV-X9 pass 1', level: 'RESTRICTED', ageDays: 52,
    attrs: {
      observationTime: isoAt(daysAgo(52)), sensorIds: ['SENSOR-SPACE-IR-04'], sensorType: 'SPACE_IR', source: 'ngsh:intel-fusion',
      trackQuality: 0.82, rawUri: 's3://ngsh-raw/tobs/hgvx9-pass1/',
      measurements: [{ name: 'mach', value: 5.62, unit: 'Mach', uncertainty: 0.09 }, { name: 'altitude', value: 31.2, unit: 'km', uncertainty: 1.4 }],
    },
  },
  {
    id: 'TOBS:01J8ZWC6M6D2', type: 'ThreatObservation', name: 'Observation HGV-X9 pass 2', level: 'RESTRICTED', ageDays: 28,
    attrs: {
      observationTime: isoAt(daysAgo(28)), sensorIds: ['SENSOR-SPACE-EO-02', 'SENSOR-GROUND-RADAR-07'], sensorType: 'SPACE_EO', source: 'ngsh:intel-fusion',
      trackQuality: 0.69, rawUri: 's3://ngsh-raw/tobs/hgvx9-pass2/',
      measurements: [{ name: 'mach', value: 5.44, unit: 'Mach', uncertainty: 0.12 }, { name: 'range', value: 1640, unit: 'km', uncertainty: 60 }],
    },
  },
  {
    id: 'ESC:DETECT-CUSTODY-02', type: 'EngagementScenario', name: 'Detect to Custody Scenario 02', level: 'RESTRICTED', ageDays: 33,
    attrs: {
      name: 'Detect to Custody Scenario 02', threatSystemIds: ['THR:HGV-X9'],
      defensiveArchitecture: 'HBTSS-cued-Aegis-GPI',
      sensorChain: [{ stage: 'space', asset: 'HBTSS' }, { stage: 'handover', asset: 'Aegis BMD' }],
      effectorChain: [{ stage: 'engage', asset: 'GPI (prototype)' }],
      monteCarloConfig: { runs: 5000, seed: 20260314, confidenceLevel: 0.9 },
      resultsSummary: { detectToCustodySec: 118, pk: 0.72, singleShotPk: 0.41 },
    },
  },

  /* ---- Supply chain ---- */
  {
    id: 'SUP:ARCLITE-07', type: 'Supplier', name: 'Arclite Composites', level: 'CUI', ageDays: 190,
    attrs: {
      name: 'Arclite Composites', tier: 1, riskScore: 0.31, leadTimeDays: 180,
      capabilities: ['CMC prepreg', 'autoclave processing'], certifications: ['ISO-9001', 'AS9100D', 'CMMC-L2'],
      domesticContent: 1.0, exportControlled: false, facilityIds: ['FAC:MR-01'],
    },
  },
  {
    id: 'SUP:KYTEC-22', type: 'Supplier', name: 'Kytec Advanced Materials', level: 'CUI', ageDays: 150,
    attrs: {
      name: 'Kytec Advanced Materials', tier: 2, riskScore: 0.58, leadTimeDays: 240,
      capabilities: ['UHTC billet', 'carbon fiber precursor'], certifications: ['ISO-9001'],
      domesticContent: 0.42, exportControlled: true, facilityIds: [],
    },
  },
  {
    id: 'SUP:NANOFAB-03', type: 'Supplier', name: 'Nanofab Processing', level: 'CUI', ageDays: 122,
    attrs: {
      name: 'Nanofab Processing', tier: 2, riskScore: 0.66, leadTimeDays: 310,
      capabilities: ['CVI silicon infiltration'], certifications: ['ISO-14001'],
      domesticContent: 0.35, exportControlled: true, facilityIds: [],
    },
  },
  {
    id: 'PROV:01J8ZWD6H7D3', type: 'PartProvenance', name: 'Custody Record NSN-4472 Rev C', level: 'CUI', ageDays: 160,
    attrs: {
      partId: 'PART:NSN-4472',
      materialIds: ['MAT:LOT-CMC-2291'],
      processRunIds: ['PR:01J8ZWQ4T7B', 'PR:01J8ZW2N6F9'],
      chainOfCustody: [
        { fromNodeId: 'SUP:ARCLITE-07', toNodeId: 'FAC:MR-01', transferredAt: isoAt(daysAgo(168)), quantity: 40, transferType: 'RECEIPT', custodian: 'ARCLITE-LOG-8841' },
        { fromNodeId: 'FAC:MR-01', toNodeId: 'PART:NSN-4472', transferredAt: isoAt(daysAgo(158)), quantity: 6, transferType: 'PROCESSING', custodian: 'MR-01-KEEPER-22' },
        { fromNodeId: 'PART:NSN-4472', toNodeId: 'FAC:PLANT-02', transferredAt: isoAt(daysAgo(74)), quantity: 2, transferType: 'SHIPMENT', custodian: 'PLANT-02-LOG-0031' },
      ],
    },
  },

  /* ---- Workforce ---- */
  {
    id: 'SKL:CMC-LAM-3', type: 'Skill', name: 'CMC Layup and Cure Level 3', level: 'UNCLASSIFIED', ageDays: 260,
    attrs: {
      name: 'CMC Layup and Cure Level 3', code: 'NGSH-MFG-011', category: 'MANUFACTURING', level: 3,
      qualificationCriteria: ['6 years autoclave operation', 'documented cure cycle qualification'],
      clearanceRequired: 'SECRET',
    },
  },
  {
    id: 'SKL:NDT-ET-2', type: 'Skill', name: 'NDT Eddy Current Level 2', level: 'UNCLASSIFIED', ageDays: 258,
    attrs: {
      name: 'NDT Eddy Current Level 2', code: 'NGSH-QLT-004', category: 'QUALITY', level: 2,
      qualificationCriteria: ['ASNT SNT-TC-1A certification'], clearanceRequired: 'SECRET',
    },
  },
  {
    id: 'SKL:PYRO-OP-1', type: 'Skill', name: 'Pyrolysis Furnace Operator', level: 'UNCLASSIFIED', ageDays: 254,
    attrs: {
      name: 'Pyrolysis Furnace Operator', code: 'NGSH-MFG-022', category: 'MANUFACTURING', level: 2,
      qualificationCriteria: ['3 years furnace operation', 'hazmat hot-work certification'], clearanceRequired: 'SECRET',
    },
  },
  {
    id: 'SKL:FLT-DIR-1', type: 'Skill', name: 'Flight Test Director', level: 'UNCLASSIFIED', ageDays: 250,
    attrs: {
      name: 'Flight Test Director', code: 'NGSH-TST-001', category: 'TEST', level: 4,
      qualificationCriteria: ['range safety qualification', '10 flight campaigns'],
      clearanceRequired: 'TOP SECRET',
    },
  },
  {
    id: 'SKL:MACH-5X-2', type: 'Skill', name: '5-Axis Machining Operator', level: 'UNCLASSIFIED', ageDays: 240,
    attrs: {
      name: '5-Axis Machining Operator', code: 'NGSH-MFG-031', category: 'MANUFACTURING', level: 2,
      qualificationCriteria: ['5 years 5-axis machining', 'CMM interpretation'], clearanceRequired: 'SECRET',
    },
  },
  {
    id: 'CRD:01J8ZWF8N8E4', type: 'Credential', name: 'Credential CMC-LAM-3 — R. Vasquez', level: 'CUI', ageDays: 240,
    attrs: {
      personId: PERSON_IDS.vasquez, skillId: 'SKL:CMC-LAM-3', issuedAt: isoAt(daysAgo(240)), expiresAt: isoAt(daysAgo(-125)),
      issuingAuthority: 'NGSH Workforce Authority', status: 'ACTIVE', workAuthorizationIds: ['WA-AC-02'],
    },
  },
  {
    id: 'CRD:01J8ZWG9P9F5', type: 'Credential', name: 'Credential NDT-ET-2 — A. Bhatt', level: 'CUI', ageDays: 200,
    attrs: {
      personId: PERSON_IDS.bhatt, skillId: 'SKL:NDT-ET-2', issuedAt: isoAt(daysAgo(200)), expiresAt: isoAt(daysAgo(-165)),
      issuingAuthority: 'NGSH Workforce Authority', status: 'ACTIVE', workAuthorizationIds: ['WA-NDT-11'],
    },
  },
  {
    id: 'CRD:01J8ZWH0Q0G6', type: 'Credential', name: 'Credential PYRO-OP-1 — J. Lindqvist', level: 'CUI', ageDays: 180,
    attrs: {
      personId: PERSON_IDS.lindqvist, skillId: 'SKL:PYRO-OP-1', issuedAt: isoAt(daysAgo(180)), expiresAt: isoAt(daysAgo(-12)),
      issuingAuthority: 'NGSH Workforce Authority', status: 'EXPIRED', workAuthorizationIds: ['WA-FUR-03'],
    },
  },
  {
    id: 'PER:01J8ZV7M2A', type: 'Person', name: 'R. Vasquez', level: 'CUI', ageDays: 300,
    attrs: {
      employeeId: 'E-10442', name: 'R. Vasquez', citizenship: 'US', clearanceLevel: 'SECRET',
      clearanceExpiry: isoAt(daysAgo(-240)), role: 'CMC Process Engineer', organization: 'NGSH/Thread Ops', region: 'US-W',
      skillIds: ['SKL:CMC-LAM-3', 'SKL:NDT-ET-2'],
    },
  },
  {
    id: 'PER:01J8ZV8Q4B', type: 'Person', name: 'J. Lindqvist', level: 'CUI', ageDays: 296,
    attrs: {
      employeeId: 'E-10918', name: 'J. Lindqvist', citizenship: 'US', clearanceLevel: 'TOP SECRET',
      clearanceExpiry: isoAt(daysAgo(-90)), role: 'Test Campaign Lead', organization: 'NGSH/Test Enterprise', region: 'US-W',
      skillIds: ['SKL:FLT-DIR-1', 'SKL:PYRO-OP-1'],
    },
  },
  {
    id: 'PER:01J8ZV9R6C', type: 'Person', name: 'A. Bhatt', level: 'CUI', ageDays: 288,
    attrs: {
      employeeId: 'E-11207', name: 'A. Bhatt', citizenship: 'ALLIED', clearanceLevel: 'SECRET',
      clearanceExpiry: isoAt(daysAgo(-150)), role: 'NDT Inspector', organization: 'AFRL/RD', region: 'US-E',
      skillIds: ['SKL:NDT-ET-2'],
    },
  },
  {
    id: 'PER:01J8ZWA1S8D', type: 'Person', name: 'M. Osei', level: 'CUI', ageDays: 270,
    attrs: {
      employeeId: 'E-11551', name: 'M. Osei', citizenship: 'US', clearanceLevel: 'NONE',
      role: 'Supplier Quality Engineer', organization: 'NGSH/Supplier Quality', region: 'US-M',
      skillIds: [],
    },
  },

  /* ---- Facilities and range slots ---- */
  {
    id: 'FAC:MR-01', type: 'Facility', name: 'Materials Research Lab Bay 4', level: 'SECRET', ageDays: 240,
    attrs: {
      name: 'Materials Research Lab Bay 4', facilityType: 'LABORATORY', securityLevel: 'SECRET',
      capabilities: ['autoclave curing', 'pyrolysis', 'CVI infiltration', 'NDT'],
      accreditations: ['CMMC-L2', 'ISO-17025'],
      surgeCapacity: { baselineUnitsPerYear: 40, surgeUnitsPerYear: 120, timeToSurgeDays: 210 },
      constrainedBySkillIds: ['SKL:CMC-LAM-3', 'SKL:PYRO-OP-1'],
    },
  },
  {
    id: 'FAC:WT-03', type: 'Facility', name: 'Wind Tunnel 03', level: 'CUI', ageDays: 200,
    attrs: {
      name: 'Wind Tunnel 03', facilityType: 'TEST', securityLevel: 'CUI',
      capabilities: ['hypersonic wind tunnel', 'model fidelity correlation'],
      accreditations: ['ISO-17025'],
      surgeCapacity: { baselineUnitsPerYear: 90, surgeUnitsPerYear: 140, timeToSurgeDays: 60 },
      constrainedBySkillIds: ['SKL:FLT-DIR-1'],
    },
  },
  {
    id: 'FAC:PLANT-02', type: 'Facility', name: 'Hypersonic Assembly Plant 02', level: 'CUI', ageDays: 180,
    attrs: {
      name: 'Hypersonic Assembly Plant 02', facilityType: 'MANUFACTURING', securityLevel: 'CUI',
      capabilities: ['mechanical assembly', 'thermal spray', 'final integration'],
      accreditations: ['CMMC-L2'],
      surgeCapacity: { baselineUnitsPerYear: 12, surgeUnitsPerYear: 120, timeToSurgeDays: 365 },
      constrainedBySkillIds: ['SKL:MACH-5X-2'],
    },
  },
  {
    id: 'FAC:TRN-05', type: 'Facility', name: 'Training Center 05', level: 'UNCLASSIFIED', ageDays: 150,
    attrs: {
      name: 'Training Center 05', facilityType: 'TRAINING', securityLevel: 'UNCLASSIFIED',
      capabilities: ['digital twin simulation', 'process qualification'],
      accreditations: [],
      surgeCapacity: { baselineUnitsPerYear: 200, surgeUnitsPerYear: 400, timeToSurgeDays: 90 },
      constrainedBySkillIds: ['SKL:CMC-LAM-3'],
    },
  },
  {
    id: 'RS:2026-03-14A', type: 'RangeSlot', name: 'WT-03 Slot 14A', level: 'CUI', ageDays: 66,
    attrs: {
      facilityId: 'FAC:WT-03', start: isoAt(daysAgo(66)), end: isoAt(daysAgo(64)), campaignId: 'TC:WT-26-04',
      status: 'USED', telemetryCoverage: { channels: 12, redundancy: 'dual', coveragePct: 97.4 },
      instrumentation: [{ sensorId: 'PHOT-PD' }, { sensorId: 'IR-CAM' }],
    },
  },
  {
    id: 'RS:2026-04-02B', type: 'RangeSlot', name: 'WT-03 Slot 02B', level: 'CUI', ageDays: 25,
    attrs: {
      facilityId: 'FAC:WT-03', start: isoAt(daysAgo(25)), end: isoAt(daysAgo(-2)), campaignId: 'TC:FLT-26-02',
      status: 'CONFIRMED', telemetryCoverage: { channels: 9, redundancy: 'single', coveragePct: 88.1 },
      instrumentation: [{ sensorId: 'TELEM-B' }],
    },
  },
];

function buildEntities(): NgsHEntity[] {
  return ENTITY_SEEDS.map((seed, index) => {
    const createdMs =
      seed.ageHours !== undefined
        ? MOCK_EPOCH_MS - seed.ageHours * 3_600_000
        : daysAgo(seed.ageDays, (index % 9) + 1);
    const updatedMs = createdMs + Math.floor(between(1, 24)) * 3_600_000;
    return {
      id: seed.id,
      type: seed.type,
      tenant: MOCK_TENANT,
      program: MOCK_PROGRAM,
      version: 1 + (index % 4),
      classification: { level: seed.level, caveats: seed.level === 'SECRET' ? ['CNSSI 5016.1'] : [] },
      createdAt: isoAt(createdMs),
      updatedAt: isoAt(Math.min(updatedMs, MOCK_EPOCH_MS)),
      createdBy: index % 3 === 0 ? ACTORS.lindqvist!.subjectId : ACTORS.vasquez!.subjectId,
      updatedBy: ACTORS.svcFabric!.subjectId,
      labels: { ...(seed.labels ?? {}), source: 'mock-dataset' },
      annotations: { seeded: 'true' },
      deleted: false,
      attributes: { name: seed.name, ...seed.attrs },
    };
  });
}

export const MOCK_ENTITIES: NgsHEntity[] = buildEntities();

const ENTITY_BY_ID = new Map(MOCK_ENTITIES.map((e) => [e.id, e]));

/* ------------------------------------------------------------------ */
/* Relations                                                            */
/* ------------------------------------------------------------------ */

interface RelationSeed {
  from: string;
  type: string;
  to: string;
  confidence: number;
  ageDays: number;
  attributes?: Record<string, unknown>;
}

const RELATION_SEEDS: RelationSeed[] = [
  { from: 'PART:NSN-4472', type: 'satisfies', to: 'REQ:NGH-0093', confidence: 0.95, ageDays: 92 },
  { from: 'PART:LEAD-1180', type: 'satisfies', to: 'REQ:NGH-0012', confidence: 0.93, ageDays: 168 },
  { from: 'SUB:TPS-01', type: 'satisfies', to: 'REQ:NGH-0012', confidence: 0.9, ageDays: 166 },
  { from: 'PART:SEAKER-A3', type: 'satisfies', to: 'REQ:NGH-0024', confidence: 0.91, ageDays: 132 },
  { from: 'SUB:SEAKER-01', type: 'satisfies', to: 'REQ:NGH-0024', confidence: 0.88, ageDays: 130 },
  { from: 'SUB:GNC-01', type: 'satisfies', to: 'REQ:NGH-0031', confidence: 0.94, ageDays: 180 },
  { from: 'PP:AUTOCLAVE-01', type: 'satisfies', to: 'REQ:NGH-0042', confidence: 0.87, ageDays: 176 },
  { from: 'FAC:MR-01', type: 'satisfies', to: 'REQ:NGH-0042', confidence: 0.72, ageDays: 176 },
  { from: 'MDL:AERO-6.2', type: 'satisfies', to: 'REQ:NGH-0055', confidence: 0.86, ageDays: 128 },
  { from: 'SYS:SENSOR-HBTSS', type: 'satisfies', to: 'REQ:NGH-0074', confidence: 0.81, ageDays: 110 },
  { from: 'ESC:DETECT-CUSTODY-02', type: 'satisfies', to: 'REQ:NGH-0074', confidence: 0.79, ageDays: 33 },
  { from: 'SKL:CMC-LAM-3', type: 'satisfies', to: 'REQ:NGH-0088', confidence: 0.66, ageDays: 104 },
  { from: 'FAC:MR-01', type: 'satisfies', to: 'REQ:NGH-0088', confidence: 0.7, ageDays: 104 },
  { from: 'SUP:NANOFAB-03', type: 'satisfies', to: 'REQ:NGH-0061', confidence: 0.52, ageDays: 120 },
  { from: 'IF:ICD-GNC-05', type: 'satisfies', to: 'REQ:NGH-0102', confidence: 0.96, ageDays: 78 },
  { from: 'PART:AVIONICS-77', type: 'satisfies', to: 'REQ:NGH-0102', confidence: 0.92, ageDays: 78 },
  { from: 'THR:HGV-X9', type: 'satisfies', to: 'REQ:NGH-0117', confidence: 0.58, ageDays: 64 },
  { from: 'MDL:THREAT-KIN-2.0', type: 'satisfies', to: 'REQ:NGH-0117', confidence: 0.85, ageDays: 60 },

  { from: 'TR:01J8ZW4C7T2', type: 'verifies', to: 'REQ:NGH-0012', confidence: 0.97, ageDays: 58 },
  { from: 'TR:01J8ZW5D8U3', type: 'verifies', to: 'REQ:NGH-0012', confidence: 0.9, ageDays: 56 },
  { from: 'TR:01J8ZW6E9V4', type: 'verifies', to: 'REQ:NGH-0055', confidence: 0.93, ageDays: 54 },
  { from: 'TR:01J8ZW7F0W5', type: 'verifies', to: 'REQ:NGH-0031', confidence: 0.95, ageDays: 19 },
  { from: 'TR:01J8ZW8G1X6', type: 'verifies', to: 'REQ:NGH-0024', confidence: 0.88, ageDays: 17 },
  { from: 'TR:01J8ZW9H2Y7', type: 'verifies', to: 'REQ:NGH-0042', confidence: 0.99, ageDays: 10 },
  { from: 'TR:01J8ZWA3J3Z8', type: 'verifies', to: 'REQ:NGH-0042', confidence: 0.94, ageDays: 26 },
  { from: 'TR:01J8ZWA4K4A9', type: 'verifies', to: 'REQ:NGH-0012', confidence: 0.71, ageDays: 23 },
  { from: 'TC:WT-26-04', type: 'verifies', to: 'REQ:NGH-0012', confidence: 0.9, ageDays: 62 },
  { from: 'TC:FLT-26-02', type: 'verifies', to: 'REQ:NGH-0024', confidence: 0.86, ageDays: 21 },

  { from: 'PART:NSN-4472', type: 'manufacturedBy', to: 'FAC:MR-01', confidence: 0.96, ageDays: 160 },
  { from: 'PART:LEAD-1180', type: 'manufacturedBy', to: 'FAC:MR-01', confidence: 0.94, ageDays: 120 },
  { from: 'PART:FIN-2207', type: 'manufacturedBy', to: 'FAC:PLANT-02', confidence: 0.91, ageDays: 140 },
  { from: 'PART:SEAKER-A3', type: 'manufacturedBy', to: 'SUP:ARCLITE-07', confidence: 0.58, ageDays: 132 },
  { from: 'PART:AVIONICS-77', type: 'manufacturedBy', to: 'SUP:ARCLITE-07', confidence: 0.77, ageDays: 118 },
  { from: 'PART:ACT-3320', type: 'manufacturedBy', to: 'FAC:PLANT-02', confidence: 0.89, ageDays: 92 },
  { from: 'MAT:LOT-CMC-2291', type: 'manufacturedBy', to: 'SUP:ARCLITE-07', confidence: 0.93, ageDays: 168 },
  { from: 'MAT:LOT-CMC-4470', type: 'manufacturedBy', to: 'SUP:NANOFAB-03', confidence: 0.84, ageDays: 120 },
  { from: 'MAT:BILLET-0088', type: 'manufacturedBy', to: 'SUP:KYTEC-22', confidence: 0.81, ageDays: 134 },

  { from: 'MAT:LOT-CMC-2291', type: 'characterizedBy', to: 'MDL:THERM-3.1', confidence: 0.91, ageDays: 160 },
  { from: 'MAT:LOT-CMC-4470', type: 'characterizedBy', to: 'MDL:THERM-3.1', confidence: 0.83, ageDays: 116 },
  { from: 'MAT:BILLET-0088', type: 'characterizedBy', to: 'MDL:AERO-6.2', confidence: 0.64, ageDays: 128 },
  { from: 'PR:01J8ZWQ4T7B', type: 'characterizedBy', to: 'MDL:MLPRED-1.4', confidence: 0.79, ageDays: 150 },
  { from: 'PR:01J8ZWR9K2M', type: 'characterizedBy', to: 'MDL:MLPRED-1.4', confidence: 0.55, ageDays: 120 },
  { from: 'PART:NSN-4472', type: 'characterizedBy', to: 'TR:01J8ZW2N6F9', confidence: 0.9, ageDays: 158 },
  { from: 'PART:NSN-4472', type: 'characterizedBy', to: 'TR:01J8ZW4C7T2', confidence: 0.95, ageDays: 58 },
  { from: 'PART:LEAD-1180', type: 'characterizedBy', to: 'TR:01J8ZWA4K4A9', confidence: 0.74, ageDays: 23 },
  { from: 'PART:NSN-4472', type: 'characterizedBy', to: 'TR:01J8ZWA3J3Z8', confidence: 0.88, ageDays: 26 },

  { from: 'MDL:AERO-6.2', type: 'derivedFrom', to: 'TR:01J8ZW4C7T2', confidence: 0.94, ageDays: 57 },
  { from: 'MDL:AERO-6.2', type: 'derivedFrom', to: 'TR:01J8ZW6E9V4', confidence: 0.92, ageDays: 53 },
  { from: 'MDL:THERM-3.1', type: 'derivedFrom', to: 'TR:01J8ZW4C7T2', confidence: 0.89, ageDays: 55 },
  { from: 'MDL:MLPRED-1.4', type: 'derivedFrom', to: 'TR:01J8ZWA3J3Z8', confidence: 0.86, ageDays: 25 },
  { from: 'MDL:GNC-9.4', type: 'derivedFrom', to: 'TR:01J8ZW7F0W5', confidence: 0.91, ageDays: 18 },
  { from: 'THR:HGV-X9', type: 'derivedFrom', to: 'TOBS:01J8ZWB5L5C1', confidence: 0.81, ageDays: 51 },
  { from: 'THR:HGV-X9', type: 'derivedFrom', to: 'TOBS:01J8ZWC6M6D2', confidence: 0.66, ageDays: 27 },
  { from: 'THR:BOOSTGLIDE-3', type: 'derivedFrom', to: 'TOBS:01J8ZWC6M6D2', confidence: 0.52, ageDays: 40 },
  { from: 'MDL:THREAT-KIN-2.0', type: 'derivedFrom', to: 'TOBS:01J8ZWB5L5C1', confidence: 0.74, ageDays: 59 },

  { from: 'THR:HGV-X9', type: 'threatens', to: 'SYS:HGV-A1', confidence: 0.76, ageDays: 50 },
  { from: 'THR:HGV-X9', type: 'threatens', to: 'FAC:MR-01', confidence: 0.68, ageDays: 48 },
  { from: 'THR:BOOSTGLIDE-3', type: 'threatens', to: 'SYS:SENSOR-HBTSS', confidence: 0.71, ageDays: 39 },

  { from: 'ESC:DETECT-CUSTODY-02', type: 'engages', to: 'THR:HGV-X9', confidence: 0.83, ageDays: 32 },

  { from: 'PP:AUTOCLAVE-01', type: 'requiresSkill', to: 'SKL:CMC-LAM-3', confidence: 0.97, ageDays: 200 },
  { from: 'PP:PYROLYSIS-02', type: 'requiresSkill', to: 'SKL:PYRO-OP-1', confidence: 0.95, ageDays: 188 },
  { from: 'PP:NDT-01', type: 'requiresSkill', to: 'SKL:NDT-ET-2', confidence: 0.96, ageDays: 176 },
  { from: 'PP:MACH-COAT-04', type: 'requiresSkill', to: 'SKL:MACH-5X-2', confidence: 0.93, ageDays: 140 },
  { from: 'TC:WT-26-04', type: 'requiresSkill', to: 'SKL:FLT-DIR-1', confidence: 0.9, ageDays: 62 },
  { from: 'TC:FLT-26-02', type: 'requiresSkill', to: 'SKL:FLT-DIR-1', confidence: 0.92, ageDays: 21 },
  { from: 'FAC:MR-01', type: 'requiresSkill', to: 'SKL:CMC-LAM-3', confidence: 0.88, ageDays: 240 },
  { from: 'FAC:PLANT-02', type: 'requiresSkill', to: 'SKL:MACH-5X-2', confidence: 0.85, ageDays: 180 },
  { from: 'RS:2026-03-14A', type: 'requiresSkill', to: 'SKL:FLT-DIR-1', confidence: 0.87, ageDays: 66 },
  { from: 'RS:2026-04-02B', type: 'requiresSkill', to: 'SKL:FLT-DIR-1', confidence: 0.87, ageDays: 25 },

  { from: 'SUP:ARCLITE-07', type: 'supplies', to: 'MAT:LOT-CMC-2291', confidence: 0.95, ageDays: 168 },
  { from: 'SUP:ARCLITE-07', type: 'supplies', to: 'PART:SEAKER-A3', confidence: 0.57, ageDays: 132 },
  { from: 'SUP:KYTEC-22', type: 'supplies', to: 'MAT:BILLET-0088', confidence: 0.89, ageDays: 134 },
  { from: 'SUP:NANOFAB-03', type: 'supplies', to: 'MAT:LOT-CMC-4470', confidence: 0.91, ageDays: 120 },
  { from: 'SUP:KYTEC-22', type: 'supplies', to: 'FAC:MR-01', confidence: 0.61, ageDays: 150 },

  { from: 'FAC:MR-01', type: 'reconstitutes', to: 'PART:NSN-4472', confidence: 0.46, ageDays: 92 },
  { from: 'SUP:ARCLITE-07', type: 'reconstitutes', to: 'PART:NSN-4472', confidence: 0.62, ageDays: 92 },
  { from: 'FAC:PLANT-02', type: 'reconstitutes', to: 'PART:FIN-2207', confidence: 0.78, ageDays: 60 },

  /* ---- Recent flight campaign activity ---- */
  { from: 'TR:01J8ZY9A1B2C3', type: 'verifies', to: 'REQ:NGH-0031', confidence: 0.95, ageDays: 0 },
  { from: 'TR:01J8ZY8B2C3D4', type: 'verifies', to: 'REQ:NGH-0024', confidence: 0.9, ageDays: 0 },
  { from: 'TR:01J8ZY7C3D4E5', type: 'verifies', to: 'REQ:NGH-0102', confidence: 0.88, ageDays: 0 },
  { from: 'TR:01J8ZY6D4E5F6', type: 'verifies', to: 'REQ:NGH-0012', confidence: 0.92, ageDays: 0 },
  { from: 'TR:01J8ZY4F6G7H8', type: 'characterizedBy', to: 'PART:LEAD-1180', confidence: 0.9, ageDays: 0 },
  { from: 'MDL:GNC-9.4', type: 'derivedFrom', to: 'TR:01J8ZY9A1B2C3', confidence: 0.93, ageDays: 0 },
];

function buildRelations(): Relation[] {
  return RELATION_SEEDS.map((seed, index) => {
    const from = ENTITY_BY_ID.get(seed.from);
    const to = ENTITY_BY_ID.get(seed.to);
    const assertedMs = daysAgo(seed.ageDays, (index % 7) + 1);
    const level: ClassificationLevel =
      from?.classification?.level === 'RESTRICTED' || to?.classification?.level === 'RESTRICTED'
        ? 'RESTRICTED'
        : from?.classification?.level === 'SECRET' || to?.classification?.level === 'SECRET'
          ? 'SECRET'
          : 'CUI';
    return {
      id: `REL:${seed.type.toUpperCase()}-${shortUlid(assertedMs)}`,
      type: seed.type,
      from: { type: from?.type ?? 'Unknown', id: seed.from },
      to: { type: to?.type ?? 'Unknown', id: seed.to },
      tenant: MOCK_TENANT,
      program: MOCK_PROGRAM,
      classification: { level },
      assertedAt: isoAt(assertedMs),
      assertedBy: ACTORS.svcFabric!.subjectId,
      confidence: seed.confidence,
      attributes: { source: 'mock-dataset', ...(seed.attributes ?? {}) },
    };
  });
}

export const MOCK_RELATIONS: Relation[] = buildRelations();

/* ------------------------------------------------------------------ */
/* Events                                                               */
/* ------------------------------------------------------------------ */

function actorFor(index: number): Actor {
  const rotation: Actor[] = [
    ACTORS.vasquez!, ACTORS.svcFabric!, ACTORS.lindqvist!, ACTORS.svcIngest!,
    ACTORS.bhatt!, ACTORS.svcReduce!, ACTORS.svcPolicy!, ACTORS.edgeWt!, ACTORS.osei!,
  ];
  return rotation[index % rotation.length]!;
}

function classificationFor(entity: NgsHEntity | undefined, level?: ClassificationLevel): { level: ClassificationLevel; caveats: string[] } {
  return { level: level ?? entity?.classification?.level ?? 'CUI', caveats: entity?.classification?.caveats ?? [] };
}

function buildEvents(): EventEnvelope[] {
  const raw: Array<{
    type: string;
    aggregateType: string;
    aggregateId: string;
    at: number;
    actor: Actor;
    payload: Record<string, unknown>;
    attachments?: EventEnvelope['attachments'];
    classification?: { level: ClassificationLevel; caveats: string[] };
  }> = [];

  ENTITY_SEEDS.forEach((seed, index) => {
    const entity = MOCK_ENTITIES[index]!;
    const createdMs = Date.parse(entity.createdAt);
    raw.push({
      type: 'entity.created',
      aggregateType: seed.type,
      aggregateId: seed.id,
      at: createdMs,
      actor: actorFor(index),
      payload: { entity: { ...entity } },
      classification: classificationFor(entity),
    });
  });

  // A subset of entities receive a later update event.
  // TestResult is immutable once recorded (constraint C-003): corrections are
  // superseding events, never in-place updates.
  [2, 5, 8, 9, 12, 16, 19, 24, 27, 30, 33, 41, 46, 51].forEach((entityIndex, i) => {
    const entity = MOCK_ENTITIES[entityIndex];
    if (!entity || entity.type === 'TestResult') return;
    const at = Date.parse(entity.updatedAt);
    raw.push({
      type: 'entity.updated',
      aggregateType: entity.type,
      aggregateId: entity.id,
      at,
      actor: actorFor(i + 3),
      payload: {
        entity: { ...entity, version: entity.version + 1 },
        changedFields: ['attributes.disposition', 'attributes.updatedAt'],
        previousVersion: entity.version,
      },
      classification: classificationFor(entity),
    });
  });

  MOCK_RELATIONS.forEach((relation, index) => {
    const at = Date.parse(relation.assertedAt);
    raw.push({
      type: 'entity.relation.asserted',
      aggregateType: relation.from.type,
      aggregateId: relation.from.id,
      at,
      actor: ACTORS.svcFabric!,
      payload: { relation },
      classification: { level: relation.classification?.level ?? 'CUI', caveats: [] },
    });
    if (index % 29 === 11) {
      raw.push({
        type: 'entity.relation.retracted',
        aggregateType: relation.from.type,
        aggregateId: relation.from.id,
        at: at + 3 * 3_600_000,
        actor: ACTORS.lindqvist!,
        payload: {
          relationId: relation.id,
          reason: 'Superseded by the re-baselined configuration CFG-2026-031.',
          supersededBy: `REL:RECONSTITUTES-${shortUlid(at)}`,
        },
        classification: { level: relation.classification?.level ?? 'CUI', caveats: [] },
      });
    }
  });

  MOCK_ENTITIES.filter((e) => e.type === 'TestCampaign').forEach((campaign) => {
    const attrs = campaign.attributes as Record<string, unknown>;
    raw.push({
      type: 'test.campaign.planned',
      aggregateType: 'TestCampaign',
      aggregateId: campaign.id,
      at: Date.parse(campaign.createdAt),
      actor: ACTORS.lindqvist!,
      payload: {
        campaign: { ...campaign },
        capacityModel: {
          feasible: true,
          telemetryCoverage: { channels: 12, coveragePct: 97.4 },
          conflicts: [],
          alternatives: [],
        },
        optimizationObjective: {
          method: 'EXPECTED_INFORMATION_GAIN',
          targetRequirementIds: (attrs['requirementIds'] as string[]) ?? [],
          score: 0.73,
        },
      },
      classification: classificationFor(campaign),
    });
  });

  MOCK_ENTITIES.filter((e) => e.type === 'TestResult').forEach((result, i) => {
    raw.push({
      type: 'test.result.recorded',
      aggregateType: 'TestResult',
      aggregateId: result.id,
      at: Date.parse(result.createdAt),
      actor: i % 3 === 0 ? ACTORS.edgeWt! : ACTORS.svcReduce!,
      payload: {
        testResult: { ...result },
        reductionPipeline: {
          pipelineVersion: 'reduction@3.4.1',
          inputUri: `s3://ngsh-testdata/raw/${result.id}/`,
          inputSha256: sha256Hex(`${result.id}:raw`),
          parameters: { window: 'full', filters: ['despike', 'unit-normalise'] },
        },
      },
      attachments: [
        {
          uri: `s3://ngsh-testdata/wt-26-04/run/${i + 1}/`,
          sha256: sha256Hex(`${result.id}:dataset`),
          sizeBytes: 482_000_000 + i * 12_400_000,
          mediaType: 'application/x-hdf5',
        },
      ],
      classification: classificationFor(result),
    });
  });

  MOCK_ENTITIES.filter((e) => e.type === 'ProcessRun').forEach((run) => {
    raw.push({
      type: 'process.run.completed',
      aggregateType: 'ProcessRun',
      aggregateId: run.id,
      at: Date.parse(run.updatedAt),
      actor: ACTORS.svcFabric!,
      payload: {
        processRun: { ...run },
        sensorChannels: [
          { channel: 'autoclave_temp', uri: `s3://ngsh-process/${run.id}/temp.h5`, sampleRateHz: 1, sha256: sha256Hex(`${run.id}:temp`) },
          { channel: 'autoclave_press', uri: `s3://ngsh-process/${run.id}/press.h5`, sampleRateHz: 1, sha256: sha256Hex(`${run.id}:press`) },
        ],
      },
      classification: classificationFor(run),
    });
  });

  MOCK_ENTITIES.filter((e) => e.type === 'Model').forEach((model, i) => {
    const attrs = model.attributes as Record<string, unknown>;
    raw.push({
      type: 'model.validated',
      aggregateType: 'Model',
      aggregateId: model.id,
      at: Date.parse(model.updatedAt),
      actor: ACTORS.svcMdl!,
      payload: {
        modelId: model.id,
        modelVersion: attrs['modelVersion'],
        fidelity: attrs['fidelity'],
        evidenceTestResultIds: (attrs['fidelity'] as { evidenceRefs?: string[] } | undefined)?.evidenceRefs ?? [],
        regenerationTriggered: i % 3 === 0,
        approvedBy: i % 2 === 0 ? ACTORS.lindqvist!.subjectId : undefined,
      },
      classification: classificationFor(model),
    });
  });

  const ingestBatches = [
    { source: 'ingest:csv@r2', sourceUri: 's3://ngsh-inbox/wt-26-04/manifest.csv', format: 'CSV', records: 1840, rejected: 12 },
    { source: 'ingest:ndjson@telemetry', sourceUri: 's3://ngsh-inbox/flt-26-02/telemetry.ndjson', format: 'NDJSON', records: 412_880, rejected: 214 },
    { source: 'ingest:json@me', sourceUri: 's3://ngsh-inbox/materials/lot-2291.json', format: 'JSON', records: 64, rejected: 0 },
    { source: 'ingest:csv@supplier', sourceUri: 's3://ngsh-inbox/supplier/qual-status.csv', format: 'CSV', records: 318, rejected: 41 },
  ];
  ingestBatches.forEach((batch, i) => {
    const at = daysAgo(20 - i * 5, 3 + i);
    const batchId = `BATCH:${shortUlid(at)}`;
    raw.push({
      type: 'ingest.batch.accepted',
      aggregateType: 'IngestBatch',
      aggregateId: batchId,
      at,
      actor: ACTORS.svcIngest!,
      payload: {
        batchId,
        source: batch.source,
        sourceUri: batch.sourceUri,
        format: batch.format,
        recordsAccepted: batch.records,
        recordsRejected: batch.rejected,
        bytesAccepted: batch.records * 4096,
        sha256: sha256Hex(`${batchId}:payload`),
        objectUri: `s3://ngsh-raw/${batchId}/`,
        entityIds: MOCK_ENTITIES.filter((e) => e.type === 'TestResult').slice(i, i + 2).map((e) => e.id),
      },
      classification: { level: 'CUI', caveats: [] },
    });
  });

  MOCK_ENTITIES.filter((e) => e.type === 'Requirement').forEach((requirement, i) => {
    const at = daysAgo(45 - i * 2, 5);
    raw.push({
      type: 'access.decision.recorded',
      aggregateType: 'Requirement',
      aggregateId: requirement.id,
      at,
      actor: ACTORS.lindqvist!,
      payload: {
        decision: i === 5 ? 'DENY' : 'ALLOW',
        action: 'read',
        resource: { type: 'Requirement', id: requirement.id, classification: { level: requirement.classification?.level ?? 'CUI' } },
        policyId: 'POL-CLASS-FLOOR',
        policyVersion: '3.4',
        obligations: i === 5 ? [] : ['log-access', 'no-export'],
        reason: i === 5
          ? 'Subject clearance NONE is below the requirement classification floor.'
          : 'Clearance and program membership satisfy the classification floor.',
        context: { program: MOCK_PROGRAM },
      },
      classification: classificationFor(requirement),
    });
  });

  // Recent activity burst: the FLT-26-02 campaign is live, so the fabric is
  // ingesting telemetry, re-scoring models and taking decisions right now.
  const minutesAgo = (minutes: number): number => MOCK_EPOCH_MS - minutes * 60_000;

  [
    { minutes: 168, records: 96_412, format: 'NDJSON' },
    { minutes: 132, records: 51_204, format: 'NDJSON' },
    { minutes: 74, records: 28_960, format: 'BINARY' },
  ].forEach((batch, index) => {
    const at = minutesAgo(batch.minutes);
    const batchId = `BATCH:${shortUlid(at)}`;
    raw.push({
      type: 'ingest.batch.accepted',
      aggregateType: 'IngestBatch',
      aggregateId: batchId,
      at,
      actor: ACTORS.svcIngest!,
      payload: {
        batchId,
        source: 'ingest:ndjson@flight-telemetry',
        sourceUri: `s3://ngsh-inbox/flt-26-02/telemetry-${index + 1}.ndjson`,
        format: batch.format,
        recordsAccepted: batch.records,
        recordsRejected: index,
        bytesAccepted: batch.records * 8192,
        sha256: sha256Hex(`${batchId}:payload`),
        objectUri: `s3://ngsh-raw/${batchId}/`,
        entityIds: MOCK_ENTITIES.filter((e) => e.type === 'TestResult').slice(index, index + 2).map((e) => e.id),
      },
      classification: { level: 'CUI', caveats: [] },
    });
  });

  [
    { modelId: 'MDL:GNC-9.4', minutes: 126, evidence: ['TR:01J8ZY9A1B2C3', 'TR:01J8ZY7C3D4E5'] },
    { modelId: 'MDL:THERM-3.1', minutes: 88, evidence: ['TR:01J8ZY6D4E5F6'] },
    { modelId: 'MDL:AERO-6.2', minutes: 41, evidence: ['TR:01J8ZY4F6G7H8'] },
  ].forEach((entry) => {
    const model = MOCK_ENTITIES.find((entity) => entity.id === entry.modelId);
    const attrs = (model?.attributes ?? {}) as Record<string, unknown>;
    const at = minutesAgo(entry.minutes);
    raw.push({
      type: 'model.validated',
      aggregateType: 'Model',
      aggregateId: entry.modelId,
      at,
      actor: ACTORS.svcMdl!,
      payload: {
        modelId: entry.modelId,
        modelVersion: attrs['modelVersion'],
        fidelity: attrs['fidelity'],
        evidenceTestResultIds: entry.evidence,
        regenerationTriggered: entry.modelId === 'MDL:GNC-9.4',
        approvedBy: ACTORS.lindqvist!.subjectId,
      },
      classification: classificationFor(model),
    });
  });

  [
    { subject: PERSON_IDS.lindqvist, action: 'read', resource: 'TR:01J8ZY9A1B2C3', decision: 'ALLOW', minutes: 146 },
    { subject: PERSON_IDS.lindqvist, action: 'read', resource: 'TR:01J8ZY8B2C3D4', decision: 'ALLOW', minutes: 138 },
    { subject: PERSON_IDS.bhatt, action: 'read', resource: 'TR:01J8ZY6D4E5F6', decision: 'ALLOW', minutes: 119 },
    { subject: PERSON_IDS.osei, action: 'read', resource: 'TR:01J8ZY9A1B2C3', decision: 'DENY', minutes: 112 },
    { subject: PERSON_IDS.vasquez, action: 'export', resource: 'TR:01J8ZY7C3D4E5', decision: 'DENY', minutes: 97 },
    { subject: PERSON_IDS.lindqvist, action: 'write', resource: 'MDL:GNC-9.4', decision: 'ALLOW', minutes: 66 },
    { subject: PERSON_IDS.bhatt, action: 'read', resource: 'TR:01J8ZY4F6G7H8', decision: 'ALLOW', minutes: 49 },
    { subject: PERSON_IDS.lindqvist, action: 'read', resource: 'TR:01J8ZY5E5F6G7', decision: 'INDETERMINATE', minutes: 28 },
  ].forEach((entry) => {
    const at = minutesAgo(entry.minutes);
    const subject = Object.values(ACTORS).find((actor) => actor.subjectId === entry.subject);
    const aggregate = MOCK_ENTITIES.find((entity) => entity.id === entry.resource);
    raw.push({
      type: 'access.decision.recorded',
      aggregateType: aggregate?.type ?? 'Entity',
      aggregateId: entry.resource,
      at,
      actor: subject ?? ACTORS.svcPolicy!,
      payload: {
        decision: entry.decision,
        action: entry.action,
        resource: { type: aggregate?.type ?? 'Entity', id: entry.resource },
        policyId: entry.decision === 'ALLOW' ? 'POL-CLASS-FLOOR' : entry.decision === 'DENY' ? 'POL-CLASS-FLOOR' : 'POL-PROGRAM-NTK',
        policyVersion: '3.4',
        obligations: entry.decision === 'ALLOW' ? ['log-access', 'no-export'] : [],
        reason:
          entry.decision === 'ALLOW'
            ? 'Clearance and program membership satisfy the classification floor for the live campaign.'
            : entry.decision === 'DENY'
              ? 'The requested action exceeds the subject clearance or program scope for this resource.'
              : 'Program need-to-know could not be evaluated for the subject at request time.',
        context: { program: MOCK_PROGRAM, live: true },
      },
      classification: { level: 'CUI', caveats: [] },
    });
  });

  [
    { id: 'MDL:GNC-9.4', minutes: 92, fields: ['attributes.fidelity.overall'] },
    { id: 'PART:SEAKER-A3', minutes: 34, fields: ['attributes.revision'] },
  ].forEach((entry) => {
    const entity = MOCK_ENTITIES.find((candidate) => candidate.id === entry.id);
    const at = minutesAgo(entry.minutes);
    raw.push({
      type: 'entity.updated',
      aggregateType: entity?.type ?? 'Entity',
      aggregateId: entry.id,
      at,
      actor: ACTORS.svcFabric!,
      payload: {
        entity: entity ? { ...entity, version: entity.version + 1 } : null,
        changedFields: entry.fields,
        previousVersion: entity?.version ?? 1,
      },
      classification: classificationFor(entity),
    });
  });

  // Sort chronologically, then stamp monotonic ULIDs so ids sort like time.
  raw.sort((a, b) => a.at - b.at);
  return raw.map((item, index) => ({
    eventId: ulid(item.at),
    eventType: item.type,
    eventVersion: 1,
    aggregateType: item.aggregateType,
    aggregateId: item.aggregateId,
    sequence: index + 1,
    causationId: index > 0 ? ulid(raw[index - 1]!.at) : undefined,
    correlationId: `COR:${shortUlid(item.at)}`,
    transactionId: `TX:${shortUlid(item.at)}`,
    occurredAt: isoAt(item.at),
    recordedAt: isoAt(item.at + 1200 + (index % 17) * 130),
    tenant: MOCK_TENANT,
    program: MOCK_PROGRAM,
    actor: item.actor,
    classification: item.classification,
    payload: item.payload,
    attachments: item.attachments,
    schemaRef: `contracts/events/${item.type}/1`,
  }));
}

export const MOCK_EVENTS: EventEnvelope[] = buildEvents();

/* ------------------------------------------------------------------ */
/* Audit ledger                                                         */
/* ------------------------------------------------------------------ */

interface LedgerSeed {
  eventType: string;
  subject: string;
  action: string;
  resource: string;
  decision: 'ALLOW' | 'DENY' | 'INDETERMINATE';
  reason: string;
  ageDays: number;
}

const LEDGER_SEEDS: LedgerSeed[] = [
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'TR:01J8ZW4C7T2', decision: 'ALLOW', reason: 'Clearance TOP SECRET satisfies resource classification; program membership confirmed.', ageDays: 58 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'TR:01J8ZW4C7T2', decision: 'DENY', reason: 'Subject clearance NONE is below the resource classification floor.', ageDays: 58 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'export', resource: 'MAT:LOT-CMC-2291', decision: 'DENY', reason: 'Export is restricted to US citizens with current SECRET clearance.', ageDays: 57 },
  { eventType: 'entity.created', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'PART:NSN-4472', decision: 'ALLOW', reason: 'Service identity holds write scope for the NGSH-SHY program.', ageDays: 56 },
  { eventType: 'test.result.recorded', subject: ACTORS.svcReduce!.subjectId, action: 'write', resource: 'TR:01J8ZW5D8U3', decision: 'ALLOW', reason: 'Reduction pipeline is an approved writer for test results.', ageDays: 56 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.vasquez, action: 'read', resource: 'REQ:NGH-0012', decision: 'ALLOW', reason: 'Requirement is within the subject program scope.', ageDays: 55 },
  { eventType: 'ingest.batch.accepted', subject: ACTORS.svcIngest!.subjectId, action: 'write', resource: 'BATCH:01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Ingest adapter is an approved batch writer.', ageDays: 54 },
  { eventType: 'model.validated', subject: ACTORS.svcMdl!.subjectId, action: 'write', resource: 'MDL:AERO-6.2', decision: 'ALLOW', reason: 'Model validator holds write scope for validated models.', ageDays: 53 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'THR:HGV-X9', decision: 'ALLOW', reason: 'RESTRICTED threat reconstruction requires TOP SECRET; subject qualified.', ageDays: 51 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'read', resource: 'THR:HGV-X9', decision: 'DENY', reason: 'ALLIED citizenship is not sufficient for RESTRICTED threat reconstructions.', ageDays: 51 },
  { eventType: 'entity.relation.asserted', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'REL:SATISFIES-01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Relation type satisfies is permitted between the declared endpoint types.', ageDays: 50 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'PART:NSN-4472', decision: 'INDETERMINATE', reason: 'Resource classification could not be resolved from the caller role mapping.', ageDays: 49 },
  { eventType: 'entity.created', subject: ACTORS.vasquez!.subjectId, action: 'write', resource: 'PP:AUTOCLAVE-01', decision: 'ALLOW', reason: 'Process plan write scope granted by program role.', ageDays: 48 },
  { eventType: 'process.run.completed', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'PR:01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Process run recorded by the fabric writer.', ageDays: 47 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.vasquez, action: 'export', resource: 'TR:01J8ZW6E9V4', decision: 'DENY', reason: 'no-export obligation attaches to the caller program context.', ageDays: 46 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'REQ:NGH-0117', decision: 'ALLOW', reason: 'Requirement classified RESTRICTED; subject clearance TOP SECRET.', ageDays: 45 },
  { eventType: 'entity.updated', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'PART:LEAD-1180', decision: 'ALLOW', reason: 'Revision B supersession applied to the leading edge article.', ageDays: 44 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'read', resource: 'PART:LEAD-1180', decision: 'ALLOW', reason: 'CUI article within program scope.', ageDays: 43 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'write', resource: 'PART:FIN-2207', decision: 'DENY', reason: 'Subject role is read-only for manufacturing articles.', ageDays: 42 },
  { eventType: 'ingest.batch.accepted', subject: ACTORS.svcIngest!.subjectId, action: 'write', resource: 'BATCH:01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Telemetry batch accepted with 214 rejected records.', ageDays: 41 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'ESC:DETECT-CUSTODY-02', decision: 'ALLOW', reason: 'Scenario classified RESTRICTED; subject qualified.', ageDays: 40 },
  { eventType: 'entity.relation.asserted', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'REL:THREATENS-01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Threatens edge asserted within ontology constraints.', ageDays: 39 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.vasquez, action: 'read', resource: 'PER:01J8ZV8Q4B', decision: 'DENY', reason: 'PII-bearing person record requires person-attribute scope.', ageDays: 38 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'PER:01J8ZV8Q4B', decision: 'ALLOW', reason: 'Workforce programme lead holds person-attribute scope.', ageDays: 38 },
  { eventType: 'entity.updated', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'MDL:MLPRED-1.4', decision: 'ALLOW', reason: 'Fidelity re-scored against new evidence.', ageDays: 36 },
  { eventType: 'test.result.recorded', subject: ACTORS.edgeWt!.subjectId, action: 'write', resource: 'TR:01J8ZW7F0W5', decision: 'ALLOW', reason: 'Edge agent reconciled after a 42 s clock skew.', ageDays: 35 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'read', resource: 'TR:01J8ZW8G1X6', decision: 'ALLOW', reason: 'Failing result is CUI; subject clearance SECRET.', ageDays: 33 },
  { eventType: 'entity.relation.retracted', subject: ACTORS.lindqvist!.subjectId, action: 'write', resource: 'REL:RECONSTITUTES-01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Edge withdrawn pending re-qualification of the alternate facility.', ageDays: 32 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'SUP:ARCLITE-07', decision: 'ALLOW', reason: 'Supplier risk record is releasable within program scope.', ageDays: 31 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'export', resource: 'SUP:KYTEC-22', decision: 'DENY', reason: 'Foreign dependency export requires program security review.', ageDays: 30 },
  { eventType: 'model.validated', subject: ACTORS.svcMdl!.subjectId, action: 'write', resource: 'MDL:THREAT-KIN-2.0', decision: 'ALLOW', reason: 'Threat kinematic model re-scored with two observations.', ageDays: 28 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'TOBS:01J8ZWB5L5C1', decision: 'ALLOW', reason: 'Observation classified RESTRICTED; subject qualified.', ageDays: 27 },
  { eventType: 'entity.created', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'TA:TA-0012', decision: 'ALLOW', reason: 'Test article created against configuration CFG-2026-031.', ageDays: 26 },
  { eventType: 'test.campaign.planned', subject: ACTORS.lindqvist!.subjectId, action: 'write', resource: 'TC:FLT-26-02', decision: 'ALLOW', reason: 'Campaign twin produced a feasible capacity plan.', ageDays: 24 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.vasquez, action: 'read', resource: 'RS:2026-04-02B', decision: 'ALLOW', reason: 'Range slot visible to the programme.', ageDays: 23 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'read', resource: 'TC:FLT-26-02', decision: 'ALLOW', reason: 'Campaign within program scope.', ageDays: 21 },
  { eventType: 'entity.created', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'TC:HMTC-26-01', decision: 'ALLOW', reason: 'Manufacturing test campaign planned.', ageDays: 12 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'PER:01J8ZWA1S8D', decision: 'ALLOW', reason: 'Self-service personnel record read.', ageDays: 11 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'PER:01J8ZV7M2A', decision: 'DENY', reason: 'PII-bearing record requires an explicit need-to-know grant.', ageDays: 10 },
  { eventType: 'entity.updated', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'REQ:NGH-0061', decision: 'ALLOW', reason: 'Requirement returned to draft after supplier review.', ageDays: 9 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'CRD:01J8ZWH0Q0G6', decision: 'INDETERMINATE', reason: 'Credential expiry could not be evaluated against the request clock.', ageDays: 8 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'CRD:01J8ZWF8N8E4', decision: 'ALLOW', reason: 'Credential active and current.', ageDays: 7 },
  { eventType: 'ingest.batch.accepted', subject: ACTORS.svcIngest!.subjectId, action: 'write', resource: 'BATCH:01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Supplier qualification batch accepted.', ageDays: 6 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.vasquez, action: 'read', resource: 'MDL:MLPRED-1.4', decision: 'DENY', reason: 'Model is not approved for use and may not inform safety-relevant output.', ageDays: 5 },
  { eventType: 'entity.relation.asserted', subject: ACTORS.svcFabric!.subjectId, action: 'write', resource: 'REL:DERIVEDFROM-01J8ZWQ4T7B', decision: 'ALLOW', reason: 'Lineage edge asserted from test evidence to model version.', ageDays: 4 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'REQ:NGH-0093', decision: 'ALLOW', reason: 'Requirement within program scope.', ageDays: 3 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.bhatt, action: 'write', resource: 'TR:01J8ZWA3J3Z8', decision: 'ALLOW', reason: 'NDT inspector attested the result within qualification.', ageDays: 2 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.osei, action: 'read', resource: 'FAC:MR-01', decision: 'ALLOW', reason: 'Facility record releasable.', ageDays: 1 },
  { eventType: 'access.decision.recorded', subject: PERSON_IDS.lindqvist, action: 'read', resource: 'FAC:MR-01', decision: 'ALLOW', reason: 'Facility classified SECRET; subject clearance TOP SECRET.', ageDays: 0 },
];

const GENESIS_HASH = '0'.repeat(64);

function ledgerDigest(prevHash: string, entry: Omit<AuditEntry, 'hash'>): string {
  return sha256Hex(
    [prevHash, entry.seq, entry.timestamp, entry.eventType, entry.subject, entry.action, entry.resource, entry.decision, entry.reason].join('|'),
  );
}

function buildLedger(): AuditEntry[] {
  const entries: AuditEntry[] = [];
  let prevHash = GENESIS_HASH;
  // The ledger is append-only: timestamps must increase strictly with seq.
  let previousAt = Number.NEGATIVE_INFINITY;
  LEDGER_SEEDS.forEach((seed, index) => {
    const at = Math.max(daysAgo(seed.ageDays, 0), previousAt + 3_600_000);
    previousAt = at;
    const base: Omit<AuditEntry, 'hash'> = {
      seq: index + 1,
      prevHash,
      timestamp: isoAt(at),
      eventType: seed.eventType,
      subject: seed.subject,
      action: seed.action,
      resource: seed.resource,
      decision: seed.decision,
      reason: seed.reason,
    };
    const hash = ledgerDigest(prevHash, base);
    entries.push({ ...base, hash });
    prevHash = hash;
  });
  return entries;
}

export const MOCK_LEDGER: AuditEntry[] = buildLedger();
export const MOCK_LEDGER_HEAD = MOCK_LEDGER[MOCK_LEDGER.length - 1]!.hash;

/* ------------------------------------------------------------------ */
/* Policies and access decisions                                        */
/* ------------------------------------------------------------------ */

export const MOCK_POLICIES: PolicySummary[] = [
  { id: 'POL-CLASS-FLOOR', description: 'A subject may read a resource only when their clearance meets the resource classification floor.', effect: 'ALLOW', priority: 10 },
  { id: 'POL-CITIZENSHIP', description: 'Foreign and allied citizens require a program security review before reading RESTRICTED or above.', effect: 'DENY', priority: 20 },
  { id: 'POL-PROGRAM-NTK', description: 'A subject may act only on resources tagged with a program in their need-to-know set.', effect: 'DENY', priority: 30 },
  { id: 'POL-EXPORT-CONTROL', description: 'Export of articles or materials requires US citizenship and export control clearance.', effect: 'DENY', priority: 40 },
  { id: 'POL-MODEL-APPROVAL', description: 'A model may not inform safety-relevant output unless approvedForUse is true.', effect: 'DENY', priority: 50 },
  { id: 'POL-ACCESS-LOG', description: 'Every allowed read is written to the audit ledger with obligations attached.', effect: 'ALLOW', priority: 60 },
];

/* ------------------------------------------------------------------ */
/* Derived views                                                        */
/* ------------------------------------------------------------------ */

export const MOCK_GRAPH_STATS: GraphStats = (() => {
  const entityCounts: Record<string, number> = {};
  for (const entity of MOCK_ENTITIES) {
    entityCounts[entity.type] = (entityCounts[entity.type] ?? 0) + 1;
  }
  const relationCounts: Record<string, number> = {};
  for (const relation of MOCK_RELATIONS) {
    relationCounts[relation.type] = (relationCounts[relation.type] ?? 0) + 1;
  }
  return {
    entityCounts,
    relationCounts,
    totalEntities: MOCK_ENTITIES.length,
    totalRelations: MOCK_RELATIONS.length,
  };
})();

export function mockEntityWithRelations(type: string, id: string): EntityWithRelations | null {
  const entity = MOCK_ENTITIES.find((e) => e.id === id && e.type === type);
  if (!entity) return null;
  const relations = MOCK_RELATIONS.filter((r) => r.from.id === id || r.to.id === id);
  return { entity, relations };
}

/** Decision evaluation used by the mock policy service. */
export function evaluateMockPolicy(
  subject: { subjectId: string; clearance: string; citizenship: string; programs: string[] },
  resource: { type: string; id: string; classification: string },
  action: string,
): PolicyDecisionResponse {
  const rank: Record<string, number> = { UNCLASSIFIED: 0, 'CUI//REL': 1, 'CUI//FOUO': 1, CUI: 1, RESTRICTED: 2, SECRET: 3, 'TOP SECRET': 4 };
  const clearanceRank: Record<string, number> = { NONE: 0, SECRET: 2, 'TOP SECRET': 3, 'SCI-CLEARED': 4 };
  const resourceRank = rank[resource.classification] ?? 0;
  const subjectRank = clearanceRank[subject.clearance] ?? 0;

  if (subject.citizenship === 'FOREIGN' && resourceRank >= 2) {
    return {
      decision: 'DENY',
      policyId: 'POL-CITIZENSHIP',
      obligations: [],
      reason: 'Foreign citizenship is not permitted to access RESTRICTED or higher resources without a program security review.',
    };
  }
  if (subjectRank < resourceRank) {
    return {
      decision: 'DENY',
      policyId: 'POL-CLASS-FLOOR',
      obligations: [],
      reason: `Subject clearance ${subject.clearance} is below the ${resource.classification} classification floor of ${resource.type} ${resource.id}.`,
    };
  }
  if (subject.citizenship === 'ALLIED' && resourceRank >= 3) {
    return {
      decision: 'DENY',
      policyId: 'POL-CITIZENSHIP',
      obligations: [],
      reason: 'Allied citizenship requires a program security review for SECRET and above.',
    };
  }
  if (action === 'export' && subject.citizenship !== 'US') {
    return {
      decision: 'DENY',
      policyId: 'POL-EXPORT-CONTROL',
      obligations: [],
      reason: 'Export of classified material is restricted to US citizens.',
    };
  }
  if (subject.programs.length === 0) {
    return {
      decision: 'INDETERMINATE',
      policyId: 'POL-PROGRAM-NTK',
      obligations: [],
      reason: 'Subject carries no program access tags, so need-to-know cannot be evaluated.',
    };
  }
  return {
    decision: 'ALLOW',
    policyId: 'POL-CLASS-FLOOR',
    obligations: action === 'export' ? ['log-access', 'export-review'] : ['log-access', 'no-export'],
    reason: `Clearance ${subject.clearance} satisfies the ${resource.classification} floor and the subject holds a program tag.`,
  };
}
