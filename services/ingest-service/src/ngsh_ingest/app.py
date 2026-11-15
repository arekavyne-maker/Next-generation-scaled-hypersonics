"""NGSH ingest service.

Bulk admission point for the data that does not arrive as structured
platform events: raw test telemetry, wind-tunnel and sled datasets,
manufacturing process records, instrument archives.

Two responsibilities:

**Admission with an accounting trail.** Every batch produces an
``ingest.batch.accepted`` event recording what arrived, how much, at what
classification, and with what digest. This is what makes the lineage
automatable end to end (PSDD §6.3) and what lets a CMMC assessor see where
a given dataset came from.

**Normalisation into the ontology.** Records that carry a recognised
``entityType`` are lifted into platform entities and published to the fabric
as ``entity.created`` events, so that ingested data joins the same digital
thread as everything else. The raw payload is preserved and referenced; it is
never discarded in favour of the normalised form.

Classification travels with the data. A batch is stamped at admission and the
stamp is carried into every entity derived from it, because a dataset that
arrives without a handling marking cannot be safely promoted later.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.blobstore import BlobStore
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import Actor, Classification, EventEnvelope
from ngsh_core.errors import ValidationError
from ngsh_core.ids import new_ulid
from ngsh_core.store import canonical_json, open_database

SERVICE_NAME = "ingest"
DESCRIPTION = (
    "Bulk admission of test, telemetry and manufacturing data into the NGSH "
    "fabric, with lineage, digest and classification accounted for."
)

router = APIRouter(prefix="/v1", tags=["ingest"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_payload(payload: str, fmt: str) -> list[dict[str, Any]]:
    """Parse a batch payload into records.

    Only the formats the platform actually ingests are supported. Anything
    else is rejected explicitly rather than silently coerced, because a
    mis-parsed telemetry file that produces plausible-looking numbers is
    worse than one that fails loudly.
    """
    normalized = fmt.strip().upper()
    if normalized in {"NDJSON", "JSONL"}:
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(payload.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"line {line_number} is not valid JSON: {exc}") from exc
        return records

    if normalized == "JSON":
        document = json.loads(payload)
        if isinstance(document, list):
            return [record for record in document if isinstance(record, dict)]
        if isinstance(document, dict):
            return [document]
        raise ValidationError("JSON payload must be an object or an array of objects")

    if normalized == "CSV":
        reader = csv.DictReader(io.StringIO(payload))
        return [dict(row) for row in reader]

    raise ValidationError(f"unsupported payload format {fmt!r}; supported formats are CSV, NDJSON and JSON")


def _build_entity(
    record: dict[str, Any],
    *,
    entity_type: str,
    tenant: str,
    program: str | None,
    classification: Classification,
    batch_id: str,
    id_prefix: str,
) -> dict[str, Any]:
    """Lift a raw record into a platform entity."""
    stamp = _utcnow().isoformat()
    attributes = {key: value for key, value in record.items() if not key.startswith("_")}

    entity_id = record.get("id") or f"{id_prefix}:{new_ulid()}"
    return {
        "id": entity_id,
        "type": entity_type,
        "tenant": tenant,
        "program": program,
        "version": 1,
        "classification": classification.model_dump(mode="json"),
        "createdAt": stamp,
        "updatedAt": stamp,
        "createdBy": "svc:ingest",
        "updatedBy": "svc:ingest",
        "provenance": {
            "source": f"ingest:{batch_id}",
            "method": "batch-lift",
            "observedAt": stamp,
        },
        "labels": {"ingestBatch": batch_id},
        "attributes": attributes,
    }


@router.post("/ingest", summary="Admit a batch of records")
async def ingest(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Admit a batch and publish the resulting events to the fabric."""
    settings: Settings = request.app.state.settings

    source = body.get("source")
    fmt = body.get("format", "NDJSON")
    payload = body.get("payload")
    if not source:
        raise ValidationError("a 'source' is required")
    if payload is None:
        raise ValidationError("a 'payload' is required")

    if isinstance(payload, list):
        records = [record for record in payload if isinstance(record, dict)]
        raw_bytes = canonical_json(payload).encode("utf-8")
    else:
        records = _parse_payload(payload, fmt)
        raw_bytes = str(payload).encode("utf-8")

    classification = Classification.model_validate(body.get("classification") or {"level": "CUI"})
    entity_type = body.get("entityType")
    batch_id = body.get("batchId") or f"BATCH:{new_ulid()}"

    digest = hashlib.sha256(raw_bytes).hexdigest()

    executor = request.app.state.executor
    stamp = _utcnow().isoformat()

    lifted: list[dict[str, Any]] = []
    rejected = 0
    rejection_reasons: list[str] = []
    if entity_type:
        registry = request.app.state.registry
        spec = registry.entity_type(entity_type)
        if spec is None:
            raise ValidationError(f"unknown entity type {entity_type!r}; check the ontology registry")
        for record in records:
            try:
                lifted.append(
                    _build_entity(
                        record,
                        entity_type=entity_type,
                        tenant=settings.tenant,
                        program=settings.program,
                        classification=classification,
                        batch_id=batch_id,
                        id_prefix=spec.idPrefix,
                    )
                )
            except Exception as exc:
                rejected += 1
                if len(rejection_reasons) < 5:
                    rejection_reasons.append(f"{type(exc).__name__}: {exc}")

    entity_ids = [entity["id"] for entity in lifted]

    executor.execute(
        "INSERT INTO ingest_batches (batch_id, source, format, classification, records_accepted, "
        "records_rejected, bytes_accepted, sha256, object_uri, entity_ids, created_at, body_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            batch_id,
            source,
            fmt,
            classification.level,
            len(lifted) if entity_type else len(records),
            rejected,
            len(raw_bytes),
            digest,
            body.get("objectUri"),
            canonical_json(entity_ids),
            stamp,
            canonical_json(
                {"source": source, "format": fmt, "classification": classification.model_dump(mode="json")}
            ),
        ),
    )

    published = await _publish(
        request,
        batch_id,
        source,
        fmt,
        digest,
        entity_ids,
        lifted,
        classification,
        len(records),
        rejected,
        len(raw_bytes),
    )

    return {
        "batchId": batch_id,
        "recordsAccepted": len(lifted) if entity_type else len(records),
        "recordsRejected": rejected,
        "rejectionReasons": rejection_reasons,
        "bytesAccepted": len(raw_bytes),
        "sha256": digest,
        "entityIds": entity_ids,
        "published": published,
    }


