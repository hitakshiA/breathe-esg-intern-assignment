"""
SAP MB51 (Material Document List) parser.

The MB51 flat-file export is what a facilities team realistically requests
from SAP BASIS in week 1. Production paths would use:

  - IDoc MBGMCR for goods-movements (ALE with BD21 change pointers)
  - OData via SAP Gateway exposing a CDS view
  - BAPI_PO_GETDETAIL for per-document lookups

We chose flat-file because:
  - IDoc/ALE setup is a 2-week engagement on the SAP side
  - OData/Gateway needs Basis team to activate the catalog service
  - Brief gives us 4 days

Locale quirks we handle:
  - Semicolon delimiter (default for German locale CSV exports from SAP GUI)
  - Decimal comma + dot thousands separator ("1.500,00" → 1500.00)
  - Dates in DD.MM.YYYY (German) or YYYYMMDD (SAP internal)
  - German column headers (we alias them)
  - Mixed German/English material descriptions

Movement type filtering (BWART):
  - 261 = Goods issue to production order (consumption)  — INGEST as Scope 1
  - 201 = Goods issue to cost center (consumption)       — INGEST
  - 262 = Reversal of 261                                 — INGEST (preserves
                                                            negative sign)
  - 202 = Reversal of 201                                 — INGEST
  - 101/501/311/312/561 = receipts/transfers/adjustments  — SKIP
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import IO, Iterable

CONSUMPTION_BWART = {"261", "201"}
REVERSAL_BWART = {"262", "202"}
INGESTED_BWART = CONSUMPTION_BWART | REVERSAL_BWART

HEADER_ALIASES = {
    # SAP technical name → canonical
    "WERKS": "plant_code",         "PLANT": "plant_code",        "WERK": "plant_code",
    "MATNR": "material_number",    "MATERIAL": "material_number",
    "MAKTX": "material_text",      "DESCRIPTION": "material_text",
    "BWART": "movement_type",      "MOVEMENT TYPE": "movement_type",
    "MENGE": "quantity",           "QUANTITY": "quantity",
    "MEINS": "unit",               "UNIT": "unit",  "UOM": "unit",
    "BUDAT": "posting_date",       "POSTING DATE": "posting_date", "DATE": "posting_date",
    "LIFNR": "vendor",             "VENDOR": "vendor",
    "WAERS": "currency",           "CURRENCY": "currency",
    "KOSTL": "cost_center",        "COST CENTER": "cost_center",
}

# Fuel type detection from material number / description.
# Hits the realistic German/English material naming.
FUEL_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("biodiesel", "biodi", "b100"),               "biodiesel_B100"),
    (("diesel", "kraftstoff", "gasoil", "gas oil"), "diesel_EN590"),
    (("petrol", "gasoline", "benzin", "unleaded"), "petrol"),
    (("erdgas", "natural gas", "ngas", "naturgas"), "natural_gas"),
    (("flussiggas", "flüssiggas", "lpg", "propan"), "lpg"),
    (("jet", "kerosin", "kerosene"),                "jet_fuel"),
]


def parse_german_decimal(value: str) -> Decimal | None:
    """'1.500,00' → Decimal('1500.00'); also handles plain '2500'."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    # If there's a comma, it's the decimal separator (German).
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_sap_date(value: str) -> date | None:
    v = (value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def detect_fuel_type(material_number: str, material_text: str) -> str | None:
    haystack = f"{material_number} {material_text}".lower()
    for needles, label in FUEL_PATTERNS:
        if any(n in haystack for n in needles):
            return label
    return None


def _read_text(file_obj: IO) -> str:
    data = file_obj.read()
    if isinstance(data, bytes):
        # SAP CSVs often arrive as UTF-8-BOM or latin-1.
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
    return data


def _detect_delimiter(sample: str) -> str:
    if sample.count(";") > sample.count(","):
        return ";"
    if "\t" in sample:
        return "\t"
    return ","


def parse(file_obj: IO) -> Iterable[dict]:
    """
    Yields one dict per row:
      {
        "row_number": int,
        "raw": {...},                  # verbatim row keyed by original header
        "status": "ok"|"error"|"warning",
        "errors": [str, ...],
        "record": {...} | None,        # canonical fields if status != error
      }
    """
    text = _read_text(file_obj)
    if not text.strip():
        return
    sample = text[:4096]
    delim = _detect_delimiter(sample)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers = next(reader, None)
    if not headers:
        return
    canonical = [HEADER_ALIASES.get(h.strip().upper(), h.strip().lower()) for h in headers]

    for i, row in enumerate(reader, start=2):  # row 1 was the header
        if not any(c.strip() for c in row):
            continue
        raw = {headers[j].strip(): (row[j] if j < len(row) else "")
               for j in range(len(headers))}
        canonical_row = {canonical[j]: (row[j] if j < len(row) else "")
                         for j in range(len(canonical))}

        result = _parse_row(canonical_row)
        yield {
            "row_number": i,
            "raw": raw,
            "status": result["status"],
            "errors": result["errors"],
            "record": result["record"],
        }


def _parse_row(c: dict) -> dict:
    errors: list[str] = []
    plant = c.get("plant_code", "").strip()
    matnr = c.get("material_number", "").strip()
    maktx = c.get("material_text", "").strip()
    bwart = c.get("movement_type", "").strip()
    qty_s = c.get("quantity", "")
    unit = c.get("unit", "").strip().upper()
    posting_date = parse_sap_date(c.get("posting_date", ""))

    # Filter: skip non-consumption movement types.
    if bwart and bwart not in INGESTED_BWART:
        return {
            "status": "ok",
            "record": None,
            "errors": [
                f"BWART {bwart} is not a consumption movement type; skipped."
            ],
        }

    # Required fields.
    for name, val in (("plant_code", plant), ("movement_type", bwart),
                      ("unit", unit), ("posting_date", c.get("posting_date", ""))):
        if not val:
            errors.append(f"Missing required field: {name}")

    qty = parse_german_decimal(qty_s)
    if qty is None:
        errors.append(f"Cannot parse quantity '{qty_s}'.")

    # Quantity sign sanity check.
    if qty is not None:
        if bwart in REVERSAL_BWART and qty > 0:
            errors.append(
                f"BWART {bwart} (reversal) has positive quantity — expected negative; analyst review needed."
            )
        if bwart in CONSUMPTION_BWART and qty < 0:
            errors.append(
                f"BWART {bwart} (consumption) has negative quantity — likely export error."
            )

    if errors and qty is None or posting_date is None or not plant or not bwart:
        return {"status": "error", "record": None, "errors": errors}

    fuel = detect_fuel_type(matnr, maktx)
    if fuel is None:
        return {
            "status": "ok",
            "record": None,
            "errors": [
                f"Material '{matnr} / {maktx}' is not recognised as a fuel/energy "
                "source; not classified as Scope 1 — skipping."
            ],
        }

    # Unit conversion expected by EmissionFactor table.
    canonical_unit = _canonicalize_unit(unit, fuel)
    if canonical_unit is None:
        return {
            "status": "error",
            "record": None,
            "errors": [f"Unsupported unit '{unit}' for fuel {fuel}."],
        }

    return {
        "status": "warning" if errors else "ok",
        "errors": errors,
        "record": {
            "activity_type": "fuel_combustion",
            "scope": "1",
            "scope3_category": None,
            "fuel_or_energy_type": fuel,
            "quantity_original": qty,
            "unit_original": unit,
            "quantity_normalized": qty,
            "unit_normalized": canonical_unit,
            "period_start": posting_date,
            "period_end": posting_date,
            "supplier_name": c.get("vendor", ""),
            "description": maktx or matnr,
            "plant_code": plant,
            "data_quality_tier": 1,
        },
    }


def _canonicalize_unit(unit: str, fuel: str) -> str | None:
    u = unit.upper()
    if fuel in {"diesel_EN590", "petrol", "biodiesel_B100", "jet_fuel"}:
        if u in {"L", "LTR", "LITER", "LITRE", "LITERS", "LITRES"}:
            return "L"
    if fuel == "natural_gas":
        if u in {"M3", "CBM", "NM3"}:
            return "M3"
    if fuel == "lpg":
        if u in {"KG", "KGM"}:
            return "KG"
    return None
