"""
Breathe ESG — data model.

Built around a single load-bearing question: can an auditor reconstruct the
exact derivation of any reported number, even after factor tables update?

Three layers:
1. Raw layer       — IngestionBatch, RawRow (immutable, append-only)
2. Canonical layer — Activity (one normalized row per source row)
3. Calculation     — EmissionFactor (versioned) → ActivityEmission (snapshotted)

GHG Protocol alignment:
- Scope 1/2/3 categorization on every Activity
- Dual Scope 2 reporting: one Activity may have two ActivityEmission rows
  (method=location_based AND method=market_based)
- EnergyAttributeCertificate models contractual instruments (REC/PPA) for
  market-based; V1 stores them, V2 computes from them.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


# ── Tenancy ─────────────────────────────────────────────────────────────────
class Organization(models.Model):
    """One client company. The primary multi-tenancy boundary."""

    CONSOLIDATION_OPERATIONAL = "operational_control"
    CONSOLIDATION_FINANCIAL = "financial_control"
    CONSOLIDATION_EQUITY = "equity_share"
    CONSOLIDATION_CHOICES = [
        (CONSOLIDATION_OPERATIONAL, "Operational Control"),
        (CONSOLIDATION_FINANCIAL, "Financial Control"),
        (CONSOLIDATION_EQUITY, "Equity Share"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    # GHG Protocol Corporate Standard Ch.3 — picked at onboarding.
    consolidation_approach = models.CharField(
        max_length=24,
        choices=CONSOLIDATION_CHOICES,
        default=CONSOLIDATION_OPERATIONAL,
    )
    # Disclosure framework the tenant ultimately reports under.
    # Drives required-field validation in V2.
    disclosure_framework = models.CharField(
        max_length=16,
        default="GHG_PROTOCOL",
        choices=[
            ("GHG_PROTOCOL", "GHG Protocol Corporate"),
            ("CSRD_ESRS_E1", "EU CSRD ESRS E1"),
            ("CA_SB253", "California SB 253"),
            ("IN_BRSR", "India BRSR"),
        ],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    """Custom user. Bound to one organization, holds one role."""

    ROLE_ADMIN = "admin"
    ROLE_ANALYST = "analyst"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_ANALYST, "Analyst"),
        (ROLE_VIEWER, "Viewer"),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_ANALYST)

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class Facility(models.Model):
    """A physical or operational site. Carries grid + SAP lookup metadata."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="facilities"
    )
    name = models.CharField(max_length=200)
    country_iso2 = models.CharField(max_length=2)  # ISO 3166-1 alpha-2
    region = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=12, blank=True)

    # US Scope 2 location-based requires eGRID subregion mapping. EPA defines 26.
    EGRID_SUBREGIONS = [
        ("AKGD", "AKGD — ASCC Alaska Grid"),
        ("AKMS", "AKMS — ASCC Miscellaneous"),
        ("AZNM", "AZNM — WECC Southwest"),
        ("CAMX", "CAMX — WECC California"),
        ("ERCT", "ERCT — ERCOT All"),
        ("FRCC", "FRCC — FRCC All"),
        ("HIMS", "HIMS — HICC Miscellaneous"),
        ("HIOA", "HIOA — HICC Oahu"),
        ("MROE", "MROE — MRO East"),
        ("MROW", "MROW — MRO West"),
        ("NEWE", "NEWE — NPCC New England"),
        ("NWPP", "NWPP — WECC Northwest"),
        ("NYCW", "NYCW — NPCC NYC/Westchester"),
        ("NYLI", "NYLI — NPCC Long Island"),
        ("NYUP", "NYUP — NPCC Upstate NY"),
        ("PRMS", "PRMS — Puerto Rico Miscellaneous"),
        ("RFCE", "RFCE — RFC East"),
        ("RFCM", "RFCM — RFC Michigan"),
        ("RFCW", "RFCW — RFC West"),
        ("RMPA", "RMPA — WECC Rockies"),
        ("SPNO", "SPNO — SPP North"),
        ("SPSO", "SPSO — SPP South"),
        ("SRMV", "SRMV — SERC Mississippi Valley"),
        ("SRMW", "SRMW — SERC Midwest"),
        ("SRSO", "SRSO — SERC South"),
        ("SRTV", "SRTV — SERC Tennessee Valley"),
        ("SRVC", "SRVC — SERC Virginia/Carolina"),
    ]
    egrid_subregion = models.CharField(
        max_length=8, blank=True, choices=EGRID_SUBREGIONS
    )

    # SAP plant codes (WERKS) that map to this facility. Comma-separated for
    # SQLite-portability — JSONField is overkill here.
    sap_plant_codes = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma-separated SAP WERKS codes (e.g. '1000,1100').",
    )

    def plant_code_list(self) -> list[str]:
        return [c.strip() for c in self.sap_plant_codes.split(",") if c.strip()]

    class Meta:
        ordering = ["organization", "name"]
        verbose_name_plural = "Facilities"

    def __str__(self) -> str:
        return f"{self.name} ({self.country_iso2})"


