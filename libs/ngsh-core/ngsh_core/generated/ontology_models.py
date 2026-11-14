"""Entity and relation models generated from the NGSH contract layer.
DO NOT EDIT. This module is produced by ``tools/codegen/generate.py``
from the JSON Schema files in ``contracts/``. Edit the contract and
regenerate; ``make codegen-check`` fails the build when the committed
output no longer matches the contract.

Contract version: ontology 1.0.0.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EntityId = Annotated[str, Field(pattern="^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
#: An NGSH identifier: ``<TYPE_PREFIX>:<key>``.

Timestamp = str
#: An RFC 3339 / ISO 8601 UTC instant.

class Actor(BaseModel):
    """Who or what performed the action. 'kind' distinguishes human, workload identity, device or edge a..."""

    citizenship: Literal["US", "ALLIED", "FOREIGN", "UNKNOWN", None] | None = None
    clearance: Literal["NONE", "SECRET", "TOP SECRET", "SCI-CLEARED", None] | None = None
    displayName: str | None = None
    kind: Literal["user", "service", "device", "edge-agent", "anonymous"] = ...
    needToKnow: list[str] | None = None
    org: str | None = None
    programs: list[str] | None = None  # Program access tags (need-to-know scoping).
    subjectId: EntityId = ...
    tenant: str | None = None  # Tenancy key the subject operates in. Used by the cross-tenant denial rule.

class Attachment(BaseModel):
    """Reference to a large artifact held in the object store. The store holds bytes; the graph holds th..."""

    classification: Classification | None = None
    encrypted: bool | None = None
    mediaType: str | None = None
    retentionUntil: Timestamp | None = None
    sha256: str = ...
    sizeBytes: int | None = None
    uri: str = ...

class Classification(BaseModel):
    """Handling caveat carried by every record. Enforcement is not limited to this header: the storage l..."""

    caveats: list[str] | None = None  # Control markings, e.g. 'NOFORN', 'PROPIN', 'CNSSI 5016.1'.
    derivedFromClassified: bool | None = None
    level: Literal["UNCLASSIFIED", "CUI", "CUI//REL", "CUI//FOUO", "RESTRICTED", "SECRET", "TOP SECRET"] = ...  # Highest classification level of the record's content.
    origins: list[str] | None = None  # Original classification authorities. Required for 508/5320-style document marking.

class CostEstimate(BaseModel):
    """Unit cost trace attached to design and production decisions. Cost-as-a-requirement (PSDD 4.2 #5)."""

    amount: float | None = None
    basis: Literal["QUOTE", "ACTUAL", "ANALOG", "PARAMETRIC", "LEARNED_CURVE"] | None = None
    confidence: float | None = None
    currency: str | None = None
    productionRate: float | None = None  # Units per year at which the estimate is valid.

class FidelityScore(BaseModel):
    """Quantitative credibility of a simulation model. Every Model entity carries one; test-coupled M&S ..."""

    applicabilityEnvelope: dict[str, dict[str, Any]] | None = None  # Regime beyond which the model must not be used. Bounds for dimension parameters.
    components: dict[str, float] | None = None  # Per-dimension fidelity (aerodynamics, thermal, structural, timeline...).
    evaluatedAt: Timestamp | None = None
    evidenceRefs: list[EntityId] | None = None  # Test results that justify the score.
    method: str | None = None  # Scoring method identifier, e.g. 'rmse-vs-baseline-normalised'.
    overall: float = ...

class Measurement(BaseModel):
    """A single measured or computed quantity with uncertainty. Used across test results, process runs a..."""

    channel: str | None = None  # Instrumentation channel identifier.
    max: float | None = None
    method: str | None = None
    min: float | None = None
    name: str = ...
    uncertainty: float | None = None  # Expanded uncertainty (k=2) when available.
    unit: str | None = None
    value: float = ...

class Provenance(BaseModel):
    """Where the data came from and how much to trust it. Required for every derived/estimated value; su..."""

    confidence: float | None = None
    method: str | None = None  # Method or algorithm identifier, e.g. 'kalman-fusion-v2'.
    modelVersion: str | None = None  # Model version that produced the value; required when method is an estimator.
    observedAt: Timestamp | None = None
    parentRefs: list[EntityId] | None = None  # Upstream records that produced this one; powers lineage graph traversal.
    reviewedBy: str | None = None  # Human approver for safety-relevant or low-confidence assertions.
    source: str | None = None  # Origin system or process, e.g. 'wind-tunnel.itc', 'analyst.judgment', 'ingest:csv@r2'.

class Reference(BaseModel):
    """Typed pointer to another entity."""

    id: EntityId = ...
    type: str = ...

class Credential(BaseModel):
    evidenceRefs: list[EntityId] | None = None
    expiresAt: str | None = None
    issuedAt: str = ...
    issuingAuthority: str | None = None
    personId: EntityId = ...
    skillId: EntityId = ...
    status: Literal["ACTIVE", "EXPIRED", "SUSPENDED", "REVOKED"] = ...
    workAuthorizationIds: list[str] | None = None

class EngagementScenario(BaseModel):
    defensiveArchitecture: str | None = None  # Architecture under evaluation, e.g. 'HBTSS-cued-Aegis-GPI'.
    effectorChain: list[dict[str, Any]] | None = None
    monteCarloConfig: dict[str, Any] | None = None
    name: str = ...
    resultsSummary: dict[str, Any] | None = None  # Detection-to-custody time, Pk, single-shot Pk.
    sensorChain: list[dict[str, Any]] | None = None
    threatSystemIds: list[EntityId] | None = None
    timeline: dict[str, Any] | None = None

class Facility(BaseModel):
    accreditations: list[str] | None = None
    capabilities: list[str] | None = None
    constrainedBySkillIds: list[EntityId] | None = None
    facilityType: Literal["MANUFACTURING", "TEST", "RANGE", "LABORATORY", "WAREHOUSE", "TRAINING", "OTHER"] = ...
    name: str = ...
    resourceIds: list[str] | None = None
    securityLevel: Literal["UNCLASSIFIED", "CUI", "SECRET", "TOP SECRET"] | None = None
    surgeCapacity: dict[str, Any] | None = None

class Interface(BaseModel):
    characteristics: dict[str, Any] | None = None  # Rate, latency, timing, envelope.
    dataItems: list[dict[str, Any]] | None = None
    fromSystemId: EntityId = ...
    icdVersion: str | None = None
    name: str = ...
    toSystemId: EntityId = ...

class Material(BaseModel):
    batchId: str | None = None
    certifications: list[str] | None = None
    characterizationIds: list[EntityId] | None = None
    lotNumber: str = ...
    materialType: Literal["CMC_PREG", "CMC_BILLET", "CMC_NOSECAP", "METAL", "COATING", "ADHESIVE", "OTHER"] = ...
    microstructureSummary: str | None = None
    processPlanIds: list[EntityId] | None = None
    receivedAt: str | None = None
    supplierId: EntityId | None = None

class Model(BaseModel):
    approvedForUse: bool | None = None  # Human approval gate for safety-relevant predictions.
    codeRef: str | None = None  # Versioned source reference for the model implementation.
    fidelity: FidelityScore | None = None
    inputSchemaRef: str | None = None
    modelCard: str | None = None  # Pointer to the model card artifact; mandatory for ML models (PSDD 9).
    modelType: Literal["AERODYNAMIC", "THERMAL", "STRUCTURAL", "TRAJECTORY", "GNC", "THREAT_KINEMATIC", "DETECTION", "TRACKING", "ENGAGEMENT", "PRODUCTION_SURGE", "SURROGATE_ML", "OTHER"] = ...
    modelVersion: str = ...
    name: str = ...
    outputSchemaRef: str | None = None
    parentModelId: EntityId | None = None
    runtime: dict[str, Any] | None = None

class Part(BaseModel):
    criticality: Literal["CRITICAL", "KEY", "STANDARD", "LOW"] | None = None
    exportControlled: bool | None = None  # ITAR/EAR jurisdiction flag; drives export-review workflow.
    isSingleSource: bool | None = None
    leadTimeDays: int | None = None
    materialIds: list[EntityId] | None = None
    name: str = ...
    partNumber: str = ...
    partType: Literal["CMC_NOSECAP", "PREPREG", "BILLET", "STRUCTURAL", "AVIONICS", "PROPULSION", "TPS", "FASTENER", "CONSUMABLE", "OTHER"] | None = None
    processPlanIds: list[EntityId] | None = None
    revision: str | None = None
    unitCost: CostEstimate | None = None

class PartProvenance(BaseModel):
    chainOfCustody: list[dict[str, Any]] = ...
    materialIds: list[EntityId] | None = None
    partId: EntityId = ...
    processRunIds: list[EntityId] | None = None

class Person(BaseModel):
    citizenship: Literal["US", "ALLIED", "FOREIGN", "UNKNOWN"] = ...
    clearanceExpiry: str | None = None
    clearanceLevel: Literal["NONE", "SECRET", "TOP SECRET", "SCI-CLEARED"] = ...
    employeeId: str = ...
    name: str = ...
    organization: str | None = None
    region: str | None = None  # Workforce geography for regional gap analysis (PSDD E-4).
    role: str | None = None
    skillIds: list[EntityId] | None = None

class ProcessPlan(BaseModel):
    name: str = ...
    operations: list[dict[str, Any]] = ...
    processType: Literal["FILM_LAMINATION", "AUTOCLAVE", "PYROLYSIS", "HIP", "MACHINING", "COATING", "BRAZE", "NDT", "ASSEMBLY", "OTHER"] = ...
    qualificationStatus: Literal["QUALIFIED", "QUALIFICATION_IN_PROGRESS", "NOT_QUALIFIED", "EXPIRED"] | None = None
    qualifiedFacilityIds: list[EntityId] | None = None
    revision: str = ...

class ProcessRun(BaseModel):
    disposition: Literal["ACCEPTED", "REWORK", "SCRAP", "PENDING"] | None = None
    driftFlags: list[str] | None = None  # Process drift detected against the characterized envelope.
    endedAt: str | None = None
    facilityId: EntityId | None = None
    materialId: EntityId | None = None
    measuredParameters: dict[str, Any] | None = None
    measuredSeries: list[Measurement] | None = None
    nonconformanceId: str | None = None
    operatorId: EntityId | None = None
    partId: EntityId | None = None
    processPlanId: EntityId = ...
    startedAt: str = ...

class RangeSlot(BaseModel):
    campaignId: EntityId | None = None
    end: str = ...
    facilityId: EntityId = ...
    instrumentation: list[dict[str, Any]] | None = None
    start: str = ...
    status: Literal["HELD", "REQUESTED", "CONFIRMED", "CANCELLED", "USED"] | None = None
    telemetryCoverage: dict[str, Any] | None = None

class Requirement(BaseModel):
    acceptanceCriteria: str | None = None
    allocatedToIds: list[EntityId] | None = None
    costDrivers: list[str] | None = None  # Cost impacts traced from this requirement (PSDD H-3).
    parentId: EntityId | None = None
    reqType: Literal["FUNCTIONAL", "PERFORMANCE", "INTERFACE", "DERIVED", "QUALITY", "SAFETY", "SECURITY", "CONSTRAINT"] | None = None
    statement: str = ...
    status: Literal["DRAFT", "BASELINED", "ALLOCATED", "IMPLEMENTED", "VERIFIED", "INVALID"] = ...
    text: str | None = None  # Verbatim requirement text; distinct from the normalized statement.
    verificationMethod: Literal["TEST", "ANALYSIS", "INSPECTION", "DEMONSTRATION", "CERTIFICATION", "TOLERANCE"] = ...
    verificationStatus: Literal["NOT_STARTED", "IN_PROGRESS", "PARTIAL", "COMPLETE", "NOT_APPLICABLE"] | None = None

class Skill(BaseModel):
    category: Literal["MANUFACTURING", "QUALITY", "TEST", "ENGINEERING", "ANALYSIS", "OPERATIONS", "SUPERVISION"] = ...
    clearanceRequired: str | None = None
    code: str = ...  # SDO/O*NET-style code where available.
    level: int | None = None
    name: str = ...
    qualificationCriteria: list[str] | None = None

class Subsystem(BaseModel):
    interfaceIds: list[EntityId] | None = None
    maturity: Literal["TRL_1", "TRL_2", "TRL_3", "TRL_4", "TRL_5", "TRL_6", "TRL_7", "TRL_8", "TRL_9", "UNSPECIFIED"] | None = None
    name: str = ...
    parentSystemId: EntityId = ...
    subsystemType: str | None = None

class Supplier(BaseModel):
    capabilities: list[str] | None = None
    certifications: list[str] | None = None
    dependencies: list[EntityId] | None = None
    domesticContent: float | None = None
    exportControlled: bool | None = None
    facilityIds: list[EntityId] | None = None
    leadTimeDays: int | None = None
    name: str = ...
    riskScore: float | None = None
    tier: int = ...

class System(BaseModel):
    costEstimate: CostEstimate | None = None
    interfaceIds: list[EntityId] | None = None
    lifecycleState: Literal["CONCEPT", "DEVELOPMENT", "QUALIFICATION", "PRODUCTION", "FIELDED", "RETIRED"] = ...
    mission: str | None = None
    name: str = ...
    parentSystemId: EntityId | None = None
    platform: str | None = None  # Modularity platform / family-of-systems family tag (PSDD A-2).
    systemType: Literal["HYPERSONIC_WEAPON", "BOOSTER", "PAYLOAD", "GNC", "AIRFRAME", "TPS", "SENSOR", "EFFECTOR", "C2", "GROUND_SYSTEM", "ENTERPRISE_SERVICE"] | None = None

class TestArticle(BaseModel):
    asBuiltStatus: Literal["AS_BUILT", "AS_DESIGNED", "DEVIATED"] = ...  # Configuration fidelity to the design intent.
    buildConfigurationId: str | None = None  # Configuration baseline that pins every part revision and software build.
    deviations: list[dict[str, Any]] | None = None
    partIds: list[EntityId] | None = None
    serialNumber: str = ...
    variantId: EntityId | None = None

class TestCampaign(BaseModel):
    campaignType: Literal["GROUND", "WIND_TUNNEL", "SLED", "FLIGHT", "ENGINE", "MATERIAL_COUPOON", "STRUCTURAL", "QUALIFICATION"] = ...
    dataSetUris: list[str] | None = None
    instrumentationManifest: list[dict[str, Any]] | None = None
    name: str = ...
    objectives: list[str] | None = None
    rangeSlotIds: list[EntityId] | None = None
    requirementIds: list[EntityId] | None = None
    status: Literal["PLANNED", "ACTIVE", "COMPLETE", "ABORTED"] = ...
    testArticleIds: list[EntityId] | None = None

class TestResult(BaseModel):
    anomalyFlags: list[str] | None = None
    baselineId: str | None = None
    campaignId: EntityId | None = None
    configurationSnapshot: dict[str, Any] | None = None  # Full configuration context: variant, lot, software build, instrument calibration.
    dataSetUris: list[str] | None = None
    limits: dict[str, Any] | None = None
    measurements: list[Measurement] | None = None
    modelVersionIds: list[EntityId] | None = None
    outcome: Literal["PASS", "FAIL", "MARGINAL", "INCONCLUSIVE", "NOT_RUN"] = ...
    reviewedBy: str | None = None  # Human reviewer; required for safety-relevant results.
    testArticleId: EntityId | None = None
    testMethod: str = ...

class ThreatObservation(BaseModel):
    measurements: list[Measurement] | None = None
    observationTime: str = ...
    rawUri: str | None = None
    sensorIds: list[str] | None = None
    sensorType: Literal["SPACE_IR", "SPACE_EO", "GROUND_RADAR", "AIRBORNE_IR", "AEW", "GROUND_EO", "OTHER"] | None = None
    source: str | None = None
    trackQuality: float | None = None

class ThreatSystem(BaseModel):
    characteristics: list[dict[str, Any]] | None = None
    confidence: float | None = None
    designation: str = ...
    kinematicProfile: dict[str, Any] | None = None  # Mach, altitude, range, acceleration envelope.
    modelVersionIds: list[EntityId] | None = None
    observationIds: list[EntityId] | None = None
    threatClass: Literal["HGV", "HGV_MANEUVERABLE", "HCM", "BOOST_GLIDE", "BOOSTED_GLIDE", "CRUISE_MISSILE", "UNKNOWN"] = ...

class Variant(BaseModel):
    configurationVersion: str | None = None
    distinguishingCharacteristics: list[str] | None = None
    familyId: str | None = None  # Common-core family identifier; drives variant auto-generation.
    systemId: EntityId = ...
    variantId: str = ...  # Variant designation, e.g. 'HGV-B1'.

class RelationType(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    """The 10 canonical edge types of the NGSH shared ontology (PSDD 6.1). Every relation is a first-cla..."""

    assertedAt: str = ...
    assertedBy: str | None = None
    attributes: dict[str, Any] | None = None
    classification: Classification | None = None
    confidence: float | None = None
    from_: Reference = Field(default=..., alias="from")
    id: EntityId = ...
    program: str | None = None
    provenance: Provenance | None = None
    retractedAt: str | None = None
    retractedBy: str | None = None
    retractionReason: str | None = None
    tenant: str | None = None
    to: Reference = ...
    type: Literal["satisfies", "verifies", "manufacturedBy", "characterizedBy", "derivedFrom", "threatens", "engages", "requiresSkill", "supplies", "reconstitutes"] = ...
    weight: float | None = None  # Edge strength; used by trace scoring and confidence roll-up.

#: Every generated entity type, keyed by its ontology type name.
ENTITY_MODELS: dict[str, type[BaseModel]] = {
    "Credential": Credential,
    "EngagementScenario": EngagementScenario,
    "Facility": Facility,
    "Interface": Interface,
    "Material": Material,
    "Model": Model,
    "Part": Part,
    "PartProvenance": PartProvenance,
    "Person": Person,
    "ProcessPlan": ProcessPlan,
    "ProcessRun": ProcessRun,
    "RangeSlot": RangeSlot,
    "Requirement": Requirement,
    "Skill": Skill,
    "Subsystem": Subsystem,
    "Supplier": Supplier,
    "System": System,
    "TestArticle": TestArticle,
    "TestCampaign": TestCampaign,
    "TestResult": TestResult,
    "ThreatObservation": ThreatObservation,
    "ThreatSystem": ThreatSystem,
    "Variant": Variant,
}

#: Every entity type in the ontology, in registry order.
ENTITY_TYPES: tuple[str, ...] = tuple(ENTITY_MODELS)
