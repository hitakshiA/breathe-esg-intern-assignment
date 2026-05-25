"""
Concur / Navan expense extract parser.

Concur holds ~70% of the enterprise TMC market; Navan/TripActions has the
same data shape under different field names. We parse Concur Expense Report
Extract CSVs because:

  - Live API needs OAuth2 partner-app approval (multi-week procurement)
  - Concur Itinerary v4 *does* return CarbonEmissionLbs + CarbonModel (ISO
    14083 assured via Thrust Carbon partnership), so a V2 path is to ingest
    via API and surface both vendor-computed and our DEFRA-computed values.

Expense types we ingest:
  Airfare / Hotel / Car Rental / Taxi  → Scope 3 Category 6
  (Train/Rail are realistic but deferred — see TRADEOFFS.md)

Flight distance handling:
  Concur's extract doesn't include distance. We compute great-circle
  (Haversine) and apply DEFRA's recommended 8% detour uplift. Unknown IATA
  codes (e.g. typo'd "ZZZ") are flagged for analyst, not silently dropped.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import IO, Iterable

from .airports import flight_distance_km

HEADER_ALIASES = {
    "report_id": "report_id",
    "employee_id": "employee_id",
    "employee_name": "employee_name",
    "expense_type": "expense_type",
    "transaction_date": "transaction_date",   "date": "transaction_date",
    "travel_date": "transaction_date",
    "origin": "origin_iata",                  "origin_iata": "origin_iata", "from": "origin_iata",
    "destination": "destination_iata",        "destination_iata": "destination_iata", "to": "destination_iata",
    "cabin_class": "cabin_class",             "class": "cabin_class",
    "nights": "nights",
    "vendor": "vendor",                       "supplier": "vendor",
    "amount": "amount",
    "currency": "currency",
    "trip_purpose": "trip_purpose",           "purpose": "trip_purpose",
    "hotel_country": "hotel_country",         "country": "hotel_country",
    "vehicle_type": "vehicle_type",
    "distance_km": "distance_km",
}

EXPENSE_TYPE_MAP = {
    "airfare": "air_travel",
    "air": "air_travel",
    "flight": "air_travel",
    "hotel": "hotel_stay",
    "lodging": "hotel_stay",
    "taxi": "ground_transport",
    "rideshare": "ground_transport",
    "car rental": "ground_transport",
    "rental car": "ground_transport",
    "rental": "ground_transport",
}

VALID_CABINS = {"Economy", "Premium Economy", "Business", "First"}

# Quick hotel-country guess from address text (V1 covers the demo set).
COUNTRY_HINTS: list[tuple[str, str]] = [
    ("United States", "US"), ("USA", "US"), (" US", "US"), (" NY", "US"), (" CA", "US"), (" TX", "US"),
    ("United Kingdom", "GB"), ("UK", "GB"), ("London", "GB"),
    ("Germany", "DE"), ("Frankfurt", "DE"), ("Munich", "DE"), ("Berlin", "DE"),
    ("France", "FR"), ("Paris", "FR"),
    ("Singapore", "SG"),
    ("Japan", "JP"), ("Tokyo", "JP"),
    ("India", "IN"), ("Mumbai", "IN"), ("Delhi", "IN"), ("Bengaluru", "IN"), ("Bangalore", "IN"),
    ("UAE", "AE"), ("Dubai", "AE"), ("Abu Dhabi", "AE"),
]


def _to_decimal(s: str) -> Decimal | None:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_date(s: str) -> date | None:
    v = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _hotel_country(vendor: str, explicit: str = "") -> str:
    if explicit:
        return explicit.strip().upper()[:2]
    for needle, iso in COUNTRY_HINTS:
        if needle.lower() in vendor.lower():
            return iso
    return ""


def _read_text(file_obj: IO) -> str:
    data = file_obj.read()
    if isinstance(data, bytes):
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
    return data


def parse(file_obj: IO) -> Iterable[dict]:
    text = _read_text(file_obj)
    if not text.strip():
        return
    delim = ";" if text[:4096].count(";") > text[:4096].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers = next(reader, None)
    if not headers:
        return
    canonical = [HEADER_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in headers]

    for i, row in enumerate(reader, start=2):
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
    et = c.get("expense_type", "").strip().lower()
    activity_type = EXPENSE_TYPE_MAP.get(et)
    if activity_type is None:
        return {
            "status": "ok",
            "record": None,
            "errors": [
                f"Expense type '{et}' is not a Scope 3 Cat 6 travel category; skipped."
            ],
        }

    txn_date = _parse_date(c.get("transaction_date", ""))
    if txn_date is None:
        errors.append("Missing or unparseable transaction_date.")

    employee_id = c.get("employee_id", "").strip()
    employee_name = c.get("employee_name", "").strip()
    vendor = c.get("vendor", "").strip()
    trip_purpose = c.get("trip_purpose", "").strip()
    amount = _to_decimal(c.get("amount", ""))
    currency = c.get("currency", "").strip().upper()

    if activity_type == "air_travel":
        origin = c.get("origin_iata", "").strip().upper()
        dest = c.get("destination_iata", "").strip().upper()
        cabin = c.get("cabin_class", "").strip()
        if cabin and cabin not in VALID_CABINS:
            cabin = cabin.title()
        if cabin not in VALID_CABINS:
            cabin = "Economy"   # default per DEFRA when class missing
            errors.append("Cabin class missing or unrecognized; defaulted to Economy.")

        # Distance: prefer column, fallback to Haversine.
        dist = _to_decimal(c.get("distance_km", ""))
        derived = False
        if dist is None and origin and dest:
            km = flight_distance_km(origin, dest)
            if km is None:
                errors.append(
                    f"Could not compute distance for {origin}→{dest}: airport(s) "
                    "not in lookup. Flag for analyst."
                )
            else:
                dist = Decimal(str(km))
                derived = True
        if dist is None:
            return {"status": "error", "record": None, "errors": errors or ["No distance and IATA codes unknown."]}

        return {
            "status": "warning" if errors else "ok",
            "errors": errors,
            "record": {
                "activity_type": "air_travel",
                "scope": "3",
                "scope3_category": 6,
                "fuel_or_energy_type": "",
                "quantity_original": dist,
                "unit_original": "km",
                "quantity_normalized": dist,
                "unit_normalized": "p.km",
                "period_start": txn_date,
                "period_end": txn_date,
                "supplier_name": vendor,
                "description": f"{employee_name} · {origin}→{dest} · {trip_purpose}",
                "cabin_class": cabin,
                "origin_iata": origin,
                "destination_iata": dest,
                "distance_km": dist,
                "data_quality_tier": 2 if derived else 1,
            },
        }

    if activity_type == "hotel_stay":
        nights = _to_decimal(c.get("nights", ""))
        if nights is None or nights <= 0:
            return {"status": "error", "record": None,
                    "errors": ["Hotel row missing 'nights' or non-positive."]}
        country = _hotel_country(vendor, c.get("hotel_country", ""))
        if not country:
            errors.append("Could not determine hotel country from vendor; flag for analyst.")
        return {
            "status": "warning" if errors else "ok",
            "errors": errors,
            "record": {
                "activity_type": "hotel_stay",
                "scope": "3",
                "scope3_category": 6,
                "fuel_or_energy_type": "",
                "quantity_original": nights,
                "unit_original": "night",
                "quantity_normalized": nights,
                "unit_normalized": "room-night",
                "period_start": txn_date,
                "period_end": txn_date,
                "supplier_name": vendor,
                "description": f"{employee_name} · {vendor} · {trip_purpose}",
                "country_iso2": country,
                "data_quality_tier": 1 if country else 2,
            },
        }

    # ground_transport — taxi or car rental
    dist = _to_decimal(c.get("distance_km", ""))
    if dist is None:
        # spend-based fallback — record with tier 3 and no distance.
        if amount is None:
            return {"status": "error", "record": None,
                    "errors": ["Ground transport: no distance and no amount."]}
        return {
            "status": "warning",
            "errors": ["No distance — using spend-based fallback (tier 3)."],
            "record": {
                "activity_type": "ground_transport",
                "scope": "3",
                "scope3_category": 6,
                "fuel_or_energy_type": "rental_average" if "rental" in (vendor + et).lower() else "taxi",
                "quantity_original": amount,
                "unit_original": currency or "spend",
                "quantity_normalized": Decimal("0"),  # cannot compute without distance
                "unit_normalized": "km",
                "period_start": txn_date,
                "period_end": txn_date,
                "supplier_name": vendor,
                "description": f"{employee_name} · {vendor} · {trip_purpose}",
                "data_quality_tier": 3,
            },
        }
    return {
        "status": "ok",
        "errors": [],
        "record": {
            "activity_type": "ground_transport",
            "scope": "3",
            "scope3_category": 6,
            "fuel_or_energy_type": "rental_average" if "rental" in (vendor + et).lower() else "taxi",
            "quantity_original": dist,
            "unit_original": "km",
            "quantity_normalized": dist,
            "unit_normalized": "km",
            "period_start": txn_date,
            "period_end": txn_date,
            "supplier_name": vendor,
            "description": f"{employee_name} · {vendor} · {trip_purpose}",
            "data_quality_tier": 1,
        },
    }
