"""Idempotently seed the EmissionFactor table from canonical sources."""
from datetime import date

from django.core.management.base import BaseCommand

from api import factors as F
from api.models import EmissionFactor


class Command(BaseCommand):
    help = "Seed EmissionFactor rows from DEFRA 2024 and EPA eGRID 2022."

    def handle(self, *args, **opts):
        n_created = 0

        def upsert(**kwargs):
            nonlocal n_created
            defaults = kwargs.pop("defaults", {})
            _, created = EmissionFactor.objects.get_or_create(defaults=defaults, **kwargs)
            if created:
                n_created += 1

        # ── DEFRA 2024 fuels ────────────────────────────────────────────────
        for fuel_type, unit, value in F.DEFRA_2024_FUELS:
            upsert(
                source=EmissionFactor.SOURCE_DEFRA,
                dataset_version_year=2024,
                activity_type="fuel_combustion",
                fuel_or_energy_type=fuel_type,
                region_code="",
                cabin_class="",
                haul_band="",
                valid_from=date(2024, 6, 6),
                defaults={
                    "valid_to": None,
                    "factor_value": value,
                    "unit_input": unit,
                    "unit_output": "kgCO2e",
                    "gwp_basis": "AR6",
                    "source_url": F.DEFRA_URL_2024,
                    "notes": "DEFRA 2024 fuel combustion, direct emissions only.",
                },
            )

        # ── EPA eGRID 2022 (US electricity, location-based) ────────────────
        for subregion, value in F.EPA_EGRID_2022:
            upsert(
                source=EmissionFactor.SOURCE_EPA_EGRID,
                dataset_version_year=2022,
                activity_type="electricity",
                fuel_or_energy_type="grid_avg",
                region_code=subregion,
                cabin_class="",
                haul_band="",
                valid_from=date(2024, 1, 30),  # eGRID2022 release date
                defaults={
                    "factor_value": value,
                    "unit_input": "kWh",
                    "unit_output": "kgCO2e",
                    "gwp_basis": "AR5",
                    "source_url": F.EPA_EGRID_URL,
                    "notes": "EPA eGRID2022 subregion total output rate.",
                },
            )

        # ── National grid (non-US) ──────────────────────────────────────────
        for iso2, value in F.LOCATION_GRID_BY_COUNTRY:
            upsert(
                source=EmissionFactor.SOURCE_IEA if iso2 != "GB" else EmissionFactor.SOURCE_DEFRA,
                dataset_version_year=2024 if iso2 == "GB" else 2023,
                activity_type="electricity",
                fuel_or_energy_type="grid_avg",
                region_code=iso2,
                cabin_class="",
                haul_band="",
                valid_from=date(2024, 1, 1) if iso2 == "GB" else date(2023, 11, 1),
                defaults={
                    "factor_value": value,
                    "unit_input": "kWh",
                    "unit_output": "kgCO2e",
                    "gwp_basis": "AR6" if iso2 == "GB" else "AR5",
                    "source_url": F.DEFRA_URL_2024 if iso2 == "GB" else F.IEA_URL,
                    "notes": f"National grid average for {iso2}, location-based.",
                },
            )

        # ── Aviation (RF stored separately!) ────────────────────────────────
        for haul, cabin, value in F.DEFRA_2024_AVIATION:
            upsert(
                source=EmissionFactor.SOURCE_DEFRA,
                dataset_version_year=2024,
                activity_type="air_travel",
                fuel_or_energy_type="",
                region_code="",
                cabin_class=cabin,
                haul_band=haul,
                valid_from=date(2024, 6, 6),
                defaults={
                    "factor_value": value,
                    "unit_input": "p.km",
                    "unit_output": "kgCO2e",
                    "rf_multiplier_applied": F.AVIATION_RF_MULTIPLIER,
                    "gwp_basis": "AR6",
                    "source_url": F.DEFRA_URL_2024,
                    "notes": (
                        "CO2-only base. RF multiplier stored separately so "
                        "disclosure choice (1.0/1.7/1.9) is explicit. Currently "
                        f"applying {F.AVIATION_RF_MULTIPLIER}× per DEFRA 2024."
                    ),
                },
            )

        # ── Hotels (per country, per room-night) ────────────────────────────
        for iso2, value in F.DEFRA_2024_HOTEL:
            upsert(
                source=EmissionFactor.SOURCE_DEFRA,
                dataset_version_year=2024,
                activity_type="hotel_stay",
                fuel_or_energy_type="",
                region_code=iso2,
                cabin_class="",
                haul_band="",
                valid_from=date(2024, 6, 6),
                defaults={
                    "factor_value": value,
                    "unit_input": "room-night",
                    "unit_output": "kgCO2e",
                    "gwp_basis": "AR6",
                    "source_url": F.DEFRA_URL_2024,
                    "notes": f"Per-country hotel factor for {iso2}.",
                },
            )

        # ── Ground transport ────────────────────────────────────────────────
        for sub_type, value in F.DEFRA_2024_GROUND:
            upsert(
                source=EmissionFactor.SOURCE_DEFRA,
                dataset_version_year=2024,
                activity_type="ground_transport",
                fuel_or_energy_type=sub_type,
                region_code="",
                cabin_class="",
                haul_band="",
                valid_from=date(2024, 6, 6),
                defaults={
                    "factor_value": value,
                    "unit_input": "km",
                    "unit_output": "kgCO2e",
                    "gwp_basis": "AR6",
                    "source_url": F.DEFRA_URL_2024,
                    "notes": "DEFRA 2024 ground transport per passenger-km.",
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"seed_factors: {n_created} new EmissionFactor rows "
            f"(total now: {EmissionFactor.objects.count()})"
        ))
