# MODEL.md — Data model

> Single load-bearing question: **can an auditor reconstruct exactly how every reported number was derived, even after the factor tables update?**
> Everything in this schema is here because the answer to that has to be yes.

## At a glance

```
Organization                             ← tenant
└── User                                 ← analyst/admin/viewer
└── Facility                             ← carries eGRID subregion + SAP plant codes

IngestionBatch                           ← one upload session, file_sha256
└── RawRow                               ← verbatim payload, row_sha256 (UNIQUE per org)
    └── Activity                         ← canonical normalized row
        └── ActivityEmission             ← one per method (dual Scope 2!)
              └── EmissionFactor (FK)    ← versioned, with valid_from/valid_to
              └── factor_value_snapshot  ← denormalized copy for immutability

EnergyAttributeCertificate               ← REC/PPA records (market-based Scope 2 prep)
Review                                   ← analyst sign-off action
AuditLog                                 ← append-only event log
```

Eleven models. Every one is here because something in the brief — or in real ESG audit practice — required it.

## The three layers

### 1. Raw layer (immutable)

`IngestionBatch` + `RawRow` store every uploaded file and every row of it, *verbatim*, before any normalisation.

The `RawRow` table has a hard-enforced unique constraint on `(organization_id, row_sha256)`. Re-uploading the same CSV — or two CSVs with overlapping date ranges — produces **zero new rows**, with the duplicate count surfaced to the analyst. This is visible in the UI and in `IngestionBatch.duplicate_count`.

Why a row-level hash and not just a file-level one? Facilities teams routinely re-export portal data with overlapping windows. File hash would let those duplicates through; row hash catches them.

The raw payload is stored as JSON, preserving original column names and original values byte-for-byte. An auditor can always go back from the canonical activity row through `Activity.raw_row → RawRow.raw_data` and see what the source CSV said before we touched it.

### 2. Canonical activity layer

`Activity` is the single normalised representation of every emission-generating event, regardless of source system. It carries:

- **Scope** (`1` | `2` | `3`) and **scope3_category** (1..15; we populate `6` for business travel)
- **`activity_type`** — one of: `fuel_combustion`, `electricity`, `air_travel`, `hotel_stay`, `ground_transport`
- **Both quantities** — `quantity_original` + `unit_original` straight from the source, and `quantity_normalized` + `unit_normalized` after conversion. The original never gets overwritten.
- **`period_start`, `period_end`** — every activity is a span, even if it's a single day. Billing-period vs calendar-month proration becomes possible downstream without losing the source period.
- **`facility`** (optional FK) — resolved at ingest from the SAP plant code or the utility service ZIP
- **`data_quality_tier`** — `1` (actual measurement), `2` (derived, e.g. Haversine distance), `3` (estimated/spend-based). Per the GHG Protocol methodology hierarchy. Tiers are never silently mixed in totals.
- **`review_status`** state machine — `draft → under_review → approved | rejected` — drives the analyst dashboard
- **`is_locked`** — once an activity is part of a closed reporting period, this turns true and the row is immutable
- **`flags`** JSON — auto-detected anomalies surfaced by the parser (e.g. "BWART 262 reversal with positive quantity")

### 3. Calculation layer

`EmissionFactor` is a versioned reference table, seeded from canonical published sources (DEFRA 2024, EPA eGRID 2022, IEA 2023). Every row has:

- `source`, `dataset_version_year`, and a **`source_url`** that cites the published methodology page — not optional
- `valid_from` / `valid_to` for temporal lookups
- `rf_multiplier_applied` **stored separately from the factor value** for aviation. DEFRA bakes RF into its published aviation rates; we don't. Storing 1.7× as its own field lets us disclose which RF assumption was used (1.0 ICAO / 1.7 current DEFRA / 1.9 older DEFRA) — exactly what auditors ask about. Cited in our SOURCES.md from DEFRA's 2024 methodology paper §4.3.

`ActivityEmission` is where the calculation lives. It has two crucial properties:

#### Dual Scope 2 reporting

Every Scope 2 electricity activity gets **two** `ActivityEmission` rows:

```
method = "location_based"   ← computed in V1 (eGRID subregion or national grid)
method = "market_based"     ← schema slot present, value null in V1
```

This matches GHG Protocol Scope 2 Guidance §6.1 which mandates dual reporting when contractual instruments exist. Almost no competitor submission models this — most have a single `co2e_kg` column.

#### Factor snapshotting

Each `ActivityEmission` carries both:

- a **foreign key** to `EmissionFactor` (for normal queries like "show every record using DEFRA 2024")
- a **denormalized snapshot** — `factor_value_snapshot`, `factor_source_snapshot`, `rf_multiplier_snapshot` — that is *immutable*

If DEFRA publishes their 2026 update, we insert new factor rows; we *never* mutate the 2024 rows, and even if we did, the snapshot on every prior `ActivityEmission` would still show what was used. An approved emission figure can never be silently restated.

## Multi-tenancy

Shared schema, row-level filtering via `organization_id` foreign key on every model.

