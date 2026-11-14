# ADR-0008: Model Cards and a Fidelity Registry

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §4.2 principle 4 requires test-coupled M&S: "models carry fidelity scores; every test result regenerates models automatically". PSDD §5.7 makes this explicit twice: G-3 "Automated model validation — every test result scores model fidelity and regenerates aero/thermal/plasma models" and G-4 "Fidelity registry — all models carry provenance, validation history, and applicability envelope". PSDD §9 governs seven AI/ML services and states: "all models carry provenance, validation history, applicability limits; safety-relevant outputs require human approval". PSDD §8 requires "Model cards for all ML; human-on-the-loop for safety-relevant predictions; drift monitoring; MLOps pipeline with approval gates" and, under Auditability, that every model version be reconstructable.

The ontology registry makes `Model` a first-class type with an explicit `approvedForUse` flag and a `fidelity` attribute of type `FidelityScore`. `FidelityScore` in `contracts/ontology/common.schema.json` is not a number: it carries `overall`, a `method` identifier, per-dimension `components`, an `applicabilityEnvelope` of per-dimension bounds, an `evaluatedAt` timestamp, and `evidenceRefs` naming the test results that justify the score. The `model.validated` event payload carries `modelId`, `modelVersion`, the new `fidelity`, `evidenceTestResultIds`, `priorFidelity`, a `regenerationTriggered` flag and an `approvedBy` approver. Constraint C-004 in the registry states: "A Model used in a safety-relevant prediction must have approvedForUse=true and a non-null fidelity score."

That is a well-specified skeleton. What it does not yet specify is the part that actually decides whether the governance is real: **what happens when the fidelity changes**. A system can satisfy C-004 trivially by having every model permanently approved and a fidelity score that no one recomputes. The decision this ADR has to make is how fidelity is recomputed, by whom, at what point a score change requires a human, and what stops a model from being used outside the regime its evidence supports.

The counter-position is worth stating plainly, because it is the dominant practice in the field: many engineering platforms record a model, attach a validation report, and move on. That position fails here for three specific reasons:

1. The platform's stated value is compressing decision cycles on hypersonic hardware. A silently degraded model that nobody notices is worse than no model, because it *confidently* produces an answer.
2. The evidence base changes continuously. Every flight test, tunnel run and sled shot is new evidence against a physics model. A fidelity score that is not recomputed is a claim that is getting less true every week.
3. The models in question are safety-relevant in the literal sense: aero and thermal models for a vehicle that will fly, CMC process models for material that will be certified, engagement models for a kill chain.

## Decision

**Every `Model` entity carries a model card, a fidelity score with an applicability envelope, and an explicit approval state. Fidelity is recomputed automatically when new test evidence arrives; the recomputation updates the score but does not silently widen the envelope. Use of a model outside its envelope, or in a safety-relevant context without a current approval, is refused by the platform.**

### The Model record

| Attribute | Source | Requirement |
|---|---|---|
| `name`, `modelType`, `modelVersion` | `ModelAttributes` | Required. `modelType` ∈ AERODYNAMIC, THERMAL, STRUCTURAL, TRAJECTORY, GNC, THREAT_KINEMATIC, DETECTION, TRACKING, ENGAGEMENT, PRODUCTION_SURGE, SURROGATE_ML, OTHER |
| `parentModelId` | `ModelAttributes` | Required for any model derived from another model. Forms the model lineage chain |
| `provenance` | `EntityHeader.provenance` | Required: `source`, `method`, `confidence`, `observedAt`, `parentRefs`, `modelVersion` where the value is estimator-produced |
| `fidelity` | `FidelityScore` | Required. `overall` ∈ [0,1]; `method` names the scoring method; `components` gives per-dimension scores; `applicabilityEnvelope` gives the bounds outside which the model must not be used; `evaluatedAt` gives the evaluation time; `evidenceRefs` names the justifying test results |
| `modelCard` | `ModelAttributes.modelCard` | **Required pointer for every model**, not only ML models. The card is a versioned artifact, content-addressed and classified with the model |
| `codeRef` | `ModelAttributes.codeRef` | Versioned source reference for the implementation. Required |
| `inputSchemaRef`, `outputSchemaRef` | `ModelAttributes` | Required. The model's interface is itself a contract |
| `approvedForUse` | `ModelAttributes.approvedForUse` | Defaults to `false`. Set to `true` only by the approval workflow, never by an automated process |
| `runtime` | `ModelAttributes.runtime` | Execution environment requirements — hardware, solver, dependencies. Relevant to reproducibility |

