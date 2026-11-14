"""Documentation consistency.

Documentation drifts silently: a type is renamed in the contract layer, the
architecture document keeps the old name, and the two disagree for a year
before anyone notices. These tests make the drift a build failure.

The checks are deliberately about *referential* consistency — that the
documents name the things that actually exist — rather than about prose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"
DOCS = REPO_ROOT / "docs"

pytestmark = pytest.mark.integration


def _all_docs() -> list[Path]:
    if not DOCS.exists():
        return []
    return sorted(p for p in DOCS.rglob("*.md"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads((CONTRACTS / "ontology" / "registry.json").read_text())


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads((CONTRACTS / "events" / "catalog.json").read_text())


def test_documentation_exists() -> None:
    assert DOCS.exists(), "docs/ must exist"
    assert list(DOCS.rglob("*.md")), "docs/ must contain markdown"


def test_every_adr_has_the_required_sections() -> None:
    """Each ADR must state its decision, its alternatives and its consequences."""
    required = ["## Status", "## Context", "## Decision", "## Alternatives Considered", "## Consequences"]
    adr_files = sorted((DOCS / "adr").glob("ADR-*.md"))
    assert len(adr_files) >= 8, "the plan commits to eight ADRs"

    for path in adr_files:
        text = _read(path)
        for section in required:
            assert section in text, f"{path.name} is missing the '{section}' section"


def test_adrs_have_unique_numbers() -> None:
    numbers = []
    for path in sorted((DOCS / "adr").glob("ADR-*.md")):
        match = re.match(r"ADR-(\d{4})-", path.name)
        assert match, f"{path.name} does not follow the ADR-NNNN-slug.md convention"
        numbers.append(int(match.group(1)))
    assert len(numbers) == len(set(numbers)), "duplicate ADR numbers"


def test_ontology_document_names_every_entity_type(registry) -> None:
    text = _read(DOCS / "architecture" / "02-ontology-model.md")
    missing = [entry["type"] for entry in registry["entities"] if entry["type"] not in text]
    assert not missing, f"the ontology architecture document omits entity types: {missing}"


def test_ontology_document_names_every_relation_type(registry) -> None:
    text = _read(DOCS / "architecture" / "02-ontology-model.md")
    missing = [entry["type"] for entry in registry["relations"] if entry["type"] not in text]
    assert not missing, f"the ontology architecture document omits relation types: {missing}"


def test_ontology_document_names_every_constraint(registry) -> None:
    text = _read(DOCS / "architecture" / "02-ontology-model.md")
    missing = [constraint["id"] for constraint in registry["constraints"] if constraint["id"] not in text]
    assert not missing, f"the ontology architecture document omits constraints: {missing}"


def test_foundation_services_document_names_every_event_type(catalog) -> None:
    text = _read(DOCS / "architecture" / "03-foundation-services.md")
    missing = [entry["eventType"] for entry in catalog["events"] if entry["eventType"] not in text]
    assert not missing, f"the services architecture document omits event types: {missing}"


def test_no_document_names_a_type_that_does_not_exist(registry) -> None:
    """A document must not reference an entity type the ontology does not define."""
    known = {entry["type"] for entry in registry["entities"]}
    known |= {entry["type"] for entry in registry["relations"]}
    known |= {
        "CUI",
        "CUI//REL",
        "CUI//FOUO",
        "RESTRICTED",
        "SECRET",
        "TOP SECRET",
        "UNCLASSIFIED",
        "Pillar A",
        "Pillar B",
        "Pillar C",
        "Pillar D",
        "Pillar E",
        "Pillar F",
        "Pillar G",
        "Pillar H",
    }

    pattern = re.compile(
        r"\b(?:Requirement|Part|Material|ProcessPlan|ProcessRun|TestArticle|"
        r"TestCampaign|TestResult|Interface|Model|ThreatSystem|ThreatObservation|"
        r"EngagementScenario|Supplier|PartProvenance|Skill|Credential|Person|"
        r"Facility|RangeSlot|System|Variant|Subsystem)\b"
    )

    for path in _all_docs():
        for match in pattern.finditer(_read(path)):
            token = match.group(0)
            assert token in known, f"{path.relative_to(REPO_ROOT)} references unknown ontology type {token!r}"


def test_development_plan_covers_every_increment() -> None:
    text = _read(REPO_ROOT / "NGSH_Development_Plan.md")
    for number in range(6):
        assert f"Increment {number}" in text, f"the development plan omits Increment {number}"


def test_development_plan_references_every_adr() -> None:
    text = _read(REPO_ROOT / "NGSH_Development_Plan.md")
    for path in sorted((DOCS / "adr").glob("ADR-*.md")):
        number = path.name.split("-")[1]
        assert number in text, f"the development plan does not reference ADR-{number}"


def test_plan_and_psdd_agree_on_capability_ids() -> None:
    """The plan may not invent capability identifiers that the PSDD does not define."""
    psdd = _read(REPO_ROOT / "NGSH_Preliminary_Software_Design_Document.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    psdd_ids = set(re.findall(r"\b([A-H]-[1-9])\b", psdd))
    plan_ids = set(re.findall(r"\b([A-H]-[1-9])\b", plan))

    invented = plan_ids - psdd_ids
    assert not invented, f"the plan references capability ids absent from the PSDD: {sorted(invented)}"


def test_plan_references_real_psdd_sections() -> None:
    """Section references into the PSDD must point at sections that exist."""
    psdd = _read(REPO_ROOT / "NGSH_Preliminary_Software_Design_Document.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    referenced = set(re.findall(r"PSDD §(\d+(?:\.\d+)?)", plan))
    assert referenced, "the plan must cite the PSDD"

    for section in referenced:
        major = section.split(".")[0]
        assert re.search(rf"^## {major}\.", psdd, re.MULTILINE), (
            f"the plan cites PSDD §{section}, but section {major} does not exist"
        )


def test_readme_ports_match_the_deployment_manifests() -> None:
    """Ports quoted in the README must match the deployed services."""
    readme = _read(REPO_ROOT / "README.md")
    compose_path = REPO_ROOT / "deploy" / "compose" / "docker-compose.yml"
    if not compose_path.exists():
        pytest.skip("the compose topology is not present")

    compose = _read(compose_path)

    for service, port in (
        ("ontology", 8081),
        ("fabric", 8082),
        ("policy", 8083),
        ("audit", 8084),
        ("thread", 8085),
        ("ingest", 8086),
    ):
        assert f"| {service} | {port} |" in readme, (
            f"the README's service table does not state {service} on port {port}"
        )
        assert f'"{port}"' in compose, f"the compose topology does not publish {service} on port {port}"


def test_service_health_endpoints_are_documented() -> None:
    """Every service exposes the same health surface, and the docs say so."""
    readme = _read(REPO_ROOT / "README.md")
    assert "/healthz" in readme
    assert "/readyz" in readme


def test_roadmap_summary_matches_the_work_packages() -> None:
    """The increment summary must be derived from the work packages.

    A hand-maintained summary drifts from the detail it summarises, and a
    plan whose arithmetic does not reconcile is a plan nobody trusts.
    """
    roadmap = _read(DOCS / "roadmap" / "work-packages.md")

    blocks = re.split(r"\n### ", roadmap)
    per_increment: dict[int, dict[str, int]] = {}
    for block in blocks[1:]:
        head = block.split("\n", 1)[0]
        identifier = re.match(r"WP-(\d+)\.", head)
        size = re.search(r"\*\*Size\*\*\s*\|\s*(\d+)\s*EW", block)
        if not (identifier and size):
            continue
        increment = int(identifier.group(1))
        entry = per_increment.setdefault(increment, {"wps": 0, "ew": 0})
        entry["wps"] += 1
        entry["ew"] += int(size.group(1))

    assert per_increment, "no work packages found in the roadmap"

    # Every increment in the summary table must state the derived totals.
    for increment, entry in per_increment.items():
        row = re.search(rf"\| \*\*{increment}\*\* \| (\d+) \| ([\d,]+) \|", roadmap)
        assert row, f"the summary table has no row for increment {increment}"
        stated_wps = int(row.group(1))
        stated_ew = int(row.group(2).replace(",", ""))
        assert stated_wps == entry["wps"], (
            f"increment {increment} states {stated_wps} work packages but the detail defines {entry['wps']}"
        )
        assert stated_ew == entry["ew"], (
            f"increment {increment} states {stated_ew} engineer-weeks but the detail sums to {entry['ew']}"
        )

    total_row = re.search(r"\| \*\*Total\*\* \| \*\*(\d+)\*\* \| \*\*([\d,]+)\*\*", roadmap)
    assert total_row, "the summary table has no total row"
    assert int(total_row.group(1)) == sum(e["wps"] for e in per_increment.values())
    assert int(total_row.group(2).replace(",", "")) == sum(e["ew"] for e in per_increment.values())


def test_the_plan_and_the_roadmap_agree_on_effort() -> None:
    """The plan must not quote totals the roadmap contradicts."""
    roadmap = _read(DOCS / "roadmap" / "work-packages.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    total = re.search(r"Total programme effort is \*\*([\d,]+) engineer-weeks\*\*", roadmap)
    assert total, "the roadmap does not state the total programme effort"
    stated = total.group(1)

    assert stated in plan, (
        f"the plan does not quote the roadmap's total programme effort of {stated} engineer-weeks"
    )


def test_plan_risk_ids_exist_in_the_register() -> None:
    """A risk id the plan cites must exist in the register, with the same meaning."""
    register = _read(DOCS / "risk-register.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    register_ids = set(re.findall(r"\bR-\d{2}\b", register))
    plan_ids = set(re.findall(r"\bR-\d{2}\b", plan))

    unknown = plan_ids - register_ids
    assert not unknown, f"the plan cites risk ids absent from the register: {sorted(unknown)}"


def test_plan_risk_titles_match_the_register() -> None:
    """A risk id in the plan must carry the same title as in the register."""
    register = _read(DOCS / "risk-register.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    register_titles = {
        match.group(1): match.group(2).strip()
        for match in re.finditer(r"^### (R-\d{2}) — (.+)$", register, re.MULTILINE)
    }
    assert register_titles, "no risks found in the register"

    # The plan's risk table rows carry the risk id and the risk name.
    for match in re.finditer(r"^\| \d+ \| (R-\d{2}) \| ([^|]+) \|", plan, re.MULTILINE):
        risk_id, title = match.group(1), match.group(2).strip()
        assert risk_id in register_titles, f"{risk_id} is not in the register"
        expected = register_titles[risk_id].lower()
        actual = title.lower().rstrip(".")
        assert actual.startswith(expected[:18]) or expected.startswith(actual[:18]), (
            f"the plan calls {risk_id} {title!r} but the register calls it {register_titles[risk_id]!r}"
        )


def test_increment_titles_match_the_roadmap() -> None:
    """The plan and the roadmap must name the increments the same way."""
    roadmap = _read(DOCS / "roadmap" / "increments.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    roadmap_titles = {
        int(match.group(1)): match.group(2).strip()
        for match in re.finditer(r"^## \d+\. Increment (\d+) — (.+)$", roadmap, re.MULTILINE)
    }
    assert roadmap_titles, "no increments found in the roadmap"

    plan_titles = {
        int(match.group(1)): match.group(2).strip()
        for match in re.finditer(r"^#### Increment (\d+) — (.+)$", plan, re.MULTILINE)
    }
    assert plan_titles, "no increments found in the plan"

    for number, title in roadmap_titles.items():
        assert number in plan_titles, f"the plan omits increment {number}"
        assert plan_titles[number].lower() == title.lower(), (
            f"increment {number} is called {plan_titles[number]!r} in the plan and {title!r} in the roadmap"
        )


def test_pod_types_agree_between_the_plan_and_the_staffing_doc() -> None:
    """A pod named in the plan must be a pod type the staffing doc defines."""
    staffing = _read(DOCS / "staffing.md")
    plan = _read(REPO_ROOT / "NGSH_Development_Plan.md")

    # Pod types are declared in the staffing document's type table.
    defined = set(re.findall(r"^\| \*\*(.+?)\*\* \| ", staffing, re.MULTILINE))
    assert defined, "no pod types found in the staffing document"

    # Scope the extraction to the reference-organisation tables; the plan has
    # other tables whose rows are not pod names.
    section = re.search(r"### 5\.3 Reference organisations(.*?)### 5\.4", plan, re.DOTALL)
    assert section, "the plan has no reference-organisation section"
    named = set(
        re.findall(r"^\| \*{0,2}([A-Z][A-Za-z /&]+?)\*{0,2} \| \d+ \|$", section.group(1), re.MULTILINE)
    )
    assert named, "no pod names found in the plan"

    def _normalise(value: str) -> str:
        return value.lower().replace(" and ", " & ").replace(" / ", "/").strip()

    for pod in named:
        assert any(
            _normalise(pod) in _normalise(candidate) or _normalise(candidate) in _normalise(pod)
            for candidate in defined
        ), (
            f"the plan uses a pod type {pod!r} that the staffing document does not "
            f"define; defined types are {sorted(defined)}"
        )
