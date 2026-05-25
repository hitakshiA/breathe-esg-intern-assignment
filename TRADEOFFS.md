# TRADEOFFS.md — three things I deliberately did not build

Per the brief: *"Three things you deliberately did not build and why."*

These are real omissions, not vague hand-waves. Each one has a concrete reason that maps to "less but defensible beats more but unexplainable."

---

## 1. Live API integrations to Concur, Navan, SAP, and utility data aggregators

### What I didn't build

Continuous polling/webhook ingestion from:
- **SAP Itinerary / S/4HANA OData services**, IDoc MBGMCR over ALE, or BAPI_PO_GETDETAIL
- **Concur Itinerary v4 API** (which would also surface their ISO 14083-assured `CarbonEmissionLbs` field via the Thrust Carbon partnership — meaning we could ingest vendor-computed CO₂ and show the diff vs our own DEFRA calc)
- **Navan / TripActions `/v1/bookings` API** (OAuth2 client-credentials)
- **Urjanet / Arcadia Plug**, UtilityAPI, or NAESB REQ.21 ESPI Green Button Connect XML for utility electricity

### Why

The Concur partner OAuth flow alone is a multi-week procurement engagement (Concur app review, customer admin approval, scope grants). Navan's API is unsandboxed — you need a real customer-admin to generate client credentials before you can write a single line. SAP Gateway needs the customer's Basis team to activate the catalog service for OData; IDoc/ALE setup adds ~2 weeks of EDI configuration. Urjanet and Arcadia are paid integrations with onboarding contracts.

For a 4-day prototype, none of these are feasibly built well. Building them *badly* — fake "API mode" toggle, half-mocked OAuth, no real retry/idempotency — would have been worse than not building them.

### What I built instead