### The model card

The model card is a versioned, content-addressed document. It is stored with the model, inherits the model's classification, and is referenced by `modelCard`. Required sections:

| Section | Content |
|---|---|
| 1. Identification | Name, type, version, `parentModelId` chain, owner, `codeRef` |
| 2. Intended use | The specific questions the model may be used to answer, and the decisions its outputs may inform |
| 3. Out-of-scope use | The questions it must **not** be used to answer. Explicit, not "everything else" — the specific near-misses |
| 4. Derivation and training data | Source data, its own provenance, and the lineage of the derivation. For physics models, the governing equations, the code of record, the numerical scheme and its verified order of accuracy |
| 5. Validation evidence | The test results, the comparisons performed, the metrics, and the statistics. Links by `evidenceRefs` to `TestResult` entities |
| 6. Fidelity | The current `FidelityScore`, the `method`, the per-dimension `components`, and the history of changes with the evidence that caused each change |
| 7. Applicability envelope | The explicit regime bounds: Mach, altitude, Reynolds number, temperature, pressure, time, production rate, threat behaviour envelope, or whatever the model type's dimensions are. **A model with no envelope is not approvable.** |
| 8. Known limitations | Failure modes, numerical limitations, non-stationarity, known biases, regions of poor validity |
| 9. Drift monitoring | What is monitored, at what cadence, what threshold triggers a review, and who is notified |
| 10. Human oversight | Who approves, who may override, what the approval covers, and the re-approval trigger |
| 11. Retirement | The conditions under which the model is withdrawn, and what happens to outputs already produced |
| 12. Version history | Every version, what changed, why, and the approval status of each |

The card is the primary human-readable artefact. The machine-readable `FidelityScore` is a projection of sections 5–7 of the card. If they disagree, the card is authoritative and the machine-readable form is regenerated.

### Fidelity scoring

| Aspect | Rule |
|---|---|
| What triggers a recomputation | A `test.result.recorded` event whose `modelVersionIds` or whose `characterizedBy`/`derivedFrom` edges connect it to the model; a `process.run.completed` event for a process model; a `model.validated` event from an external validation campaign |
| What the recomputation produces | A new `FidelityScore` and a `model.validated` event carrying `modelId`, `modelVersion`, `fidelity`, `evidenceTestResultIds`, `priorFidelity` and `regenerationTriggered` |
| What it does not do | It does **not** set `approvedForUse`, and it does **not** widen the applicability envelope |
| Envelope narrowing | Automatic. If new evidence shows the model is invalid in part of its previous envelope, the envelope **shrinks** automatically and immediately. This is a safety-improving change and does not require approval |
| Envelope widening | Requires human approval. Widening means the model will now be used in regimes it has not been validated for; a human with the relevant domain authority must accept that risk |
| Fidelity score movement | A score change beyond a configured materiality threshold (per model type, default ±0.05 on `overall`) triggers a notification to the model owner and to any pillar whose published result depends on the model |
| `regenerationTriggered` | Set `true` when the validation caused the model implementation to be re-fit rather than merely re-scored. A re-fit is a new `modelVersion`, and the new version starts with `approvedForUse: false` |
| Method | Every score names its `method` (e.g. `rmse-vs-baseline-normalised`). Two models may only be compared on `overall` if they share a method. Comparing across methods is a reporting error the platform surfaces |