# ── Source-of-truth raw layer (immutable) ───────────────────────────────────
class IngestionBatch(models.Model):
    """One upload session. Tracks parse outcome and stores the original file."""

    SOURCE_SAP_FUEL = "sap_fuel"
    SOURCE_UTILITY_ELEC = "utility_electricity"
    SOURCE_TRAVEL = "travel"
    SOURCE_CHOICES = [
        (SOURCE_SAP_FUEL, "SAP — Fuel & Procurement"),
        (SOURCE_UTILITY_ELEC, "Utility — Electricity"),
        (SOURCE_TRAVEL, "Travel — Concur/Navan Export"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_SUCCEEDED_WITH_ERRORS = "succeeded_with_errors"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_SUCCEEDED_WITH_ERRORS, "Succeeded with errors"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="batches"
    )
    source_type = models.CharField(max_length=24, choices=SOURCE_CHOICES)
    file_name = models.CharField(max_length=500)
    file = models.FileField(upload_to="batches/%Y/%m/", null=True, blank=True)
    file_sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="batches"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    row_count = models.PositiveIntegerField(default=0)
    ok_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(
        default=0,
        help_text="Rows skipped because row_sha256 was already ingested for this org.",
    )
    error_summary = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["organization", "source_type"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_source_type_display()} — {self.file_name} ({self.status})"


class RawRow(models.Model):
    """A single row from a source file, stored verbatim. Immutable."""

    PARSE_OK = "ok"
    PARSE_ERROR = "error"
    PARSE_WARNING = "warning"
    PARSE_CHOICES = [
        (PARSE_OK, "OK"),
        (PARSE_ERROR, "Error"),
        (PARSE_WARNING, "Warning"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="raw_rows",
        help_text="Denormalized from batch.organization for dedup unique constraint.",
    )
    batch = models.ForeignKey(
        IngestionBatch, on_delete=models.CASCADE, related_name="raw_rows"
    )
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField()
    row_sha256 = models.CharField(max_length=64, db_index=True)
    parse_status = models.CharField(
        max_length=8, choices=PARSE_CHOICES, default=PARSE_OK
    )
    parse_errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["batch", "row_number"]
        # Content-based dedup across re-uploads and overlapping date-range exports.
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "row_sha256"],
                name="uniq_org_row_sha256",
            )
        ]
        indexes = [
            models.Index(fields=["batch", "parse_status"]),
        ]

    @staticmethod
    def hash_payload(payload: dict) -> str:
        """Deterministic SHA-256 of a row payload (key-sorted, stripped)."""
        normalized = json.dumps(
            {k.strip(): str(v).strip() for k, v in payload.items()},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── Canonical activity layer ────────────────────────────────────────────────
class Activity(models.Model):
    """The normalized record. One per source row that produced a usable record."""

    SCOPE_1 = "1"
    SCOPE_2 = "2"
    SCOPE_3 = "3"
    SCOPE_CHOICES = [
        (SCOPE_1, "Scope 1 — Direct"),
        (SCOPE_2, "Scope 2 — Purchased energy"),
        (SCOPE_3, "Scope 3 — Value chain"),
    ]

    TYPE_FUEL = "fuel_combustion"
    TYPE_ELECTRICITY = "electricity"
    TYPE_AIR = "air_travel"
    TYPE_HOTEL = "hotel_stay"
    TYPE_GROUND = "ground_transport"
    TYPE_CHOICES = [
        (TYPE_FUEL, "Fuel combustion"),
        (TYPE_ELECTRICITY, "Purchased electricity"),
        (TYPE_AIR, "Air travel"),
        (TYPE_HOTEL, "Hotel stay"),
        (TYPE_GROUND, "Ground transport"),
    ]

    REVIEW_DRAFT = "draft"
    REVIEW_PENDING = "under_review"
    REVIEW_APPROVED = "approved"
    REVIEW_REJECTED = "rejected"
    REVIEW_CHOICES = [
        (REVIEW_DRAFT, "Draft"),
        (REVIEW_PENDING, "Under review"),
        (REVIEW_APPROVED, "Approved"),
        (REVIEW_REJECTED, "Rejected"),
    ]

    # GHG Protocol methodology hierarchy. Never silently mix tiers in totals.
    TIER_ACTUAL = 1     # primary measured data (e.g. meter reading)
    TIER_DERIVED = 2    # derived (e.g. great-circle distance, estimated read)
    TIER_ESTIMATED = 3  # spend-based or extrapolated

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="activities"
    )
    raw_row = models.OneToOneField(
        RawRow, on_delete=models.PROTECT, related_name="activity"
    )
    facility = models.ForeignKey(
        Facility, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activities",
    )

    activity_type = models.CharField(max_length=24, choices=TYPE_CHOICES)
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    scope3_category = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="GHG Protocol Scope 3 category 1..15. Cat 6 = business travel.",
    )

    period_start = models.DateField()
    period_end = models.DateField()

    quantity_original = models.DecimalField(max_digits=18, decimal_places=4)
    unit_original = models.CharField(max_length=16)
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4)
    unit_normalized = models.CharField(max_length=16)

    fuel_or_energy_type = models.CharField(max_length=32, blank=True)
    cabin_class = models.CharField(max_length=24, blank=True)
    origin_iata = models.CharField(max_length=3, blank=True)
    destination_iata = models.CharField(max_length=3, blank=True)
    distance_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    supplier_name = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=400, blank=True)

    data_quality_tier = models.PositiveSmallIntegerField(default=TIER_ACTUAL)
    review_status = models.CharField(
        max_length=16, choices=REVIEW_CHOICES, default=REVIEW_PENDING
    )
    flags = models.JSONField(
        default=list, blank=True,
        help_text="Auto-detected concerns. Each: {code, message, severity}.",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Once locked (e.g. after audit sign-off), record is immutable.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start", "scope", "activity_type"]
        indexes = [
            models.Index(fields=["organization", "review_status"]),
            models.Index(fields=["organization", "scope"]),
            models.Index(fields=["organization", "period_start"]),
            models.Index(fields=["organization", "is_locked"]),
        ]
        verbose_name_plural = "Activities"

    def __str__(self) -> str:
        return f"{self.get_activity_type_display()} | {self.period_start} | Scope {self.scope}"


# ── Versioned emission factor table ─────────────────────────────────────────
class EmissionFactor(models.Model):
    """
    Versioned factor table. Records reference factors by FK *and* snapshot the
    value on ActivityEmission, so updating a factor row never retroactively
    changes approved emission figures.
    """

    SOURCE_DEFRA = "DEFRA"
    SOURCE_EPA_EGRID = "EPA_EGRID"
    SOURCE_IEA = "IEA"
    SOURCE_ICAO = "ICAO"
    SOURCE_CUSTOM = "CUSTOM"
    SOURCE_CHOICES = [
        (SOURCE_DEFRA, "UK DEFRA / DESNZ"),
        (SOURCE_EPA_EGRID, "US EPA eGRID"),
        (SOURCE_IEA, "IEA Emissions Factors"),
        (SOURCE_ICAO, "ICAO Carbon Emissions Calculator"),
        (SOURCE_CUSTOM, "Custom"),
    ]

    HAUL_SHORT = "short"
    HAUL_LONG = "long"

    source = models.CharField(max_length=16, choices=SOURCE_CHOICES)
    dataset_version_year = models.PositiveSmallIntegerField()
    activity_type = models.CharField(max_length=24, choices=Activity.TYPE_CHOICES)
    fuel_or_energy_type = models.CharField(max_length=32, blank=True)
    region_code = models.CharField(
        max_length=12, blank=True,
        help_text="ISO2 country code, eGRID subregion, or blank for global.",
    )
    cabin_class = models.CharField(max_length=24, blank=True)
    haul_band = models.CharField(
        max_length=8, blank=True,
        choices=[(HAUL_SHORT, "Short-haul (<3700km)"), (HAUL_LONG, "Long-haul (≥3700km)")],
    )

    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    factor_value = models.DecimalField(max_digits=14, decimal_places=8)
    unit_input = models.CharField(max_length=16)
    unit_output = models.CharField(max_length=16, default="kgCO2e")
    # DEFRA bakes RF into the published number. We split: factor_value is
    # CO2-only; rf_multiplier_applied is recorded separately so the audit
    # disclosure (1.0 ICAO vs 1.7 current DEFRA vs 1.9 older) is explicit.
    rf_multiplier_applied = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Radiative forcing multiplier (aviation only).",
    )
    gwp_basis = models.CharField(max_length=4, default="AR6")
    source_url = models.URLField(max_length=500)
    notes = models.CharField(max_length=400, blank=True)

    class Meta:
        ordering = ["source", "-dataset_version_year", "activity_type", "fuel_or_energy_type"]
        indexes = [
            models.Index(fields=["activity_type", "region_code", "valid_from"]),
        ]

    def __str__(self) -> str:
        bits = [self.source, str(self.dataset_version_year), self.get_activity_type_display()]
        if self.fuel_or_energy_type:
            bits.append(self.fuel_or_energy_type)
        if self.region_code:
            bits.append(self.region_code)
        if self.cabin_class:
            bits.append(self.cabin_class)
        return " · ".join(bits) + f" = {self.factor_value} {self.unit_output}/{self.unit_input}"


