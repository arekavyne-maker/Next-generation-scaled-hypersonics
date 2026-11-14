# ADR-0003: Platform-Agnostic, Hybrid-First Deployment

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §10 fixes the deployment pattern: a GovCloud IL5 enclave, an on-prem IL6 annex for classified threat and fire-control data, and edge nodes at factories and ranges. PSDD §4.2 principle 3 requires the platform to be deployable at the edge, with classified annexes physically segregated. PSDD §8 sets a 99.9% availability target for the core fabric, requires multi-program tenancy, and requires all pillars to be independently deployable and licenseable. PSDD §3.2 places BMC3-style command-and-control replacement explicitly out of scope — NGSH integrates with fielded systems rather than replacing them.

These requirements conflict with the default posture of a modern cloud-native platform. A service written against a specific cloud SDK inherits that cloud's identity model, its secret distribution, its network assumptions, its storage semantics, its logging pipeline and its pricing model. It also inherits an operational assumption that the service can reach a managed control plane. At an IL6 annex on a disconnected network, or on a factory floor with an unreliable link, that assumption is false. At a range with no outbound network at all, it is fatally false.

The competing error is to go the other way and assume everything runs on-premises, in one Kubernetes cluster, in one accreditation envelope. That fails the IL5 requirement, fails multi-program tenancy across agencies, and produces a platform nobody can operate at 120-engineer scale without a platform team of 40.

The decision that must be made is not "which cloud" but "what is the platform and what is a deployment". NGSH needs a platform abstraction that lets the *same* domain code run in a local development environment, an IL5 enclave, an IL6 annex, and a disconnected edge node, with the difference expressed as configuration and capability, not as a code branch.

## Decision

**NGSH is platform-agnostic and hybrid-first. Domain code contains no cloud SDK, no managed-service client, and no environment-specific branching. Three deployment zones exist, and the platform behaves identically in all three, differing only in declared capability and enforced posture.**

### The prohibition

| # | Rule | Enforcement |
|---|---|---|
| P-1 | No domain package may import a cloud provider SDK, a managed-service client, or a vendor-specific orchestration API. | CI dependency-boundary check. Go: `go list -deps` scan for `aws-sdk-go*`, `azure-sdk-for-go*`, `google-cloud-go*`, `cloud.google.com/*`. Python: import-linter contract forbidding `boto3`, `azure.*`, `google.cloud.*` outside an explicitly declared adapter package. TypeScript: ESLint `import/no-restricted-paths` with the same exclusion. The build fails on violation |
| P-2 | No domain package may read an environment variable, a file path convention, or a hostname in order to decide *which behaviour to run*. Behavioural variation must be declared as a **capability** in a configuration document, not sniffed. | Lint rule banning `os.environ`/`process.env` reads outside the config package. The config package may read them; the config package may only produce a capability declaration |
| P-3 | Every external dependency on a platform service is expressed as a **port** — an interface declared in a domain-owned package — with an adapter in an infrastructure package that is allowed to be platform-specific. | Architectural test asserting that domain packages have no infrastructure imports |
| P-4 | Ports are capability-gated at runtime, not compile-time. A deployment declares which capabilities are present; a missing capability produces a typed `CapabilityUnavailable` error and a defined degraded behaviour, never a crash and never a silent default | Every port call site handles `CapabilityUnavailable`; enforced by review checklist plus a per-pod contract test |
| P-5 | All storage access is through ports. The concrete backing store is a deployment decision, not a code decision. | Same architectural test as P-3 |
| P-6 | The domain layer contains no secrets, no endpoints, and no environment-specific identifiers. | Secret scanning in CI; config schema validation |

### The three zones

| Zone | Name | Purpose | Accreditation | Typical contents |
|---|---|---|---|---|
| **Z-1** | Central fabric | Shared, multi-tenant, multi-program platform core | IL5 (FedRAMP Moderate equivalent), CMMC 2.0 L2+ | Fabric (event log), ontology service, policy service, audit service, thread service, ingest service, console, projection stores |
| **Z-2** | Accredited cloud enclave | Elastic scale for the Pillar F/G compute: Monte Carlo batches, ML training, lakehouse | IL5, with an accredited path to higher assurance where required | Compute partitions, lakehouse, vector index, model training, surrogate model serving |
| **Z-3** | Segregated edge annex | Field and factory execution; disconnected-capable | IL6 / physical security, physically segregated from Z-1 and Z-2 | Edge agent, local store-and-forward queue, local projection cache, local ingest buffer, local console replica |