### Applicability envelope enforcement

The envelope is enforced at **use** time, not at authoring time. This is the difference between a governance document and a control.

| # | Rule |
|---|---|
| EN-1 | A caller of a model must supply the operating point (the parameter values that determine regime membership) as part of the request. The model service evaluates the point against `applicabilityEnvelope` |
| EN-2 | **Out of envelope is refused, not clamped.** The model service returns `CapabilityUnavailable`-style refusal with a message naming the exceeded dimension. It does not extrapolate and it does not silently clamp |
| EN-3 | A model with no envelope is refused for any use in a safety-relevant context, and is refused for any use at all once its `approvedForUse` is `false` |
| EN-4 | A model whose `approvedForUse` is `false` may be used only in an explicitly exploratory mode, which produces outputs marked `EXPLORATORY` in the provenance and which are excluded from requirement verification evidence and from any safety-relevant decision |
| EN-5 | A model whose current `fidelity.overall` is below the configured floor for its use class is refused. The floor is set per model type and per use class, by the pillar that owns the use |
| EN-6 | C-004 is enforced as a hard precondition at the point of use: `approvedForUse == true` and `fidelity != null` are checked before the model is invoked, and a violation is an error, not a warning |

### Human approval gate

| # | Rule |
|---|---|
| DR-1 | `approvedForUse` is set only by an explicit approval action by a named human with the required authority for the model type. There is no automated path to `true` |
| DR-2 | An approval is scoped: it names the model, the model version, the applicability envelope, the use classes covered, and any conditions. It is not a blanket "approved" |
| DR-3 | The approver must not be the author of the model implementation for the same version. Separation of duties applies to safety-relevant models |
| DR-4 | An approval expires or is withdrawn automatically on any of: the model version being superseded, the fidelity score falling below the floor, the envelope being narrowed below a dimension the approval depended on, or the approval's own validity period elapsing |
| DR-5 | Every approval, withdrawal, and re-approval is recorded in the audit ledger with the approver identity, the model version, and the decision basis. `model.validated.approvedBy` is the in-band copy |
| DR-6 | A safety-relevant prediction is one whose output informs a decision about flight hardware, material certification, a kill chain, or a human safety-of-life matter. The determination of what is safety-relevant for a given model is made by the owning pillar, published in the model's card section 2 and 10, and enforced by the platform's use classification |
| DR-7 | When a safety-relevant prediction is produced, the output carries the approving human's identity, the model version, the fidelity at the time of use, and the operating point. This is the "human-on-the-loop" requirement of PSDD §8, and it is what makes the prediction reconstructable |
| DR-8 | Approval is a workflow item in the pillar's review queue, not a flag on a form. An approval that requires no review of the evidence is not an approval; the card's section 5 is the reviewable artefact |

### How test evidence auto-updates fidelity

The end-to-end path is a projection over the event log. It requires no new infrastructure beyond what the foundation already provides.

```
test.result.recorded
   └─ causationId ─▶ twin validation job (Pillar G-3)
        ├─ selects candidate models by entity.relation.asserted (characterizedBy / derivedFrom) edges
        ├─ recomputes FidelityScore against the new evidence
        ├─ compares against priorFidelity
        │    ├─ envelope narrows            ─▶ auto-apply, notify owner
        │    ├─ |Δfidelity| > threshold      ─▶ auto-apply score, notify owner + dependent pillars
        │    └─ envelope would widen         ─▶ do NOT apply; raise an approval task
        └─ emits model.validated (modelId, modelVersion, fidelity, evidenceTestResultIds,
                                  priorFidelity, regenerationTriggered, approvedBy)
             └─▶ Model entity updated (fidelity, provenance)
                  └─▶ Fidelity registry index refreshed
                       └─▶ model card section 6 regenerated
```

