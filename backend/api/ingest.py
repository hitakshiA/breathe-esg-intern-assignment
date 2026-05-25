"""
Ingestion orchestration: file → IngestionBatch + RawRow + Activity + ActivityEmission.

Public entry point: `ingest_file(organization, source_type, file_obj, file_name, user)`.
"""
from __future__ import annotations

import hashlib

from django.db import transaction

from . import audit
from .calc import calculate_for_activity
from .models import Activity, Facility, IngestionBatch, RawRow
from .parsers import sap as sap_parser
from .parsers import travel as travel_parser
from .parsers import utility as utility_parser

PARSER_REGISTRY = {
    IngestionBatch.SOURCE_SAP_FUEL: sap_parser.parse,
    IngestionBatch.SOURCE_UTILITY_ELEC: utility_parser.parse,
    IngestionBatch.SOURCE_TRAVEL: travel_parser.parse,
}


def ingest_file(organization, source_type: str, file_obj, file_name: str, user=None) -> IngestionBatch:
    file_obj.seek(0)
    raw_bytes = file_obj.read()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    file_obj.seek(0)

    batch = IngestionBatch.objects.create(
        organization=organization,
        source_type=source_type,
        file_name=file_name,
        file=None,  # we don't store the file on disk in V1; SHA-256 is enough
        file_sha256=file_sha256,
        uploaded_by=user,
        status=IngestionBatch.STATUS_PROCESSING,
    )
    audit.record(organization, batch, "ingest.start",
                 after={"source_type": source_type, "file_name": file_name})

    parser = PARSER_REGISTRY.get(source_type)
    if not parser:
        batch.status = IngestionBatch.STATUS_FAILED
        batch.error_summary = [{"code": "unsupported", "message": f"No parser for {source_type}"}]
        batch.save()
        return batch

    rows_seen = 0
    rows_ok = 0
    rows_err = 0
    rows_dup = 0
    error_summary: list[dict] = []

    with transaction.atomic():
        for row_result in parser(file_obj):
            rows_seen += 1
            row_hash = RawRow.hash_payload(row_result["raw"])

            # Dedup: if we've already ingested this exact payload for this org, skip.
            if RawRow.objects.filter(organization=organization, row_sha256=row_hash).exists():
                rows_dup += 1
                continue

            raw = RawRow.objects.create(
                organization=organization,
                batch=batch,
                row_number=row_result["row_number"],
                raw_data=row_result["raw"],
                row_sha256=row_hash,
                parse_status=row_result["status"],
                parse_errors=row_result["errors"],
            )
            if row_result["status"] == "error" or row_result["record"] is None:
                if row_result["status"] == "error":
                    rows_err += 1
                    error_summary.append({
                        "row": row_result["row_number"],
                        "errors": row_result["errors"],
                    })
                continue

            rec = row_result["record"]
            facility = _resolve_facility(organization, source_type, rec)
            activity = Activity.objects.create(
                organization=organization,
                raw_row=raw,
                facility=facility,
                activity_type=rec["activity_type"],
                scope=rec["scope"],
                scope3_category=rec.get("scope3_category"),
                period_start=rec["period_start"],
                period_end=rec["period_end"],
                quantity_original=rec["quantity_original"],
                unit_original=rec["unit_original"],
                quantity_normalized=rec["quantity_normalized"],
                unit_normalized=rec["unit_normalized"],
                fuel_or_energy_type=rec.get("fuel_or_energy_type", ""),
                cabin_class=rec.get("cabin_class", ""),
                origin_iata=rec.get("origin_iata", ""),
                destination_iata=rec.get("destination_iata", ""),
                distance_km=rec.get("distance_km"),
                supplier_name=rec.get("supplier_name", ""),
                description=rec.get("description", ""),
                data_quality_tier=rec.get("data_quality_tier", 1),
                flags=[{"code": "parser", "message": m, "severity": "warning"}
                       for m in row_result["errors"]],
            )
            calculate_for_activity(activity)
            rows_ok += 1

    batch.row_count = rows_seen
    batch.ok_count = rows_ok
    batch.error_count = rows_err
    batch.duplicate_count = rows_dup
    batch.error_summary = error_summary[:50]  # cap for sanity
    batch.status = (
        IngestionBatch.STATUS_SUCCEEDED if rows_err == 0
        else IngestionBatch.STATUS_SUCCEEDED_WITH_ERRORS
    )
    batch.save()
    audit.record(organization, batch, "ingest.complete",
                 after={"rows": rows_seen, "ok": rows_ok, "err": rows_err, "dup": rows_dup})
    return batch


def _resolve_facility(organization, source_type, record) -> Facility | None:
    if source_type == IngestionBatch.SOURCE_SAP_FUEL:
        code = record.get("plant_code", "")
        if code:
            for f in organization.facilities.all():
                if code in f.plant_code_list():
                    return f
    if source_type == IngestionBatch.SOURCE_UTILITY_ELEC:
        z = record.get("service_zip", "")
        if z:
            # Match by postal code first; else by eGRID subregion
            f = organization.facilities.filter(postal_code=z).first()
            if f:
                return f
            sub = record.get("egrid_subregion", "")
            if sub:
                return organization.facilities.filter(egrid_subregion=sub).first()
    return None