Additional non-production zone: **Z-0**, the developer local environment, which runs the same domain code against local emulators and is never a source of truth.

### The rule that makes it work

> **The edge annex and the local environment are not reduced deployments. They are the same deployment with fewer capabilities declared.**

A degraded mode is not an error path and not a build variant. It is a *capability declaration*. A deployment declares:

```
capabilities:
  storeAndForward:      true      # local durable queue for disconnected operation
  reconcileBidirectional: true
  localProjectionCache: true
  bulkIngest:           false
  monteCarloDispatch:   false
  modelTraining:        false
  surrogateInference:   false
  sanitizeExtract:      false     # no classified content present to sanitize
```

The same service binary, running the same domain code, executes against these declarations. An edge annex has `monteCarloDispatch: false`; the kill-chain simulator's entry point returns `CapabilityUnavailable` with a message pointing to the Z-2 submission path, and the UI presents a queue-and-forward action instead of a failure.

### Edge and degraded mode

| Aspect | Behaviour |
|---|---|
| Store-and-forward | The edge agent maintains a durable, encrypted, bounded local queue of events destined for the fabric. Bounded means it has a configured capacity; when full, the oldest or lowest-priority items are dropped with an explicit `dropped` audit entry — never silently |
| Local projection | The edge node maintains a local projection of the entities it needs (its own site’s parts, process runs, test articles). It reads these from the fabric when connected and from its local store when not |
| Write path | Edge writes append to the local queue with the local sequence allocator described in [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md), and are reconciled deterministically on reconnection |
| Read path | Local projection serves reads. When connected, reads are served from the local projection too, so read behaviour is identical connected or disconnected — the single most important property for operator trust |
| Reconciliation | On reconnection, the edge drains its queue to the fabric; the fabric reconciles against any changes it received from other sources during the disconnection |
| Clock | Edge nodes hold a disciplined clock (NTP, or PTP where the site supports it). Skew is measured and recorded at reconciliation, not assumed away |
| Classification | The edge annex holds only the classification it is accredited for. Its local stores are physically separate instances, never a shared volume with another zone |
| What the edge does *not* do | No cross-site consensus, no global read-your-writes, no real-time cross-site visibility, no multi-site transaction. These are explicitly out of scope and are enumerated in [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md) |

### Deployment profiles

Four profiles are defined, all running the same domain code:

| Profile | Where | Acceleration | Posture | Notes |
|---|---|---|---|---|
| **DP-L** Local | Developer workstation or a CI runner | None | No classified content; mock identity; synthetic threat data only | Used for contract tests, replay tests and the degraded-mode test harness |
| **DP-5** IL5 enclave | Z-1 + Z-2 | Managed Kubernetes or equivalent; autoscaling on the Monte Carlo partition | CUI; PIV/ICAM; CMMC L2+ | The production posture for all CUI data; multi-tenant |
| **DP-6** IL6 annex | Z-3 | Bare metal or a small on-prem cluster; no external control plane | SECRET-classified content; physical security; local identity authority | The segregated annex; the only zone that may hold threat and fire-control data |
| **DP-E** Edge | Z-3 at a factory, range, or lab | Single-node appliance or container on an industrial host; no control plane | CUI, scoped to the site | Store-and-forward; a subset of capabilities; local console replica |

### What the abstraction buys and what it costs are set out in the Consequences section.

## Alternatives Considered

### ALT-1. Cloud-native-first on one accredited cloud (e.g. AWS GovCloud managed services as the primary path)

*Rejected.* It is the fastest route to a working product and the slowest route to an IL6 annex and a disconnected factory floor. Managed identity, managed key management, managed storage and managed networking all assume a reachable control plane and a trust relationship with a provider; at an IL6 annex neither is guaranteed. It also concentrates the accreditation burden on the provider's own ATO rather than on NGSH's, which does not help when a customer needs a *local* or *on-prem* deployment for ITAR reasons. Most decisively, it puts the deployment posture of every domain service inside a vendor's API surface, which is the exact coupling this ADR forbids under rule P-1.

### ALT-2. On-premises Kubernetes everywhere, single accreditation envelope

