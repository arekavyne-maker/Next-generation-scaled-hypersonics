# Next-Generation Scaled Hypersonics (NGSH)
## Preliminary Software Design Document (PSDD)

| Field | Value |
|---|---|
| Document ID | NGSH-PSDD-001 |
| Version | 0.1 (Preliminary) |
| Date | 2026-11-14 |
| Classification Handling | CUI (document); system designed for IL5/IL6 operation |
| Status | Draft for internal review / teaming discussion |
| Program Alignment | OUSW(R&E) RNI Scaled Hypersonics (SHY); NSWC Crane Project 26-07; WISH 25-14; DASH-MOT 23-12; S2MARTS 22-04; HAMTC 21-13; MDA counter-hypersonic kill-chain initiatives |

---

## 1. Executive Summary

**Next-Generation Scaled Hypersonics (NGSH)** is a dual-mission software platform — the digital engineering, test, and industrial-readiness environment for America's hypersonic enterprise. It serves both sides of the mission with one shared data fabric:

- **Strike side**: model-based systems engineering (MBSE), digital-thread manufacturing, CMC process intelligence, and production surge readiness for hypersonic weapon systems (aligned with SHY, 26-07, DASH-MOT, HAMTC).
- **Shield side**: counter-hypersonic kill-chain engineering, threat digital twins, and a virtual test enterprise (aligned with MDA Project Maverick, GPI, HBTSS/PWSA, Golden Dome reference architecture).

The strategic premise: both sides of the hypersonic mission fail or succeed for the same reasons — disconnected data, slow test cycles, no digital thread, and an industrial base that cannot scale. NGSH is the connective tissue. It is positioned to be treated as **vital national-security infrastructure**: not a tool that helps build hypersonic systems, but the environment without which the U.S. cannot compress counter-hypersonic kill chains, stretch scarce defense dollars, or verify surge production capacity.

---

## 2. Problem Statement and Mission Need

### 2.1 Problem

| # | Problem | Evidence |
|---|---|---|
| P1 | Adversary hypersonic/high-speed strike systems are fielded today; U.S. glide-phase defense (GPI) reaches full capability only in the early 2030s | MDA program timeline; Northrop acceleration contract (2026) |
| P2 | Interim defense depends on integration and fire-control data quality (sensor-to-shooter), not new hardware — MDA Project Maverick (2027 flight test) | MDA interim counter-hypersonic architecture |
| P3 | Space-based fire control (HBTSS in SDA PWSA) is the pacing item; kill chain runs from proliferated LEO tracking through offboard cueing to effector | SDA/HBTSS program descriptions |
| P4 | FY2026 request: ~$3.9B offensive hypersonics vs. $200.6M hypersonic defense — defense must buy speed and integration, not hardware | DoD FY2026 budget request |
| P5 | National hypersonic test enterprise is fragmented; M&S is not test-coupled; designs iterate on scarce flight tests | Atlantic Council hypersonics task force; GAO reports |
| P6 | Industrial base cannot demonstrate surge production; CMC materials processes are poorly characterized and expensive to qualify | SHY RNI; DASH-MOT |
| P7 | Cleared, skilled workforce supply does not track classified production demand | WISH; JHTO workforce studies |

### 2.2 Mission Need Statement

Provide a single, CUI-compliant, zero-trust software environment that (a) compresses hypersonic system development from design to flight demonstration, (b) engineers and validates counter-hypersonic kill-chain architectures on software timelines, (c) verifies industrial-base surge capacity continuously, and (d) guarantees a cleared workforce pipeline — using one shared ontology linking parts, processes, tests, threats, and people.

---

## 3. Scope and Objectives

### 3.1 In Scope

- Digital thread / MBSE environment for hypersonic weapon systems (payload, booster, GNC, airframe, thermal protection)
- Manufacturing execution & process intelligence for CMC and extreme-environment materials
- Test & evaluation data platform (ground, wind tunnel, sled, flight) with automated validation
- Supply chain visibility, surge simulation, and reconstitution planning
- Counter-hypersonic kill-chain simulator, threat digital twins, fire-control data quality scoring
- Cleared-workforce training, credentialing, and demand modeling
- Federated M&S / virtual test range capability

