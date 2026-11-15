"""Projections and programme measures: search, lakehouse, KPIs, interfaces."""

from __future__ import annotations

from ngsh_core.analytics import programme_kpis
from ngsh_core.integration import (
    INTERFACE_REGISTER,
    interface_check,
    interface_register_report,
    outbound_allowed,
)
from ngsh_core.lakehouse import dataset_catalog, dataset_lineage
from ngsh_core.search import score_entity, search, tokenise

ENTITIES = [
    {
        "id": "PART:NSN-4472",
        "type": "Part",
        "attributes": {"name": "TPS ablative panel", "partNumber": "NSN-4472"},
        "classification": {"level": "CUI"},
    },
    {
        "id": "REQ:1",
        "type": "Requirement",
        "attributes": {"statement": "The TPS shall survive 2200 K for 300 s."},
        "classification": {"level": "CUI"},
    },
    {
        "id": "SYS:1",
        "type": "System",
        "attributes": {"name": "Boost vehicle"},
        "classification": {"level": "UNCLASSIFIED"},
    },
]


def test_search_ranks_an_exact_identifier_first():
    result = search(ENTITIES, "PART:NSN-4472")
    assert result["results"][0]["id"] == "PART:NSN-4472"
    assert "id" in result["results"][0]["matchedFields"]


def test_search_requires_every_term_to_match():
    result = search(ENTITIES, "TPS 2200")
    assert [row["id"] for row in result["results"]] == ["REQ:1"]


def test_search_explains_a_missing_match_with_an_empty_result():
    result = search(ENTITIES, "submarine")
    assert result["count"] == 0
    assert result["totalMatches"] == 0


def test_tokenise_keeps_identifiers_whole():
    assert tokenise("PART:NSN-4472 and TPS") == ["part:nsn-4472", "and", "tps"]


def test_score_entity_returns_zero_when_one_term_is_absent():
    score, fields = score_entity(ENTITIES[2], ["system", "submarine"])
    assert score == 0
    assert fields == []


def _result(result_id: str, uri: str, snapshot: dict | None, **extra) -> dict:
    attributes = {"dataSetUris": [uri], "configurationSnapshot": snapshot, **extra}
    return {"id": result_id, "type": "TestResult", "attributes": attributes, "classification": {"level": "CUI"}}


def test_dataset_catalogue_marks_an_unconfigured_dataset_incomplete():
    catalog = dataset_catalog(
        [
            _result("TR:1", "s3://range/run1.parquet", {"variantId": "VAR:1", "baselineId": "BL:1"}),
            _result("TR:2", "s3://range/run2.tdms", {"variantId": "VAR:1"}),
        ]
    )
    assert catalog["summary"]["datasetCount"] == 2
    assert catalog["summary"]["configuredCount"] == 1
    assert catalog["complete"] is False
    incomplete = [row for row in catalog["datasets"] if not row["configured"]]
    assert incomplete[0]["unconfiguredResults"][0]["missing"] == ["baselineId"]


def test_dataset_lineage_names_every_result_and_configuration():
    results = [
        _result(
            "TR:1",
            "s3://range/run1.parquet",
            {"variantId": "VAR:1", "baselineId": "BL:1"},
            campaignId="TC:1",
            outcome="PASS",
        )
    ]
    catalog = dataset_catalog(results)
    dataset_id = catalog["datasets"][0]["datasetId"]
    lineage = dataset_lineage("s3://range/run1.parquet", results)
    assert lineage["datasetId"] == dataset_id
    assert lineage["lineage"][0]["configurationSnapshot"]["baselineId"] == "BL:1"
    assert lineage["complete"] is True


AS_OF = "2026-03-01T00:00:00+00:00"


def test_kpis_report_every_measure_and_name_the_unavailable_ones():
    report = programme_kpis(
        as_of=AS_OF,
        scenarios=[],
        test_results=[],
        campaigns=[],
        models=[],
        persons=[],
        credentials=[],
        skills=[],
    )
    identifiers = {row["id"] for row in report["kpis"]}
    assert identifiers == {
        "kill-chain-latency",
        "virtual-to-physical",
        "surge-readiness",
        "time-to-reconstitute",
        "workforce-gap",
        "design-iterate-cycles",
        "model-fidelity-improvement",
    }
    assert report["summary"]["computedCount"] == 0
    for row in report["kpis"]:
        assert row["status"] == "NOT_COMPUTED"
        assert row["note"]


def test_virtual_to_physical_ratio_is_measured_against_real_flight_tests():
    report = programme_kpis(
        as_of=AS_OF,
        scenarios=[
            {
                "id": "ESC:1",
                "attributes": {"resultsSummary": {"runs": 20_000}},
            }
        ],
        test_results=[
            {
                "id": "TR:1",
                "attributes": {"testMethod": "FLIGHT_TEST", "outcome": "PASS"},
            }
        ],
        campaigns=[],
        models=[],
        persons=[],
        credentials=[],
        skills=[],
    )
    kpi = next(row for row in report["kpis"] if row["id"] == "virtual-to-physical")
    assert kpi["value"] == 20_000
    assert kpi["status"] == "MEETS"


def test_a_kill_chain_reduction_is_reported_against_its_baseline():
    report = programme_kpis(
        as_of=AS_OF,
        scenarios=[
            {
                "id": "ESC:BASE",
                "attributes": {
                    "baseline": True,
                    "timeline": {"detectionToCustodySeconds": 100.0},
                },
            },
            {
                "id": "ESC:NEW",
                "attributes": {"timeline": {"detectionToCustodySeconds": 40.0}},
            },
        ],
        test_results=[],
        campaigns=[],
        models=[],
        persons=[],
        credentials=[],
        skills=[],
    )
    kpi = next(row for row in report["kpis"] if row["id"] == "kill-chain-latency")
    assert kpi["value"] == 40.0
    assert kpi["detail"]["meanBaselineSeconds"] == 100.0
    assert kpi["detail"]["reductionPct"] == 60.0


def test_the_interface_register_is_complete_and_marks_if3_inbound_only():
    report = interface_register_report()
    assert report["complete"] is True
    assert report["count"] == 7
    assert report["missing"] == []
    assert report["inboundOnly"] == ["IF-3"]
    assert outbound_allowed("IF-3") is False
    assert outbound_allowed("IF-2") is True


def test_an_incomplete_register_is_reported_as_incomplete():
    entries = [entry for entry in INTERFACE_REGISTER if entry["id"] != "IF-6"]
    report = interface_register_report(entries)
    assert report["complete"] is False
    assert report["missing"] == ["IF-6"]


def test_a_known_interface_checks_usable_and_names_its_boundary():
    check = interface_check("IF-3")
    assert check["usable"] is True
    assert check["outboundBlocked"] is True
    assert check["problems"] == []
