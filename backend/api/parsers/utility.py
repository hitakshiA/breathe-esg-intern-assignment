"""
Utility electricity portal export parser.

Targets the shape of US utility data dictionaries — PG&E "Bill Detail",
ConEd "Account Detail". Production paths considered and deferred:

  - NAESB REQ.21 ESPI Green Button Connect XML (free; per-utility availability)
  - UtilityAPI / Urjanet (Arcadia Plug) aggregators (paid, multi-country)
  - Individual utility APIs (e.g. PG&E Share My Data) (cert auth + setup)

We chose CSV upload because:
  - It's what the facilities team actually exports week-1 from any utility portal
  - Every realistic V2 path is a parser swap, not a data-model change

Quirks handled:
  - Mixed kWh / MWh units in the same file
  - Billing periods that don't align with calendar months (we store as-given)
  - Estimated vs Actual reads (data_quality_tier downgrade)
  - "Demand" (kW) is informational; we don't multiply it as if it were energy.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import IO, Iterable

# ZIP → eGRID subregion lookup. Subset of the EPA Power Profiler table.
# Real implementation loads the full ZIP→subregion CSV (~42k rows).
ZIP_TO_EGRID = {
    "94105": "CAMX",  "94103": "CAMX",  "94107": "CAMX",   # SF
    "10038": "NYCW",  "10001": "NYCW",  "10025": "NYCW",   # NYC
    "77001": "ERCT",  "77002": "ERCT",  "75201": "ERCT",   # Texas
    "60601": "RFCW",  "60607": "RFCW",                       # Chicago
    "02108": "NEWE",  "02110": "NEWE",                       # Boston
    "98101": "NWPP",  "97201": "NWPP",                       # Pacific NW
    "20001": "RFCE",  "20004": "RFCE",  "20850": "RFCE",   # DC area
}

HEADER_ALIASES = {
    "account_number": "account_number",   "account no": "account_number",
    "meter_id": "meter_id",               "meter": "meter_id",        "meter no": "meter_id",
    "service_address": "service_address", "address": "service_address",
    "service_zip": "service_zip",         "zip": "service_zip", "postcode": "service_zip", "zip code": "service_zip",
    "bill_start": "bill_start",           "billing period start": "bill_start", "from": "bill_start",
    "bill_end": "bill_end",               "billing period end": "bill_end",     "to": "bill_end",
    "kwh_consumed": "kwh",  "kwh": "kwh", "consumption (kwh)": "kwh", "usage (kwh)": "kwh", "consumption": "kwh",
    "mwh": "mwh", "consumption (mwh)": "mwh",
    "demand_kw": "demand_kw", "demand (kw)": "demand_kw", "peak demand (kw)": "demand_kw",
    "read_type": "read_type", "read type": "read_type",
    "rate_schedule": "rate_schedule", "rate": "rate_schedule", "tariff": "rate_schedule",
    "total_cost_usd": "total_cost", "total cost (usd)": "total_cost", "cost": "total_cost",
}


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


def _parse_date(value: str) -> date | None:
    v = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _to_decimal(s: str) -> Decimal | None:
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


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
    account = c.get("account_number", "").strip()
    meter = c.get("meter_id", "").strip()
    zipcode = c.get("service_zip", "").strip()
    address = c.get("service_address", "").strip()
    start = _parse_date(c.get("bill_start", ""))
    end = _parse_date(c.get("bill_end", "")) or start

    # Either kWh or MWh must be present
    kwh = _to_decimal(c.get("kwh", ""))
    mwh = _to_decimal(c.get("mwh", ""))
    if kwh is None and mwh is None:
        # Maybe it was in a different column we couldn't alias
        for guess in ("kwh", "consumption", "usage", "energy"):
            for k, v in c.items():
                if guess in k and v:
                    kwh = _to_decimal(v)
                    if kwh is not None:
                        break

    if mwh is not None and kwh is None:
        kwh = mwh * Decimal("1000")

    if kwh is None:
        errors.append("Missing kWh consumption.")

    if start is None:
        errors.append("Missing billing period start.")

    if errors:
        return {"status": "error", "record": None, "errors": errors}

    # Read-type quality flag
    read_type = c.get("read_type", "").strip().lower()
    tier = 1
    if read_type in {"estimated", "estimate", "est", "calculated"}:
        tier = 2

    # Demand vs energy sanity check — if demand_kw is given and is far higher
    # than kwh would imply, the user probably exported MWh in a kWh column.
    demand_kw = _to_decimal(c.get("demand_kw", ""))
    warnings = []
    if demand_kw and kwh and start and end:
        days = max((end - start).days, 1)
        # Implausible max-load check: peak demand can't exceed energy / hours.
        avg_kw = kwh / (Decimal(days) * Decimal(24))
        if demand_kw > avg_kw * Decimal("4") and kwh < Decimal("1000"):
            warnings.append(
                f"Peak demand {demand_kw} kW with only {kwh} kWh over {days} days "
                "suggests the consumption column may be in MWh."
            )
            tier = 2  # downgrade quality

    egrid = ZIP_TO_EGRID.get(zipcode)

    return {
        "status": "warning" if warnings else "ok",
        "errors": warnings,
        "record": {
            "activity_type": "electricity",
            "scope": "2",
            "scope3_category": None,
            "fuel_or_energy_type": "grid_avg",
            "quantity_original": kwh,
            "unit_original": "kWh",
            "quantity_normalized": kwh,
            "unit_normalized": "kWh",
            "period_start": start,
            "period_end": end,
            "supplier_name": "",
            "description": f"{account} · {meter} · {address}",
            "service_zip": zipcode,
            "egrid_subregion": egrid or "",
            "country_iso2": "US" if egrid else "",
            "data_quality_tier": tier,
        },
    }