| # | Property of this path |
|---|---|
| FD-1 | Fidelity is never a manual field. A `Model.fidelity` that was not produced by a `model.validated` event is a defect, and the projection detects and reports it |
| FD-2 | The recomputation is reproducible. It is a pure function of (model version, evidence set, scoring method). Re-running it on the same inputs yields the same score |
| FD-3 | The evidence set is explicit. `evidenceTestResultIds` and `fidelity.evidenceRefs` name the test results; a score with no evidence is not a score, it is an assertion, and the platform treats it as such |
| FD-4 | `regenerationTriggered: true` means the implementation changed. That is a new `modelVersion`, and a new version resets `approvedForUse` to `false`. A re-fit model does not inherit the old version's approval |
| FD-5 | The `model.validated` event's `causationId` names the `test.result.recorded` event that triggered it, so the causal chain from physical test to model score to downstream decision is one traversal |

### Drift monitoring

| Aspect | Rule |
|---|---|
| What is monitored | The inputs' distribution against the model's derivation data; the residuals between prediction and new evidence; the applicability-envelope population (how often and where the model is being used) |
| Cadence | Continuous where the inputs are streaming; per-batch for batch inference; at minimum, at every recomputation |
| Threshold | A configured drift score per model type, set in the card's section 9 |
| Action on drift | Below the "investigate" threshold: recorded, surfaced on the model dashboard. Above the "investigate" threshold: the model owner is notified and the fidelity score is recomputed. Above the "suspend" threshold: `approvedForUse` is withdrawn automatically, use is refused, and the dependent pillars are notified |
| Visibility | Drift status is visible on every model-derived output, so a consumer can see that the model was operating inside its validated regime |

### Interaction with the other ADRs

| ADR | Interaction |
|---|---|
| [ADR-0001](ADR-0001-event-sourced-foundation.md) | The fidelity path is a projection over the log, so the whole chain is reconstructable by replay — which is exactly what PSDD §8 Auditability demands for model versions |
| [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) | `ModelAttributes`, `FidelityScore` and the `model.validated` payload are contract-governed; adding a card section is a change to the card artefact, not to the contract, unless a new attribute is needed |
| [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md) | Model use is a policy-governed action. The approval requirement is an obligation attached to an ALLOW, and the evidence attached to the prediction is audited |
| [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) | Approvals, withdrawals, drift suspensions and out-of-envelope refusals are ledger entries |
| [ADR-0007](ADR-0007-classification-partitioning.md) | A model inherits the highest classification of its evidence set; the model's card and evidence references are classified accordingly, and a model with RESTRICTED evidence lives in P-R |

## Alternatives Considered

### ALT-1. Record the model and its validation report; no ongoing fidelity tracking

*Rejected.* This is the common practice and it is directly contradicted by PSDD §4.2 principle 4 ("every test result regenerates models automatically"), by G-3 and by G-4. It is rejected on the specific ground that it makes the fidelity score a static label whose accuracy decays silently with every new test. Given that the platform's stated purpose is to compress decision cycles, a stale fidelity score is a liability that looks like an asset.

### ALT-2. An external ML lifecycle tracker (MLflow-style registry) as the system of record for models

*Rejected as the system of record, retained as a convenience.** An external registry is good at tracking runs, parameters and artifacts, and it is weak in the ways that matter here. It does not know NGSH's ontology, so a model in the registry is not a `Model` entity with `evidenceRefs` into `TestResult` — the evidence link is the thing the platform is actually for. It does not carry classification, so it cannot be placed in a partition ([ADR-0007](ADR-0007-classification-partitioning.md)) and storing a SECRET-derived model's artifacts in an unclassified tracker is a disclosure. And it introduces a dependency with its own availability profile in a platform whose edge profile must operate with no control plane ([ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md)). NGSH's own `Model` entity plus a fidelity registry index is a sufficient implementation, and it keeps the model inside the ontology where the digital thread can reach it.

### ALT-3. Human-authored model cards in a wiki or document store, not linked to the entity