### 3.2 Out of Scope (v1)

- BMC3 / command-and-control software that replaces fielded systems (NGSH *tests and integrates with* BMC3; it does not replace it)
- Weapon GNC or flight software
- Hardware manufacturing (partner domain)

---

## 4. System Overview

### 4.1 Concept

NGSH is organized as **two layers sharing one ontology and one data fabric**:

```
┌──────────────────────────────────────────────────────────────────┐
│                     ZERO-TRUST DATA FABRIC                        │
│        IL5/IL6-capable · CUI · CMMC 2.0 L2+ · ITAR/EAR-aware      │
├──────────────────────────────────────────────────────────────────┤
│  MISSION LAYER                                                    │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐   │
│  │ Pillar F      │ │ Pillar G      │ │ Pillar H              │   │
│  │ Kill-Chain    │ │ Test & M&S    │ │ Surge & Resilience    │   │
│  │ Engineering   │ │ Federation    │ │ Command               │   │
│  │ + Threat Twins│ │ + Virtual     │ │ + Affordability       │   │
│  │               │ │   Range       │ │ Engineering           │   │
│  └───────────────┘ └───────────────┘ └───────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ Pillar E — Cleared Workforce Pipeline of Record           │   │
│  └───────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  FOUNDATION LAYER                                                 │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐   │
│  │ Pillar A      │ │ Pillar B      │ │ Pillar C              │   │
│  │ MBSE Digital  │ │ Smart Mfg &   │ │ Test & Flight Data    │   │
│  │ Thread        │ │ CMC Process   │ │ Platform              │   │
│  │               │ │ Intelligence  │ │                       │   │
│  └───────────────┘ └───────────────┘ └───────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ Pillar D — Supply Chain & Production Scaling Analytics    │   │
│  └───────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│  SHARED ONTOLOGY: parts ↔ processes ↔ tests ↔ threats ↔ people    │
└──────────────────────────────────────────────────────────────────┘
         ⇅ Open APIs: prime PLM/MES, MDA/Aegis systems, SDA PWSA,
           range instrumentation, university LMS instances
```

**Key architectural insight:** the digital thread that traces a U.S. CMC part from powder to flight also traces an adversary threat from observation to engagement solution. One ontology, two mission sides. Point-tool competitors will serve one side; NGSH is the only environment serving both.

### 4.2 Design Principles

1. **Digital thread first** — every artifact (requirement, part, process plan, test result, threat observation) is a node in one graph.
2. **Complement, never replace** — open APIs into prime PLM/MES/BMC3; NGSH is the integration and verification layer, not a rip-and-replace.
3. **Deployable at the edge** — factory-floor and range annexes with sync to the central fabric; classified annexes physically segregated.
4. **Test-coupled M&S** — models carry fidelity scores; every test result regenerates models automatically.
5. **Cost-as-a-requirement** — affordability traced from the earliest design decision (per national hypersonics strategy guidance).
6. **Security by design** — CMMC 2.0 Level 2+ processes, zero trust, attribute-based access control, ITAR/EAR data partitioning from day one.

---

## 5. Functional Design — Pillars

### 5.1 Pillar A — MBSE & Digital Thread Core

| ID | Capability | Description |
|---|---|---|
| A-1 | Digital twin backbone | Single source of truth for configuration, interfaces, requirements across payload/booster/GNC/airframe/TPS |
| A-2 | Modularity engine | Library-based architecture enforcement; auto-generates family-of-system variants from common core (SHY requirement) |
| A-3 | Requirements-to-test traceability | End-to-end trace with automated coverage and verification status reporting |
| A-4 | Technology insertion planner | TRL/SRL mapping against production slots; supports rapid technology integration (SHY) |
| A-5 | Digital engineering SaaS | SysML v2 environment, requirement management, ICD generation, pre-integrated DoN reference architectures |

### 5.2 Pillar B — Smart Manufacturing & Materials Process Intelligence

