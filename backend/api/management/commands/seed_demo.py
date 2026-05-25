"""
Seed a demo tenant with users, facilities, and ingest the sample CSVs.

Idempotent: re-running does not duplicate. The dedup unique constraint on
(organization, row_sha256) means re-ingesting the same CSV produces 0 new
Activity rows — which is the whole demo-grade signal.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from api.ingest import ingest_file
from api.models import Facility, IngestionBatch, Organization, User

DEMO_ORG_SLUG = "acme-global"
DEMO_PASSWORD = "breathe2024"

SAMPLES = Path("/app/samples")


class Command(BaseCommand):
    help = "Seed a demo organisation, users, facilities, and ingest sample CSVs."

    def handle(self, *args, **opts):
        org, created = Organization.objects.get_or_create(
            slug=DEMO_ORG_SLUG,
            defaults={
                "name": "Acme Global Industries",
                "consolidation_approach": Organization.CONSOLIDATION_OPERATIONAL,
                "disclosure_framework": "GHG_PROTOCOL",
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created org: {org.name}"))

        analyst, ucreated = User.objects.get_or_create(
            username="analyst",
            defaults={
                "email": "analyst@acme.demo",
                "role": User.ROLE_ANALYST,
                "organization": org,
            },
        )
        if ucreated:
            analyst.set_password(DEMO_PASSWORD)
            analyst.save()
            self.stdout.write(self.style.SUCCESS(f"Created user: analyst / {DEMO_PASSWORD}"))

        admin, acreated = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@acme.demo",
                "role": User.ROLE_ADMIN,
                "organization": org,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if acreated:
            admin.set_password(DEMO_PASSWORD)
            admin.save()

        # Facilities — UK HQ + US ops + DE subsidiary
        facilities_spec = [
            {
                "name": "London HQ",
                "country_iso2": "GB",
                "region": "Greater London",
                "postal_code": "EC2A 4XX",
                "egrid_subregion": "",
                "sap_plant_codes": "1000",
            },
            {
                "name": "Munich Plant",
                "country_iso2": "DE",
                "region": "Bavaria",
                "postal_code": "80331",
                "egrid_subregion": "",
                "sap_plant_codes": "1100",
            },
            {
                "name": "San Francisco Office",
                "country_iso2": "US",
                "region": "California",
                "postal_code": "94105",
                "egrid_subregion": "CAMX",
                "sap_plant_codes": "2000",
            },
            {
                "name": "New York Office",
                "country_iso2": "US",
                "region": "New York",
                "postal_code": "10038",
                "egrid_subregion": "NYCW",
                "sap_plant_codes": "2100",
            },
        ]
        for spec in facilities_spec:
            Facility.objects.get_or_create(
                organization=org, name=spec["name"], defaults=spec
            )

        # Only ingest if no batches exist yet (idempotent guard).
        if IngestionBatch.objects.filter(organization=org).exists():
            self.stdout.write("Demo batches already present; skipping sample ingest.")
            return

        if not SAMPLES.exists():
            self.stdout.write(self.style.WARNING(
                f"Sample dir {SAMPLES} not found; skipping sample ingest."
            ))
            return

        for source_type, fname in [
            (IngestionBatch.SOURCE_SAP_FUEL, "sap_fuel_extract.csv"),
            (IngestionBatch.SOURCE_UTILITY_ELEC, "utility_electricity_export.csv"),
            (IngestionBatch.SOURCE_TRAVEL, "concur_expense_extract.csv"),
        ]:
            path = SAMPLES / fname
            if not path.exists():
                self.stdout.write(self.style.WARNING(f"Missing sample: {path}"))
                continue
            with path.open("rb") as fh:
                batch = ingest_file(org, source_type, fh, fname, analyst)
            self.stdout.write(self.style.SUCCESS(
                f"Ingested {fname}: {batch.ok_count} ok, "
                f"{batch.error_count} err, {batch.duplicate_count} dup"
            ))