*Rejected.* A card that is not referenced by `ModelAttributes.modelCard` drifts from the model it describes. The pointer is what makes the card a property of the model rather than a document about it, and it makes "which models lack a card" a queryable question that the release pipeline can gate on.

### ALT-4. Automated approval — set `approvedForUse: true` when the fidelity score crosses a threshold

*Rejected.* This is the automation that C-004 was written to prevent. A fidelity threshold is not a risk acceptance. Approval means a person with domain authority has looked at the evidence and accepted the risk of the model being used in the stated regime. The threshold is a necessary condition for prompting a human, not a substitute for the human. Note also that the approval is scoped to an envelope, and the envelope is what a threshold cannot evaluate.

### ALT-5. Enforce the applicability envelope only at authoring time (a warning in the card)

*Rejected.* The envelope's entire purpose is to prevent a model being used outside the regime its evidence supports. A warning that a human must notice is not a control, because the use case that matters — a fast, automated, in-pipeline evaluation — is precisely the case where nobody is looking. Refusal (EN-2) is the only behaviour that is correct for a safety-relevant use.

### ALT-6. Statistical process control on residuals only, without an explicit applicability envelope

*Rejected.* SPC on residuals detects that the model is *wrong* somewhere; an applicability envelope prevents it being *asked* somewhere it is wrong. The two are complementary: the envelope is a precondition, the drift monitor is a detector for when the precondition stops being true. SPC alone also requires a steady nominal process, which a model under new evidence does not have.

### ALT-7. Store fidelity as a single scalar with no per-dimension components

*Rejected.* A single number cannot express "this model is excellent in the transonic regime and poor in the hypersonic heating regime", which is the normal condition of a hypersonic aero/thermal model. `FidelityScore.components` plus `applicabilityEnvelope` is the minimum structure that makes the score actionable. A single scalar also cannot be compared across two models with different `method` values, and PSDD §12's KPI "model fidelity improvement per campaign" requires a comparable measure.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | "How good is this model, and for what?" has a single, machine-checkable answer that is attached to the model itself. |
| P-2 | Test evidence flows into model quality automatically, which is the mechanism that delivers PSDD §4.2 principle 4 and makes the platform's value proposition (compressing design cycles) concrete and measurable. |
| P-3 | The model approval trail is part of the audit ledger, so a model-derived decision is reconstructable end to end: which model version, at what fidelity, under whose approval, applied to which operating point. |
| P-4 | Use outside the validated regime is impossible rather than discouraged, so the failure mode of a degraded model is a refusal, not a confidently wrong number. |
| P-5 | A new pillar can add a model type without changing the governance mechanism; the model card template and the fidelity registry are platform-provided. |
| P-6 | PSDD §8 Auditability's "every model version" is satisfied by construction: every version is a `Model` entity with a `modelVersion`, a parent link, and a card. |
| P-7 | The fidelity registry becomes a navigable index across the whole enterprise — "every model that is valid in this regime, with what evidence" — which is a direct input to the virtual test range (G-1) and to the campaign optimiser (PSDD §9.6). |
| P-8 | Automatic envelope narrowing is a safety-improving behaviour that requires no human in the loop, so the system is safer the more evidence it accumulates. |

### Negative