| ID | Capability | Description |
|---|---|---|
| B-1 | Defense MES | Work instructions, traveler management, nonconformance, genealogy — tuned for low-rate/high-complexity production |
| B-2 | CMC process characterization | Process parameters → microstructure → test results; ML quality prediction; drift detection before scrap |
| B-3 | Test capability management | Schedule/execute/archive manufacturing test campaigns (HAMTC); auto-curation into reusable datasets |
| B-4 | Rate & cost simulation | Discrete-event production simulation; what-if for rate increases, workforce shifts, supply disruption (SHY) |

### 5.3 Pillar C — Test, Evaluation & Flight Demonstration Data Platform

| ID | Capability | Description |
|---|---|---|
| C-1 | Unified test data lake | Ground, tunnel, sled, flight data with full configuration context (variant, lot, software build) |
| C-2 | Automated reduction & anomaly detection | ML pipelines; near-real-time thermal/structural/aero anomaly surfacing |
| C-3 | Twin validation loop | Flight-vs-simulation comparison; automated model updates feeding Pillars A/B/F |
| C-4 | Campaign management | Test planning, instrumentation manifests, range coordination data exchange |

### 5.4 Pillar D — Supply Chain & Production Scaling

| ID | Capability | Description |
|---|---|---|
| D-1 | Multi-tier visibility | Supplier risk scoring, capacity monitoring, part provenance/chain-of-custody |
| D-2 | Foreign dependency mapping | Critical single-source nodes (CMC precursors, high-temp electronics) with reconstitution playbooks |
| D-3 | Surge readiness twin | Continuous verified model of peacetime→conflict production scaling |

### 5.5 Pillar E — Cleared Workforce Pipeline of Record

| ID | Capability | Description |
|---|---|---|
| E-1 | Digital-twin training | AR/VR + screen simulators built on the actual digital thread (real CMC cells, test stands, assembly lines) |
| E-2 | Replicable curriculum engine | Deployable courseware packages for any university/manufacturing hub (WISH core requirement) |
| E-3 | Skills credentialing | Badging tied to real process qualifications; feeds B-1 work-authorization |
| E-4 | Workforce demand model | Gap analysis: cleared-skills supply vs. classified production demand, by region and trade |
| E-5 | Industry–academia sandbox | Shared, sanitized environments for real manufacturing scenarios |

### 5.6 Pillar F — Counter-Hypersonic Kill-Chain Engineering ⭐

| ID | Capability | Description |
|---|---|---|
| F-1 | Threat digital twins | Configurable HGV/HCM/boost-glide models reconstructed from intel, telemetry, range observation; versioned, confidence-scored |
| F-2 | Kill-chain simulator | Detect→track→custody→engage end-to-end modeling for candidate architectures (HBTSS + WFoV/MFoV cueing → Aegis/GPI → effector); Monte Carlo engagement statistics |
| F-3 | Fire-control data quality scoring | Continuous measurement of custody handover quality, track purity, fire-control solution error vs. thresholds — turns vague requirements into testable metrics |
| F-4 | Interim architecture workbench | Project Maverick-style: compose existing sensors + offboard cueing into candidate interim solutions; virtual validation before flight test |
| F-5 | Golden Dome readiness | Reference-architecture plug-in framework for the homeland missile-defense shield |
| F-6 | Red/blue co-simulation | Strike performance vs. defense performance against identical threat models — honest measure of the hypersonic balance |

### 5.7 Pillar G — Test Enterprise & M&S Federation ⭐

| ID | Capability | Description |
|---|---|---|
| G-1 | Virtual test range | Cloud-federated ground/tunnel/sled/flight data with physics M&S; iterate designs digitally before consuming scarce range slots |
| G-2 | Campaign digital twin | Range capacity, telemetry coverage, target/instrumentation availability modeling; cross-DoD scheduling optimization |
| G-3 | Automated model validation | Every test result scores model fidelity and regenerates aero/thermal/plasma models |
| G-4 | Fidelity registry | All models carry provenance, validation history, and applicability envelope |

### 5.8 Pillar H — Industrial Surge & Affordability ⭐

| ID | Capability | Description |
|---|---|---|
| H-1 | Surge readiness command | Continuous verified surge model (SHY question answered continuously, not per RNI) |
| H-2 | Reconstitution planning | Automated playbooks for critical node loss; time-to-reconstitute metrics |
| H-3 | Affordability engineering | Cost traced to every design decision; unit-cost prediction vs. rate curves; feeds next-gen affordable missile family and future reusable hypersonic aircraft programs |