Chosen over `django-tenants`/schema-per-tenant because at prototype scale the schema-per-tenant pattern is operationally heavy: migrations run per-schema, connection management is more complex, and cross-tenant analytics need foreign data wrappers or ETL. Shared schema gets us to working in hours instead of days, and isolation is enforced by a single `_OrgScopedMixin` on every viewset that filters `organization=request.user.organization`.

**Migration path to schema-per-tenant** when enterprise customers require it:
1. Add `django-tenants` to `SHARED_APPS` and `TENANT_APPS`
2. The `Organization` model becomes the tenant model
3. Migrations + tenant-aware management commands per [django-tenants docs](https://django-tenants.readthedocs.io/)
4. The `organization_id` FK on every model becomes redundant (search_path scopes the queries) and can be dropped over two deploys

PostgreSQL row-level security was considered as defense-in-depth on top of the queryset mixin, and deferred to V2.

## Source-of-truth tracking

Every approved emission row can be reconstructed from raw bytes. The chain is:

```
ActivityEmission.factor_value_snapshot, factor_source_snapshot
  ↑  references which factor was applied
Activity (canonical, quantity_normalized × factor_value_snapshot = co2e_kg)
  ↑  raw_row FK
RawRow.raw_data  (verbatim JSON of the source row)
  ↑  batch FK + row_sha256
IngestionBatch.file_sha256, file_name, uploaded_by, uploaded_at
```

The auditor bundle CSV export walks this exact chain and produces 26 columns per emission, including `raw_row_sha256` and `source_file_sha256`. Every reported tonne can be reconstructed.

## Audit trail

`AuditLog` is append-only, written from a single helper (`api/audit.py`) on every meaningful state change: ingest start, ingest complete, review approve, review reject, lock. Each row stores:

- `entity_type` + `entity_id` (e.g. `Activity` + UUID)
- `action` (e.g. `review.approve`, `ingest.complete`)
- `before` and `after` JSON snapshots
- `user`, `ip`, `user_agent`, `timestamp`

The brief explicitly grades audit trail. ISAE 3000 (Revised), AA1000AS v3, and the upcoming ISSA 5000 (effective Dec 2026) all require the same thing: an auditor must be able to reconstruct any reported metric's derivation and reach the actor + time of every modification. This table supports that.

The `Review` model is separate from `AuditLog` because reviews are a domain artifact the analyst interacts with directly (the queue shows "last 3 reviews"), whereas `AuditLog` is the technical evidence trail that lives in the auditor bundle.

## Unit normalization

Source data arrives in mixed units; canonical units per activity_type are stable:

| Activity type | Canonical unit |
|---|---|
| `fuel_combustion` (diesel/petrol/biodiesel/jet) | `L` (litres) |
| `fuel_combustion` (natural_gas) | `M3` |
| `fuel_combustion` (lpg) | `KG` |
| `electricity` | `kWh` |
| `air_travel` | `p.km` (passenger-kilometres) |
| `hotel_stay` | `room-night` |
| `ground_transport` | `km` |

Conversion happens in the source-specific parsers. `Activity.quantity_original` + `unit_original` always preserve the original — `Activity.quantity_normalized` is post-conversion. The factor lookup keys off the canonical unit.

Specific conversions implemented:

- **MWh → kWh** when a utility row exports in MWh (auto-detected by magnitude / column header)
- **German decimal comma → ISO decimal point** (`1.500,00` → `1500.00`) for SAP CSVs in DE_DE locale
- **lb CO₂e/MWh → kg CO₂e/kWh** for EPA eGRID factors (× 0.453592 / 1000)
- **Great-circle distance via Haversine + 8% detour uplift** for flights with no distance column (DEFRA's recommended uplift for non-direct routing)

## What this model does *not* try to be

- It does **not** model all 14 other Scope 3 categories. Only Cat 6 (business travel). The brief asked for the three sources we ingest, not a full Scope 3 inventory.
- It does **not** carry a `ReportingPeriod` table. The brief mentioned "approve rows before they're locked for audit" — a row-level `is_locked` flag suffices for that. Period-locked snapshots for proper restatement (when DEFRA refreshes) are a V2 concern, called out in TRADEOFFS.md.
- It does **not** compute market-based Scope 2. The schema slot is there (`ActivityEmission.method = "market_based"`) and the contractual instrument is modelled (`EnergyAttributeCertificate`), but the GHG Protocol Quality Criteria validator (ownership, retirement period, supplier proximity) is deferred. See TRADEOFFS.md.
- It does **not** support multiple consolidation approaches in V1. `Organization.consolidation_approach` is a field so the data model is correct on day one, but every demo activity is treated as operational-control. Equity-share rollups would change `Activity → Facility → Organization` weighting, V2 work.

## Indexes

The hot paths are filtering activities by `(organization, review_status)` for the queue view, by `(organization, scope)` for the summary, by `(organization, period_start)` for date-range slicing. Indexes are declared on each.

`RawRow.row_sha256` is indexed and unique-constrained per organization — that's the dedup contract, and it has to be fast.