| # | Consequence |
|---|---|
| N-1 | Model card authoring is a real cost per model version, and it is a cost that lands on scarce domain engineers rather than on the platform team. This is the single largest source of friction in this ADR. |
| N-2 | Requiring a card and an envelope for *every* model — including trivial utility models — is over-governance for some cases. The rule stands for uniformity; the mitigation is a genuinely minimal card for low-risk model types, not a waiver mechanism, because waivers become the norm. |
| N-3 | The approval queue is a bottleneck. If the model-owning engineers are busy, model use stalls. The queue must be staffed and aged. |
| N-4 | Automatic fidelity recomputation requires a scoring implementation per model type, and the scoring method is itself a modelling choice that needs domain validation. A bad scoring method will produce confident, wrong fidelity numbers. |
| N-5 | Envelope enforcement (EN-2) means callers must supply an operating point. That is a real API burden on every consumer, and consumers who do not have one cannot use the model at all. |
| N-6 | Narrowing an envelope automatically can remove a capability that a pillar is relying on, mid-programme, with no human in the loop. It is the right default for safety and the wrong default for schedule, and the consequence is that the platform must notify dependent pillars promptly and loudly. |
| N-7 | The registry becomes a critical path. A defect in the fidelity projection corrupts the credibility of every model-derived result in the platform. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | The first model in each domain | Someone has to write the first card, define the first envelope, and implement the first scoring method, and there is no prior art in the organisation to copy. This is a schedule item with a named owner, not a documentation chore |
| HW-2 | Multi-dimensional envelopes | An aero model's envelope has Mach, altitude, Reynolds number, angle of attack, and possibly a laminar/turbulent transition condition. The contract's `applicabilityEnvelope` is `additionalProperties: {type: object}`, so the *shape* is free-form — but the *semantics* (which dimensions, what bounds, what the bounds mean) must be specified per model type. The platform must provide a per-model-type envelope template, or every team invents its own |
| HW-3 | Comparing fidelity across models and campaigns | PSDD §12 asks for "model fidelity improvement per campaign". That requires a comparable measure, which requires a shared `method` per model type. Getting domain authorities to agree on one scoring method per model type is a governance task with a long lead time |
| HW-4 | The approval queue's workflow | Approval is a workflow item with a domain authority, a reviewable evidence set, an expiry, and an automatic withdrawal path. That is a case-management system, not a boolean. Building it is more work than the mechanism it serves |
| HW-5 | Historical results | A model is re-scored and its envelope narrows. Results already produced under the old envelope are now, retrospectively, out of envelope. The platform must be able to identify them ("this result was produced by a model that has since narrowed"). This requires storing the fidelity and the operating point *at the time of use* on every model-derived output — which DR-7 requires, and which is why DR-7 is non-negotiable |
| HW-6 | Models with no natural operating point | Some models (e.g. a production-rate simulation) have no Mach number. The envelope must still be expressed, in whatever dimensions the model type has. "The envelope is empty" is not an acceptable state — it is a modelling failure that has to be resolved |
| HW-7 | The unapprovable model | A model that cannot be approved for any envelope — because no evidence exists yet — must still be usable for its intended development purpose. The exploratory mode (EN-4) is the escape valve, and its outputs must be visibly and machine-distinguishable so they can never be mistaken for evidence. Getting that distinction right in the UI, the API and the downstream pillars is a non-trivial consistency problem across three codebases |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §4.2 principle 4 — "Test-coupled M&S — models carry fidelity scores; every test result regenerates models automatically" | Implemented literally: `FidelityScore` on `Model`, and the `test.result.recorded` → `model.validated` projection that recomputes on every new evidence event. |
| PSDD §5.7 G-3 — "Automated model validation" | The twin validation job is the G-3 deliverable; the fidelity recomputation is its output contract. |
| PSDD §5.7 G-4 — "Fidelity registry — all models carry provenance, validation history, and applicability envelope" | The three named attributes are `provenance`, the card's section 6 (validation history) plus the `priorFidelity` chain, and `applicabilityEnvelope`. |
| PSDD §8 AI/ML — "Model cards for all ML; human-on-the-loop for safety-relevant predictions; drift monitoring; MLOps pipeline with approval gates" | Card required for all models; `approvedForUse` plus scoped approval plus the attached human identity on the prediction (DR-7) is the human-on-the-loop; drift monitoring section 9; the approval workflow is the gate. |
| PSDD §8 Auditability — "Every model version ... reconstructable" | Every version is a `Model` entity with a `modelVersion`, a `parentModelId` chain, a card, and an approval record in the ledger. |
| PSDD §9 — "Governance: all models carry provenance, validation history, applicability limits; safety-relevant outputs require human approval" | The decision is the direct implementation of this sentence; the seven AI/ML services in §9 each attach to a model type and inherit the card and approval requirements. |
| PSDD §12 KPI — "model fidelity improvement per campaign" | Delivered by the `priorFidelity` / `fidelity` pairs in successive `model.validated` events, comparable where the `method` matches. |
| PSDD §6.3 — "Data lineage automated end-to-end (supports CMMC assessment and program protection planning)" | `derivedFrom` edges plus `Provenance.parentRefs` plus `evidenceRefs` give the model-evidence lineage that a PPP artifact and an assessment both require. |
| CMMC 2.0 L2 (SA family) | The model card, the approval record and the drift record form the configuration-control evidence for a model version. |
| CMMC 2.0 L2 (SI family) | SI-7 (integrity) is supported by the model version chain and the content-addressed card artefact. |
| CMMC 2.0 L2 (AU family) | Approvals, withdrawals, suspensions and refusals are ledger entries; model-derived outputs carry the approving identity. |
| CMMC 2.0 L2 (CA family) | Model artefacts inherit the classification of their evidence, so an ML model trained on RESTRICTED threat data is itself RESTRICTED and is placed in P-R accordingly ([ADR-0007](ADR-0007-classification-partitioning.md)). |
| DoD directives on AI ethics and responsible AI | Model card content, intended-use restriction, out-of-scope use and a retirement condition are the artefacts an AI governance review expects to see. |