*Rejected.* It handles IL6 and the edge cleanly, but it does not deliver the elasticity that the Pillar F Monte Carlo workload requires — PSDD §8 specifies a 10,000-run engagement batch completing in under 4 hours on a dedicated partition, and the peak concurrency profile of a program office doing ad-hoc "what-if" analysis is extremely bursty. It also undercuts multi-agency multi-program tenancy (PSDD §8 Scalability), because a single cluster cannot be credibly accredited for both a government enclave and an academic partner's sandbox.

### ALT-3. Serverless / managed FaaS for the data plane

*Rejected.* Three disqualifiers. Latency and cold start are incompatible with a 10 GB/s sustained ingest path. Managed FaaS platforms are not accredited at IL5/IL6 and cannot be, because the execution substrate is outside the accreditation boundary. And the platform-agnostic goal collapses: the FaaS handler signature *is* the platform.

### ALT-4. Container-only, cloud-neutral via a service mesh and CSI abstraction (one abstraction layer, many backends)

*Rejected as the primary approach, retained as an implementation detail.* A mesh plus a CSI abstraction is the right *tooling* for this problem, and the reference implementation should use both. It is not a substitute for the architectural rule, because the mesh and CSI abstract *transport and storage*, not *identity, secrets, scheduling and control plane*. The residual vendor coupling after adopting them is still substantial and still sits in domain-reachable code paths. This option was rejected only as a *sufficient* answer; the adoption of mesh and CSI is explicitly in scope for WP-0.1 and WP-0.11.

### ALT-5. Two separate codebases: a cloud edition and an on-prem edition

*Rejected.* This is the option that generates the most defects. Two codebases drift; fixes are applied twice or, worse, only to the edition the team is actively working on; the security review burden doubles; and the acceptance test matrix becomes a cross product. It also directly contradicts PSDD §8 Modularity (each pillar must stand alone) by making the *platform* non-standalone.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | One codebase, four deployment profiles. Fielding a new site is a configuration and accreditation exercise, not a software release. |
| P-2 | The IL6 annex and the edge appliance are first-class, because the capability-declaration model treats "no cloud" as a set of absent capabilities rather than as a special case. |
| P-3 | Vendor exit is a matter of writing a new adapter behind an existing port. The blast radius of an adapter is one infrastructure package. |
| P-4 | Multi-program tenancy is natural. Tenancy is a query filter and a capability declaration, not a cluster split. |
| P-5 | Testability. The full capability-declaration surface can be exercised in CI on every build by running the same conformance suite against DP-L, DP-5, DP-6 and DP-E configurations. Degraded-mode behaviour is therefore *tested*, not asserted. |
| P-6 | PSDD §8 Modularity is materially stronger: a pillar licensed standalone ships as a set of services plus a capability declaration, and can run in a customer-owned envelope. |
| P-7 | Cost control. Compute-heavy work (Monte Carlo, training) can be scheduled into the elastic Z-2 partition and drained at night, while the IL5/IL6 zones run on predictable capacity. |
| P-8 | The "complement, never replace" posture (PSDD §4.2 principle 2, §3.2) is easier to honour: NGSH can be deployed inside a prime's or a government's existing envelope rather than requiring them to adopt a cloud. |

### Negative