CSV upload covers what the facilities team actually emails over in week one of onboarding (the brief's exact language: *"electricity data their facilities team pulls from utility portals"*). The data model is API-shaped — parsers take a file-like object, and a future `pull_concur` or `pull_navan` worker would call the same `ingest_file` orchestration with a streamed CSV-ish payload. No schema change needed.

### What I'd build in V2 (1–2 weeks)

- **Concur Itinerary v4 polling worker** — Celery task, every 6h, `last_modified` filter, OAuth2 partner credentials per tenant. Ingest the `CarbonEmissionLbs` field as `Activity.vendor_co2e_kg` alongside our own calc and surface the diff to the analyst.
- **Navan `/v1/bookings` polling** — same pattern, `createdFrom`/`createdTo` cursor.
- **UtilityAPI Green Button OAuth + ESPI XML parser** — for the utilities that support NAESB REQ.21.
- **SAP OData via Gateway** when the customer's Basis team activates the service.

The `ActivityEmission.factor_source_snapshot` field already supports the "vendor-reported vs our calc" distinction. The schema is ready; the integration work isn't.

---

## 2. PDF utility bill OCR

### What I didn't build

OCR-based extraction from scanned or downloaded utility PDFs. The brief mentions this as one of three realistic utility ingestion modes ("a portal CSV export, a PDF bill, an API if the utility offers one").

### Why

Per-utility layout templates plus per-field confidence-scored extraction is multi-week template engineering. There are ~200 US utilities with distinct bill formats; UK has ~30; EU is country-by-country. Tools like `utilitybillocr.com`, Veryfi, and Lido publish that they need 50–200 labelled examples per utility before extraction confidence crosses 90%.

Even at 90% confidence, every extracted field needs an analyst-review queue for the ~10% wrong reads — which is itself a feature I'd have to design (confidence threshold UI, side-by-side PDF preview, manual override flow).

In 4 days, building this badly would mean:
- Tesseract OCR with generic prompts → extraction quality wildly variable per utility
- No confidence scoring → analyst can't tell when to trust it
- No template tuning → fails on the second utility tried
- Hard to demo cleanly → looks broken in the worst possible way

A worse outcome than not having the feature at all.

### What I built instead

Hard-fail PDFs with a clear analyst-facing error. The upload endpoint returns `415 Unsupported Media Type` with the message *"PDF ingestion is not supported in V1 — please export the portal CSV. Roadmap: utility-specific OCR templates planned for V2."* Documented as a deferred path in this file and in SOURCES.md.

### What I'd build in V2 (2–4 weeks per utility cohort)

- **First**: integrate Urjanet / Arcadia Plug for the customer's existing utility accounts. That moves ~80% of US bills out of PDF-OCR scope and into structured API ingestion.
- **For utilities not on Urjanet**: per-utility layout templates with confidence scoring. Start with the customer's top 3 utilities by bill count.
- **Confidence threshold UI**: bills below a tunable threshold go to a manual-extraction queue rather than auto-creating activities with bad data.
- **Side-by-side PDF preview** in the review pane so the analyst can verify any auto-extracted field.

---

## 3. Market-based Scope 2 calculation

### What I didn't build

The market-based Scope 2 *calculation*. I did build:
- The `EnergyAttributeCertificate` model (REC, Guarantee of Origin, PPA, Green Tariff) with all the fields auditors expect
- The `ActivityEmission.method = "market_based"` slot — every Scope 2 electricity activity has a (currently empty) market-based row alongside the location-based one
- The Report dashboard showing the market-based KPI as "pending V2 calc · N rows"

What's missing is the calc itself.

### Why

The GHG Protocol Scope 2 Guidance §7 "Quality Criteria for contractual instruments" defines the validation that turns a REC/PPA into a legitimate market-based emission reduction. There are five quality criteria:

1. Conveyed unique claims (cert can only be retired once, must be tracked to a registry)
2. Tracked and redeemed within the reporting year
3. Issued and retired as close as possible to the consumption period
4. Sourced from the same market in which the operation occurs
5. Vintage matching with the reporting period

Each of these is a validator on the EAC record. Geographic proximity check needs a market-region taxonomy (NERC region in the US, country-level in EU, more granular for some markets). Vintage matching needs date-window logic against the consumption period. Tracking unique retirement requires integration with M-RETS, ERCOT REC tracking, EUGO, or whichever registry issued the cert.

Doing this *badly* in V1 — accepting any REC the analyst uploads, applying it to any kWh, ignoring vintage — would produce numbers an auditor would reject. The GHG Protocol calls out exactly this failure mode as "double-counting of zero-emission claims" and it's one of the most-cited reasons assurance opinions get qualified.

**Doing it badly is worse than not doing it.**

### What I built instead

The schema is correct. The EAC table accepts the certificate. The dual-emission row exists. The UI shows `Scope 2 (market): pending V2 calc · 7 rows`. An auditor sees that we know dual reporting is required, that we know contractual instruments are how market-based works, and that we declined to publish numbers we couldn't yet validate. That's a much better story than a broken calc.

### What I'd build in V2 (1 week)

- **Quality Criteria validator** as a single Django service that takes a `(Facility, ReportingPeriod, EnergyAttributeCertificate)` tuple and returns `(is_valid, reasons[])`
- **Market-region taxonomy seed** — NERC subregions, EU country, etc. Validates the geographic proximity criterion.
- **Vintage window** — `EAC.issue_date` and `retirement_date` against `Activity.period_start/period_end` per the GHG Protocol's "same reporting year" requirement.
- **Supplier-specific factor lookup** — when the cert covers a portion of consumption, the remainder uses the residual mix factor, not the grid average.
- **REC tracking registry integration** (M-RETS, EUGO, etc.) — V2.5 work, expensive.

The calc itself once validators pass is straightforward: `co2e_market = (kWh - covered_kWh) × residual_factor + covered_kWh × cert_supplier_factor`. The validators are 80% of the engineering.

---

## Honorable mentions (not formally "the three" but worth flagging)

These are smaller items I considered and chose to defer:

- **`ReportingPeriod` + `EmissionsSnapshot` tables.** For proper restatement audit when DEFRA refreshes factors. Row-level `is_locked` covers V1 needs.
- **PostgreSQL row-level security policies** as defense-in-depth on top of queryset-level org filtering. Considered overkill for prototype.
- **Background-task queue (Celery + Redis).** All ingestion is synchronous in V1 — adequate for CSVs under 10 MB. V2 if customers upload larger files.
- **Multi-step approval workflow** (analyst → senior analyst → manager). One-level sign-off in V1; the schema would support adding required approval-stage records without migration.
- **The other 14 Scope 3 categories** beyond Cat 6. Cat 1 (Purchased Goods, spend-based via USEEIO) is the obvious next.
- **Dark mode.** No.