## References

**PSDD:** §4.2 principle 4, §5.2 (B-2 CMC process characterisation — the process models this governs), §5.3 (C-2 anomaly detection, C-3 twin validation loop), §5.6 (F-1 threat reconstruction, F-2 kill-chain simulator and its surrogate model), §5.7 (G-3, G-4), §6.1 (ontology: `Model` with `FidelityScore`), §6.3 (data governance, lineage), §8 (AI/ML, Auditability), §9 (AI/ML services and governance), §12 (KPIs — model fidelity improvement per campaign), §13 (risks — M&S fidelity shortfall is tracked as a delivery risk).

**Contracts:**
- `contracts/ontology/entities.schema.json` — `ModelAttributes`: `modelType` enum, `modelVersion`, `parentModelId`, `fidelity`, `codeRef`, `inputSchemaRef`, `outputSchemaRef`, `modelCard`, `runtime`, `approvedForUse` (default `false`).
- `contracts/ontology/common.schema.json` — `FidelityScore` with `overall`, `method`, `components`, `applicabilityEnvelope`, `evaluatedAt`, `evidenceRefs`; `Provenance` with `method`, `confidence`, `modelVersion`, `reviewedBy`.
- `contracts/events/model.validated.schema.json` — `modelId`, `modelVersion`, `fidelity`, `evidenceTestResultIds`, `priorFidelity`, `regenerationTriggered`, `approvedBy`.
- `contracts/events/test.result.recorded.schema.json` — the evidence event; `modelVersionIds` links the result to the model versions it exercised; `reviewedBy` is the human reviewer on the result itself.
- `contracts/ontology/relations.schema.json` — `characterizedBy` (Material, ProcessRun, Part → Model, TestResult) and `derivedFrom` (Model, ThreatSystem, TestResult → Model, TestResult, ThreatObservation) are the edges that select candidate models for recomputation.
- `contracts/ontology/registry.json` — C-004 ("A Model used in a safety-relevant prediction must have approvedForUse=true and a non-null fidelity score"), enforced at use scope; `mayCrossClassification: true` on `derivedFrom` permits evidence lineage across partitions under the rule in [ADR-0007](ADR-0007-classification-partitioning.md).

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the fidelity path is a projection over the log), [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md) (model use is a policy-governed action with obligations), [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) (the approval trail), [ADR-0007](ADR-0007-classification-partitioning.md) (models inherit classification from evidence), [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) (contract governance of the model shapes).