# ── Calculated emission (supports dual Scope 2) ─────────────────────────────
class ActivityEmission(models.Model):
    """
    A single calculated CO2e value for an Activity.

    Scope 2 electricity activities have TWO of these rows:
      - method = "location_based"  (grid average via eGRID/national factor)
      - method = "market_based"    (with REC/PPA adjustment; V1 keeps null)

    factor is the FK for queries; factor_value_snapshot is the denormalized
    immutable copy so the record never silently restates if EmissionFactor
    table is later updated.
    """

    METHOD_LOCATION = "location_based"
    METHOD_MARKET = "market_based"
    METHOD_ACTIVITY = "activity_based"
    METHOD_SPEND = "spend_based"
    METHOD_CHOICES = [
        (METHOD_LOCATION, "Location-based"),
        (METHOD_MARKET, "Market-based"),
        (METHOD_ACTIVITY, "Activity-based"),
        (METHOD_SPEND, "Spend-based"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="emissions"
    )
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, null=True, blank=True
    )
    # Snapshots — immutable even if factor row updates later.
    factor_value_snapshot = models.DecimalField(
        max_digits=14, decimal_places=8, null=True, blank=True
    )
    factor_source_snapshot = models.CharField(max_length=120, blank=True)
    rf_multiplier_snapshot = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True
    )

    co2e_kg = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["activity", "method"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "method"],
                name="uniq_activity_method",
            )
        ]