| # | Consequence |
|---|---|
| N-1 | We own more of the stack. Managed multi-AZ failover, managed key rotation, managed secret distribution and managed backup/restore are not free; in an IL6 context they are not available at all. |
| N-2 | The capability-declaration model is a real abstraction cost. Every port has a "not here" path that must be written, tested and given a user-facing meaning. |
| N-3 | Two classes of bug are introduced by the abstraction: capability-declaration drift (a deployment declares a capability it does not actually have) and adapter divergence (two adapters of the same port behave differently). Both need dedicated test coverage. |
| N-4 | The prohibition P-1 is a cultural rule, not a technical one. It will be violated under schedule pressure unless the CI gate is treated as unskippable and ownership of the dependency manifest is assigned to the Platform pod. |
| N-5 | Performance-critical paths must be verified on the deployment profile they will actually run on, not only on a developer laptop. A Go data plane tuned for a container in DP-5 may not be tuned for a resource-constrained DP-E appliance. |
| N-6 | Documentation burden: every capability, every adapter, and the degraded behaviour of each must be kept current, or the abstraction becomes a fiction. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Optimising for a specific platform's primitives | No direct managed-query acceleration, no platform-specific streaming, no platform-native ML. Performance must be won in the domain code and in the port design. |
| HW-2 | Managed identity federation | The PIV/ICAM integration (IF-6) must be implemented against a portable OIDC/OAuth 2.0 profile rather than a provider's proprietary broker. This is more work up front and less work at the fourth accreditation. |
| HW-3 | Managed HSM-backed key management | The key-management posture in `04-security-architecture.md` assumes a locally operable HSM in each zone, because no cloud KMS is reachable from an IL6 annex or an edge appliance. |
| HW-4 | Autoscaling the Monte Carlo partition across two zones | Z-2 is elastic, Z-3 is not. A workload that spans both needs an explicit work-splitting policy rather than a single scheduler. |
| HW-5 | Debugging across the abstraction | A developer reproducing a field failure must be able to reproduce the field's capability declaration and adapter versions. The edge agent must export its effective capability declaration and adapter versions as part of every diagnostic bundle. |
| HW-6 | Third-party dependencies that are themselves cloud-shaped | A library that requires a managed control plane (a managed queue, a managed secret store, a managed ML tracker) cannot be used in the domain layer even if it is vendor-neutral in name. The rule P-1 must be applied to transitive dependencies, not only to direct imports. |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §10 — "GovCloud IL5 enclave + on-prem IL6 annex (classified threat data, fire-control data) + edge nodes at factories/ranges" | Zones Z-1, Z-2, Z-3 are the direct implementation of this sentence. The capability-declaration model is what makes Z-3 an ordinary deployment rather than a special case. |
| PSDD §4.2 principle 3 — "Deployable at the edge — factory-floor and range annexes with sync to the central fabric; classified annexes physically segregated" | Rule P-1 plus the edge behaviour table. Physical segregation is a topology property; the code must not assume it. |
| PSDD §8 Availability — "99.9% core fabric; edge annexes degraded-mode capable with later sync" | Degraded mode is a specified capability set with a defined behaviour table, testable in CI across all four profiles. |
| PSDD §8 Scalability — "Multi-program tenancy; federated deployments across services and agencies" | Tenancy is a filter plus a capability declaration, independent of the deployment substrate, so a federated deployment is a deployment topology rather than a fork. |
| PSDD §8 Modularity — "All pillars independently deployable and licenseable" | A pillar is a service set plus a capability declaration. Nothing in the pillar's domain code ties it to a substrate. |
| PSDD §8 Modularity + §10 — supply-chain assurance | Rule P-1 keeps vendor SDKs out of the shipped product, so the SBOM for the domain layer contains no cloud-provider component whose behaviour is outside the accreditation boundary. Each adapter is a separately versioned, separately scanable artifact. |
| CMMC 2.0 L2 (CM family) | Every deployment profile declares its configuration in a controlled document; capability declarations are configuration items under change control. |
| CMMC 2.0 L2 (CP / MP) | The same domain artifact deployed to four profiles with four configurations is exactly the case where build provenance matters: the image digest and the capability declaration are recorded together. |
| CMMC 2.0 L2 (SC family) — boundary protection | Zone boundaries and the absence of control-plane reachability from Z-3 are explicit, testable properties, not environmental assumptions. |

## References

**PSDD:** §3.2 (out of scope: no BMC3 replacement), §4.1 (concept diagram and the three-zone fabric sketch), §4.2 (design principles 2 and 3), §7 (IF-1..IF-7 external interfaces), §8 (Availability, Performance, Scalability, Modularity), §10 (Security & Compliance Architecture — deployment pattern and cross-domain guards), §13 (risks: classification friction, threat-data access chokepoint).

**Contracts:**
- `contracts/events/event-envelope.schema.json` — the `edge` block (`nodeId`, `capturedAt`, `reconciledAt`, `clockSkewMs`), the mechanism by which a Z-3 write is identified after reconciliation.
- `contracts/events/ingest.batch.accepted.schema.json` — carries the same `edge` block plus `source`, `sha256` and `objectUri`, which is the edge's durable-queue flush record.
- `contracts/ontology/registry.json` — `classificationFloor` per entity type is what determines which zone an entity may be written in.

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the log is available in every zone, including disconnected), [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) (contract-only coupling is what makes polyglot possible), [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md) (reconciliation semantics), [ADR-0007](ADR-0007-classification-partitioning.md) (physical partitioning that follows zone boundaries).