async def _publish(
    request: Request,
    batch_id: str,
    source: str,
    fmt: str,
    digest: str,
    entity_ids: list[str],
    lifted: list[dict[str, Any]],
    classification: Classification,
    record_count: int,
    rejected: int,
    byte_count: int,
) -> dict[str, Any]:
    """Publish the batch event and the lifted entities to the fabric."""
    fabric_url = request.app.state.settings.fabric_url
    actor = Actor(subjectId="svc:ingest", kind="service", clearance="SECRET", citizenship="US")

    batch_event = EventEnvelope(
        eventType="ingest.batch.accepted",
        aggregateType="IngestBatch",
        aggregateId=batch_id,
        sequence=1,
        tenant=request.app.state.settings.tenant,
        program=request.app.state.settings.program,
        actor=actor,
        classification=classification,
        payload={
            "batchId": batch_id,
            "source": source,
            "format": fmt,
            "recordsAccepted": record_count,
            "recordsRejected": rejected,
            "bytesAccepted": byte_count,
            "sha256": digest,
            "entityIds": entity_ids,
        },
    )

    events = [batch_event]
    for entity in lifted:
        events.append(
            EventEnvelope(
                eventType="entity.created",
                aggregateType=entity["type"],
                aggregateId=entity["id"],
                sequence=1,
                tenant=entity["tenant"],
                program=entity.get("program"),
                actor=actor,
                classification=classification,
                causationId=batch_event.eventId,
                correlationId=batch_id,
                payload={"entity": entity},
                idempotencyKey=f"{batch_id}:{entity['id']}",
            )
        )

    if not fabric_url:
        # Single-process development mode: append directly to the shared log.
        from ngsh_core.eventlog import EventLog

        log = EventLog(request.app.state.executor)
        outcomes = log.append_batch(events)
        return {
            "status": "appended",
            "accepted": sum(1 for outcome in outcomes if outcome.accepted),
            "rejected": sum(1 for outcome in outcomes if not outcome.accepted),
        }

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{fabric_url}/v1/events",
                json={"events": [e.to_logical_json() for e in events]},
            )
            if response.status_code >= 300:
                return {"status": "failed", "code": response.status_code, "detail": response.text[:400]}
            return {"status": "published", "detail": response.json()}
    except Exception as exc:
        return {"status": "failed", "reason": type(exc).__name__}


