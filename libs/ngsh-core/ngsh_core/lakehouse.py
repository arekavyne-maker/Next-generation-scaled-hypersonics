"""Lakehouse dataset catalogue: the test data lake, with its configuration context.

Pillar C's C-1 is not "a bucket of files". It is ground, tunnel, sled and flight
data that can be traced to the variant, lot and software build that produced
it. This module builds that catalogue as a projection over admitted test
results and their dataset URIs, so a dataset that loses its configuration
context is visible as a defect rather than silently joined to the wrong build.

Nothing here is authoritative: the catalogue is derived from the thread and can
be rebuilt. The dataset identifiers are content addresses over the source
records, so the same evidence produces the same catalogue entry.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .classification import ClassificationLevel, max_level, parse_level
from .errors import ValidationError

#: Formats the catalogue recognises. An unknown extension is reported as
#: ``UNKNOWN`` rather than guessed, because a guessed format is a pipeline bug
#: waiting for the first read.
FORMAT_BY_EXTENSION = {
    ".csv": "CSV",
    ".json": "JSON",
    ".parquet": "PARQUET",
    ".avro": "AVRO",
    ".hdf5": "HDF5",
    ".h5": "HDF5",
    ".tdms": "TDMS",
    ".bag": "ROS_BAG",
    ".mcap": "MCAP",
    ".zip": "ARCHIVE",
    ".tar": "ARCHIVE",
    ".gz": "ARCHIVE",
}

REQUIRED_CONFIGURATION_KEYS = ("variantId", "baselineId")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def dataset_format(uri: str) -> str:
    lowered = (uri or "").lower()
    for extension, label in FORMAT_BY_EXTENSION.items():
        if lowered.endswith(extension):
            return label
    return "UNKNOWN"


def _attributes(entity: dict[str, Any]) -> dict[str, Any]:
    return entity.get("attributes") or {}


def dataset_catalog(
    results: list[dict[str, Any]],
    *,
    batches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the dataset catalogue from test results and ingest batches.

    A dataset is *configured* only when every result that references it carries
    a configuration snapshot naming a variant and a baseline. One unconfigured
    reference is enough to mark the dataset incomplete: data whose build is
    ambiguous cannot be used as evidence, and the catalogue must say so.
    """
    entries: dict[str, dict[str, Any]] = {}

    for result in results:
        attributes = _attributes(result)
        for uri in attributes.get("dataSetUris") or []:
            if not isinstance(uri, str) or not uri:
                continue
            entry = entries.setdefault(
                uri,
                {
                    "uri": uri,
                    "format": dataset_format(uri),
                    "referencedBy": [],
                    "campaigns": set(),
                    "variants": set(),
                    "baselines": set(),
                    "softwareBuilds": set(),
                    "modelVersionIds": set(),
                    "outcomes": {},
                    "classifications": [],
                    "unconfiguredResults": [],
                    "ingestBatches": [],
                },
            )
            result_id = result.get("id")
            entry["referencedBy"].append(result_id)
            if attributes.get("campaignId"):
                entry["campaigns"].add(attributes["campaignId"])
            snapshot = attributes.get("configurationSnapshot") or {}
            if isinstance(snapshot, dict) and snapshot:
                for key, bucket in (
                    ("variantId", "variants"),
                    ("baselineId", "baselines"),
                    ("softwareBuild", "softwareBuilds"),
                ):
                    if snapshot.get(key):
                        entry[bucket].add(str(snapshot[key]))
                missing = [
                    key for key in REQUIRED_CONFIGURATION_KEYS if not snapshot.get(key)
                ]
                if missing:
                    entry["unconfiguredResults"].append(
                        {"resultId": result_id, "missing": missing}
                    )
            else:
                entry["unconfiguredResults"].append(
                    {"resultId": result_id, "missing": list(REQUIRED_CONFIGURATION_KEYS)}
                )
            for model_id in attributes.get("modelVersionIds") or []:
                entry["modelVersionIds"].add(str(model_id))
            outcome = attributes.get("outcome")
            if outcome:
                entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + 1
            entry["classifications"].append(
                (result.get("classification") or {}).get("level") or "UNCLASSIFIED"
            )

    for batch in batches or []:
        uri = batch.get("datasetUri") or batch.get("uri")
        if not uri or uri not in entries:
            continue
        entries[uri]["ingestBatches"].append(
            {
                "batchId": batch.get("batchId"),
                "digest": batch.get("digest"),
                "recordCount": batch.get("recordCount"),
                "classification": batch.get("classification"),
            }
        )

    catalogue: list[dict[str, Any]] = []
    for uri, entry in sorted(entries.items()):
        source_ids = sorted({str(item) for item in entry["referencedBy"] if item})
        digest = _digest({"uri": uri, "sources": source_ids})
        classification = max_level(*entry["classifications"]).label if entry["classifications"] else "UNCLASSIFIED"
        catalogue.append(
            {
                "datasetId": f"DS:{digest[:26].upper()}",
                "uri": uri,
                "format": entry["format"],
                "classification": classification,
                "restricted": parse_level(classification) >= ClassificationLevel.RESTRICTED,
                "referencedBy": source_ids,
                "referenceCount": len(source_ids),
                "campaigns": sorted(entry["campaigns"]),
                "configuration": {
                    "variants": sorted(entry["variants"]),
                    "baselines": sorted(entry["baselines"]),
                    "softwareBuilds": sorted(entry["softwareBuilds"]),
                },
                "configured": not entry["unconfiguredResults"],
                "unconfiguredResults": entry["unconfiguredResults"],
                "modelVersionIds": sorted(entry["modelVersionIds"]),
                "outcomes": dict(sorted(entry["outcomes"].items())),
                "ingestBatches": entry["ingestBatches"],
                "contentDigest": digest,
            }
        )

    total = len(catalogue)
    configured = sum(1 for entry in catalogue if entry["configured"])
    return {
        "datasets": catalogue,
        "summary": {
            "datasetCount": total,
            "configuredCount": configured,
            "configurationCoverage": round(configured / total, 4) if total else 0.0,
            "unconfiguredCount": total - configured,
            "campaignCount": len(
                {campaign for entry in catalogue for campaign in entry["campaigns"]}
            ),
            "formats": sorted({entry["format"] for entry in catalogue}),
        },
        "complete": total > 0 and configured == total,
    }


def dataset_lineage(uri: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Every result, configuration and model behind one dataset URI."""
    if not isinstance(uri, str) or not uri:
        raise ValidationError("'uri' is required")
    matched = [
        result
        for result in results
        if uri in (_attributes(result).get("dataSetUris") or [])
    ]
    if not matched:
        raise ValidationError(f"no test result references dataset {uri!r}")

    lineage = []
    for result in sorted(matched, key=lambda item: str(item.get("id"))):
        attributes = _attributes(result)
        lineage.append(
            {
                "resultId": result.get("id"),
                "campaignId": attributes.get("campaignId"),
                "outcome": attributes.get("outcome"),
                "configurationSnapshot": attributes.get("configurationSnapshot"),
                "modelVersionIds": attributes.get("modelVersionIds") or [],
                "classification": (result.get("classification") or {}).get("level"),
            }
        )
    digest = _digest({"uri": uri, "sources": [row["resultId"] for row in lineage]})
    return {
        "datasetId": f"DS:{digest[:26].upper()}",
        "uri": uri,
        "format": dataset_format(uri),
        "lineage": lineage,
        "resultCount": len(lineage),
        "complete": all(
            isinstance(row["configurationSnapshot"], dict) and row["configurationSnapshot"]
            for row in lineage
        ),
    }