---

## 6. Data Design

### 6.1 Core Ontology (primary entities)

`System`, `Variant`, `Subsystem`, `Part`, `Material` (CMC lot/prepreg batch), `ProcessPlan`, `ProcessRun`, `TestArticle`, `TestCampaign`, `TestResult`, `Requirement`, `Interface`, `Model` (with `FidelityScore`), `ThreatSystem`, `ThreatObservation`, `EngagementScenario`, `Supplier`, `PartProvenance`, `Skill`, `Credential`, `Person` (cleared), `Facility`, `RangeSlot`.

Edges: `satisfies`, `verifies`, `manufacturedBy`, `characterizedBy`, `derivedFrom`, `threatens`, `engages`, `requiresSkill`, `supplies`, `reconstitutes`.

### 6.2 Data stores

| Store | Technology | Content |
|---|---|---|
| Graph DB | Property graph (e.g., Neptune/JanusGraph-class) | Ontology, digital thread, traceability |
| Time-series | TSDB | Telemetry, process sensors, fire-control quality metrics |
| Object store | S3-compatible, IL-graded | Raw test data, imagery, large artifacts |
| Document store | NoSQL | Requirements, ICDs, curricula, playbooks |
| Lakehouse | Open table format | ML training corpora, curated datasets |
| Vector index | Embedding store | Requirements/test/threat semantic search & retrieval-augmented analysis |

### 6.3 Data governance

- CUI tagging at ingestion; attribute-based access control (ABAC) with classification, program, citizenship, and need-to-know attributes
- ITAR/EAR partitions; sanitized extracts for academic partners (Pillar E)
- Full audit trail; immutable test-result ledger (append-only)
- Data lineage automated end-to-end (supports CMMC assessment and program protection planning)

---

## 7. Interface Design (External)

| Interface | Direction | Purpose |
|---|---|---|
| IF-1 Prime PLM/MES APIs | Bi-dir | Sync part/BOM/process data (Teamcenter/Windchill/SAP-class) |
| IF-2 MDA/Aegis systems | In (data), Out (scenarios) | Threat tracks, engagement results; scenario definitions for BMC3 test |
| IF-3 SDA PWSA / HBTSS data feeds | In | Tracking-layer custody/fire-control data quality ingestion |
| IF-4 Range instrumentation | Bi-dir | Test article manifests, telemetry, schedules |
| IF-5 University LMS / AR-VR clients | Out | Curriculum packages, training environments |
| IF-6 Government identity (PIV/ICAM) | In | Authentication, clearance verification |
| IF-7 Analytics/BI | Out | Program-office dashboards, Congressional reporting metrics |

**Posture:** NGSH does not replace BMC3 — it makes BMC3 testable and integrable. Prime partners are complements, not competitors.

---

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Security | Zero trust; IL5 baseline with IL6 annex architecture; CMMC 2.0 L2+ processes; ABAC; continuous monitoring (CONMON) |
| Availability | 99.9% core fabric; edge annexes degraded-mode capable with later sync |
| Performance | Kill-chain Monte Carlo: 10k-run engagement batch < 4h on dedicated partition; test data ingestion ≥ 10 GB/s burst (range support) |
| Scalability | Multi-program tenancy; federated deployments across services and agencies |
| Interoperability | Open APIs, OpenMBEE/SysML v2 alignment, OGC/NIEM-compatible data exchange where applicable |
| AI/ML | Model cards for all ML; human-on-the-loop for safety-relevant predictions; drift monitoring; MLOps pipeline with approval gates |
| Modularity | All pillars independently deployable and licenseable (each must stand alone commercially) |
| Auditability | Every model version, test result, and access decision reconstructable |

---

## 9. AI/ML Services