# ── Market-based prep (schema only; V1 doesn't calculate) ───────────────────
class EnergyAttributeCertificate(models.Model):
    INSTRUMENT_REC = "REC"
    INSTRUMENT_GO = "GO"
    INSTRUMENT_PPA = "PPA"
    INSTRUMENT_GREEN_TARIFF = "GREEN_TARIFF"
    INSTRUMENT_CHOICES = [
        (INSTRUMENT_REC, "Renewable Energy Certificate"),
        (INSTRUMENT_GO, "Guarantee of Origin"),
        (INSTRUMENT_PPA, "Power Purchase Agreement"),
        (INSTRUMENT_GREEN_TARIFF, "Green Tariff"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="certificates"
    )
    instrument_type = models.CharField(max_length=20, choices=INSTRUMENT_CHOICES)
    certificate_id = models.CharField(max_length=80)
    mwh_covered = models.DecimalField(max_digits=12, decimal_places=4)
    supplier = models.CharField(max_length=200)
    issue_date = models.DateField()
    retirement_date = models.DateField(null=True, blank=True)
    facility = models.ForeignKey(
        Facility, null=True, blank=True, on_delete=models.SET_NULL,
    )
    supporting_doc = models.FileField(upload_to="eac/%Y/", blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["organization", "-issue_date"]


# ── Review & audit ──────────────────────────────────────────────────────────
class Review(models.Model):
    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"
    ACTION_REQUEST_CHANGES = "request_changes"
    ACTION_CHOICES = [
        (ACTION_APPROVE, "Approve"),
        (ACTION_REJECT, "Reject"),
        (ACTION_REQUEST_CHANGES, "Request changes"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    """Append-only. Every meaningful state change creates one row."""

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="audit_logs"
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    entity_type = models.CharField(max_length=40)
    entity_id = models.CharField(max_length=40)
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["organization", "entity_type", "entity_id"]),
            models.Index(fields=["organization", "timestamp"]),
        ]
