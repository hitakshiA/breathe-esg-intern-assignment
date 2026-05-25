"""
Emission calculation engine.

One entry point: `calculate_for_activity(activity)` which writes one or two
ActivityEmission rows (two for Scope 2 — location_based + market_based).
"""
from __future__ import annotations

from decimal import Decimal

from .models import Activity, ActivityEmission, EmissionFactor


def calculate_for_activity(activity: Activity) -> list[ActivityEmission]:
    """Idempotent — wipes existing rows and rewrites. Returns the new rows."""
    activity.emissions.all().delete()
    out: list[ActivityEmission] = []

    if activity.activity_type == Activity.TYPE_FUEL:
        out += _calc_fuel(activity)
    elif activity.activity_type == Activity.TYPE_ELECTRICITY:
        out += _calc_electricity(activity)
    elif activity.activity_type == Activity.TYPE_AIR:
        out += _calc_air(activity)
    elif activity.activity_type == Activity.TYPE_HOTEL:
        out += _calc_hotel(activity)
    elif activity.activity_type == Activity.TYPE_GROUND:
        out += _calc_ground(activity)
    return out


def _snapshot(activity, method, factor, co2e, note=""):
    return ActivityEmission.objects.create(
        activity=activity,
        method=method,
        factor=factor,
        factor_value_snapshot=factor.factor_value if factor else None,
        factor_source_snapshot=(
            f"{factor.source} {factor.dataset_version_year} · "
            f"{factor.get_activity_type_display()}"
            + (f" · {factor.fuel_or_energy_type}" if factor and factor.fuel_or_energy_type else "")
            + (f" · {factor.region_code}" if factor and factor.region_code else "")
            + (f" · {factor.cabin_class}" if factor and factor.cabin_class else "")
            + (f" · {factor.haul_band}-haul" if factor and factor.haul_band else "")
        ) if factor else "",
        rf_multiplier_snapshot=factor.rf_multiplier_applied if factor else None,
        co2e_kg=co2e,
        note=note,
    )


def _calc_fuel(activity):
    f = EmissionFactor.objects.filter(
        activity_type="fuel_combustion",
        fuel_or_energy_type=activity.fuel_or_energy_type,
    ).order_by("-dataset_version_year").first()
    if not f:
        return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, None, None,
                          note=f"No factor for fuel '{activity.fuel_or_energy_type}'.")]
    co2e = (activity.quantity_normalized * f.factor_value).quantize(Decimal("0.0001"))
    return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, f, co2e)]


def _calc_electricity(activity):
    # Determine region. Prefer facility eGRID; else facility country; else "GB" default.
    egrid = activity.facility.egrid_subregion if activity.facility else ""
    country = activity.facility.country_iso2 if activity.facility else ""

    # Location-based factor
    if egrid:
        loc = EmissionFactor.objects.filter(
            activity_type="electricity", region_code=egrid,
            source="EPA_EGRID",
        ).order_by("-dataset_version_year").first()
    else:
        loc = EmissionFactor.objects.filter(
            activity_type="electricity", region_code=country or "GB",
        ).order_by("-dataset_version_year").first()

    out = []
    if loc:
        co2e = (activity.quantity_normalized * loc.factor_value).quantize(Decimal("0.0001"))
        out.append(_snapshot(activity, ActivityEmission.METHOD_LOCATION, loc, co2e,
                             note="Grid average (location-based) per GHG Protocol Scope 2 Guidance §6.1."))
    else:
        out.append(_snapshot(activity, ActivityEmission.METHOD_LOCATION, None, None,
                             note="No location-based factor found for this region."))

    # Market-based — schema slot exists, computation deferred to V2.
    out.append(_snapshot(
        activity, ActivityEmission.METHOD_MARKET, None, None,
        note=(
            "Market-based: pending REC/PPA Quality Criteria validation per "
            "GHG Protocol Scope 2 Guidance §7. V1 stores EAC records but does "
            "not compute. See TRADEOFFS.md."
        )
    ))
    return out


def _calc_air(activity):
    # Determine haul band
    dist = activity.distance_km or Decimal("0")
    haul = "long" if dist >= Decimal("3700") else "short"
    cabin = activity.cabin_class or "Economy"
    # Some short-haul rows in DEFRA only have Economy/Business; fall back.
    f = EmissionFactor.objects.filter(
        activity_type="air_travel", haul_band=haul, cabin_class=cabin,
    ).order_by("-dataset_version_year").first()
    if not f and cabin in {"Premium Economy", "First"} and haul == "short":
        f = EmissionFactor.objects.filter(
            activity_type="air_travel", haul_band="short", cabin_class="Business",
        ).order_by("-dataset_version_year").first()
    if not f:
        return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, None, None,
                          note=f"No factor for {haul}-haul {cabin}.")]
    # CO2e per p.km × distance × RF
    rf = f.rf_multiplier_applied or Decimal("1")
    co2e = (dist * f.factor_value * rf).quantize(Decimal("0.0001"))
    return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, f, co2e,
                      note=f"Base CO2 × RF {rf} (DEFRA aviation methodology).")]


def _calc_hotel(activity):
    country = (activity.raw_row.raw_data.get("hotel_country", "") or "").upper()
    # Fall back to facility country
    if not country and activity.facility:
        country = activity.facility.country_iso2
    if not country:
        country = "GB"
    f = EmissionFactor.objects.filter(
        activity_type="hotel_stay", region_code=country,
    ).order_by("-dataset_version_year").first()
    if not f:
        # Try GB as a sane fallback for unknown jurisdictions.
        f = EmissionFactor.objects.filter(activity_type="hotel_stay", region_code="GB").first()
    if not f:
        return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, None, None,
                          note="No hotel factor available.")]
    co2e = (activity.quantity_normalized * f.factor_value).quantize(Decimal("0.0001"))
    return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, f, co2e,
                      note=f"Per-country hotel factor ({country}).")]


def _calc_ground(activity):
    sub = activity.fuel_or_energy_type or "taxi"
    f = EmissionFactor.objects.filter(
        activity_type="ground_transport", fuel_or_energy_type=sub,
    ).order_by("-dataset_version_year").first()
    if not f or activity.data_quality_tier == 3:
        return [_snapshot(activity, ActivityEmission.METHOD_SPEND, None, None,
                          note="Spend-based; activity-based calc not possible.")]
    co2e = (activity.quantity_normalized * f.factor_value).quantize(Decimal("0.0001"))
    return [_snapshot(activity, ActivityEmission.METHOD_ACTIVITY, f, co2e)]