@router.get("/ingest/batches", summary="List ingestion batches")
async def list_batches(request: Request, limit: int = 50) -> dict[str, Any]:
    rows = request.app.state.executor.fetchall(
        "SELECT batch_id, source, format, classification, records_accepted, records_rejected, "
        "bytes_accepted, sha256, entity_ids, created_at FROM ingest_batches "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return {
        "batches": [
            {
                "batchId": row["batch_id"],
                "source": row["source"],
                "format": row["format"],
                "classification": row["classification"],
                "recordsAccepted": row["records_accepted"],
                "recordsRejected": row["records_rejected"],
                "bytesAccepted": row["bytes_accepted"],
                "sha256": row["sha256"],
                "entityIds": json.loads(row["entity_ids"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
    }


@router.get("/ingest/batches/{batch_id}", summary="Fetch one ingestion batch")
async def get_batch(request: Request, batch_id: str) -> dict[str, Any]:
    row = request.app.state.executor.fetchone("SELECT * FROM ingest_batches WHERE batch_id = ?", (batch_id,))
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": f"no batch {batch_id!r}"}},
        )
    result = dict(row)
    result["entityIds"] = json.loads(result.get("entity_ids") or "[]")
    result["body"] = json.loads(result.pop("body_json", "{}"))
    return result


@router.post("/lakehouse/objects", summary="Store a lakehouse object by content", status_code=201)
async def store_object(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Store bytes under their SHA-256 and return the addressable record.

    Content is supplied inline because the reference implementation has no
    object-store SDK (ADR-0003). A deployment adapter streams the same bytes to
    the accredited store; the ``ngsh-lake://<digest>`` URI and the verification
    contract do not change.
    """
    content = body.get("content")
    if not isinstance(content, str):
        raise ValidationError("'content' must be a string")
    encoding = str(body.get("encoding", "utf-8")).lower()
    if encoding in {"utf-8", "text", "utf8"}:
        raw = content.encode("utf-8")
    elif encoding == "base64":
        try:
            raw = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValidationError("'content' is not valid base64") from exc
    else:
        raise ValidationError("'encoding' must be 'utf-8' or 'base64'")
    if not raw:
        raise ValidationError("'content' must not be empty")

    metadata = body.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValidationError("'metadata' must be an object")
    media_type = body.get("mediaType") or "application/octet-stream"
    if not isinstance(media_type, str):
        raise ValidationError("'mediaType' must be a string")
    store: BlobStore = request.app.state.blobstore
    record = store.put(raw, media_type=media_type, metadata=metadata)
    return JSONResponse(status_code=201, content={"object": record})


@router.get("/lakehouse/objects", summary="List lakehouse objects")
async def list_objects(request: Request, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    records = request.app.state.blobstore.list(limit=limit)
    return {"objects": records, "count": len(records), "storage": "local-content-addressed"}


@router.get("/lakehouse/objects/{digest}", summary="Metadata for one lakehouse object")
async def object_metadata(request: Request, digest: str) -> dict[str, Any]:
    return {"object": request.app.state.blobstore.metadata(digest)}


@router.get("/lakehouse/objects/{digest}/content", summary="Fetch lakehouse object content")
async def object_content(request: Request, digest: str, encoding: str = Query("base64")) -> dict[str, Any]:
    content, record = request.app.state.blobstore.get(digest)
    normalized = encoding.lower()
    if normalized in {"utf-8", "text", "utf8"}:
        try:
            value = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError("the object is not UTF-8 text; request base64") from exc
    elif normalized == "base64":
        value = base64.b64encode(content).decode("ascii")
    else:
        raise ValidationError("'encoding' must be 'base64' or 'utf-8'")
    return {"digest": digest, "encoding": normalized, "content": value, "object": record}


@router.get("/lakehouse/objects/{digest}/verify", summary="Re-hash a lakehouse object")
async def verify_object(request: Request, digest: str) -> dict[str, Any]:
    return request.app.state.blobstore.verify(digest)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    executor = open_database(resolved.dsn)

    from ngsh_core.ontology import OntologyLoader

    registry = OntologyLoader(resolved.contracts_dir).load()

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "ingest", "description": "Bulk data admission and lineage."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.registry = registry
    app.state.blobstore = BlobStore(resolved.lakehouse_path)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