1. **Generative design assistant** — requirement-traceable design space exploration with cost constraints (Pillars A/H)
2. **CMC process drift & quality prediction** (B-2)
3. **Telemetry anomaly detection** (C-2)
4. **Threat reconstruction** — fusion of multi-source observations into updated threat twins with confidence intervals (F-1)
5. **Engagement outcome prediction** — surrogate models accelerating F-2 Monte Carlo
6. **Test campaign optimization** — active learning selecting the next most-informative test (G)
7. **Skills gap forecasting** — workforce demand modeling (E-4)

Governance: all models carry provenance, validation history, applicability limits; safety-relevant outputs require human approval.

---

## 10. Security & Compliance Architecture

- **Deployment pattern:** GovCloud IL5 enclave + on-prem IL6 annex (classified threat data, fire-control data) + edge nodes at factories/ranges
- **Cross-domain:** ICAP-class guard services for sanitized extract generation (academic sandbox)
- **Program protection:** PPP (Program Protection Plan) artifacts generated automatically from data lineage
- **Supply chain:** NGSH itself developed under CMMC L2+ with SBOM for all components

---

## 11. Development Approach and Phasing

| Phase | Vehicle | Scope | Duration |
|---|---|---|---|
| 1 | WISH-type OTA | Pillar E MVP: digital-twin training for CMC mfg & systems test at 2–3 institutions + 1 Navy lab | 12–18 mo |
| 2 | DASH-MOT/HAMTC-type OTA | Pillars B+C: CMC process intelligence + test data platform, integrated with Phase 1 training | 12–24 mo |
| 3 | SHY RNI response | Pillars D+H: surge simulation, supply visibility, family-of-systems configuration engine | 18–30 mo |
| 4 | MDA engagement (Project Maverick ecosystem) | Pillar F/G: kill-chain simulator + virtual range; validation event: 2027 Maverick flight test | 18–30 mo |
| 5 | 26-07-type RFS | Full stack for next-gen prototype integration & flight demo | 24–36 mo |
| 6 | Golden Dome / GPI transition | Test & integration environment of record for early-2030s IOC | 2030s |
| 7 | Reusable hypersonic aircraft | Incumbent test/M&S/workforce infrastructure | 2030s |

Each phase yields a standalone, revenue-capable product (risk management for OTA work).

---

## 12. Measures of Vital-ness (KPIs)

| National-security outcome | Metric |
|---|---|
| Compress counter-hypersonic kill chain | Simulated time detection→custody per architecture; reduction % vs. baseline |
| Stretch defense dollars | Virtual engagements per flight test consumed (target ≥ 10×) |
| Deter by capacity | Verified surge production rate; cost-per-effect trajectory |
| Sustain under attack | Time-to-reconstitute for critical nodes |
| Workforce guarantee | Cleared-skills supply vs. classified demand gap, by region/trade |
| Development speed | Design-iterate cycles per flight test; model fidelity improvement per campaign |

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Defense-side budgets thin ($200.6M vs $3.9B) | Pillar F wins on leverage (multiplies existing sensor/effector value), not on competing with hardware primes |
| Prime data-sharing resistance | Open APIs, complement posture, teaming agreements; Pillar E (least sensitive data) as entry wedge |
| Classification/CUI friction slows delivery | CMMC/IL5 from day one; edge/annex architecture; sanitized extract pipelines pre-built |
| Threat-model data access is chokepoint | SCI annex architecture early; collateral handling procedures; partnerships with intel community integrators |
| MDA/SDA integration politics | Explicit non-replacement posture for BMC3; sensor/prime partner on teaming list |
| Budget cyclicality | Workforce + industrial-base framings (WISH/SHY) are durable across budget cycles |

---

## 14. Teaming Strategy

- **CMC credibility:** DASH-MOT ecosystem (e.g., Fiber Materials Inc.)
- **Test capability:** HAMTC performers; national range operators
- **Sensors/BMC3:** at least one sensor or prime partner (MDA credibility)
- **Academia:** UCAH-university consortium members for WISH
- **Manufacturing analytics:** commercial MES/industrial-AI firm
- **Integration (self):** NGSH is the ecosystem integrator — "industrial base software," not weapons

---

## 15. Document Control

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-14 | Initial preliminary design |

*Next artifacts: Capability statement for MDA counter-hypersonic community; Pillar F technical architecture deep-dive; teaming partner target list; one-page concept paper.*
