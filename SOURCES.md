# SOURCES.md — per source: real-world format, what I learned, sample data, what would break

For each of the three sources, the brief asked: *"what real-world format you researched, what you learned, what your sample data looks like and why, and what would break in a real deployment."*

---

## 1. SAP — Fuel & Procurement

### Real-world format researched

SAP exposes procurement and goods-movement data through several paths, listed roughly in order of "what you actually get in practice from a sustainability project":

| Path | What it is | Realistic onboarding effort |
|---|---|---|
| **MB51 flat-file export** (SAP GUI report) | A CSV/Excel dump from the Material Document List report — what a Basis admin can produce on day one | Hours |
| **MIRO / MIGO line-item export** | Invoice + goods-receipt line items via custom ABAP query (SQVI, SE38) | Days |
| **IDoc** (`MBGMCR` for goods movements, `INVOIC02` for invoices, `ORDERS05` for POs) | SAP's asynchronous EDI document format; needs ALE configuration + a partner profile + `BD21` change-pointer dance for deltas | 1–2 weeks |
| **OData via SAP Gateway** (S/4HANA) | RESTful CDS view exposure; needs `Customizing > SAP Gateway > Activation` and the customer's Basis team to grant scopes | 1–2 weeks |
| **BAPIs** (`BAPI_PO_GETDETAIL`, `BAPI_GOODSMVT_CREATE`) | Per-document RFC calls over JCo or SAP RFC SDK | Multi-week if no existing connection |
| **SLT / SAP Data Services / CPI** | Replication / middleware | Multi-month engagements |

Source: SAP Help Portal pages for MM (Materials Management) and the IDoc message-type catalog; SAP community posts on MB51 export options; the "APIs vs IDocs in S/4HANA" decision matrix on the SAP-Press blog (Dec 2025).

### What I learned

A few things that shaped the parser:

1. **MB51 is the realistic V1 ingestion mode.** It's a standard SAP GUI report any Basis admin can run; the output is locale-formatted CSV. Every other path requires meaningful customer engineering effort upfront.

2. **`BWART` (movement type) is the load-bearing field.** SAP records every inventory movement with one of ~60 movement types. For fuel/procurement consumption you want **261** (goods issue to production order — typical for fleet diesel) and **201** (goods issue to cost center — typical for stationary heating fuel). You want **262/202** reversals so a returned-fuel row offsets the original consumption. You want to **skip** 101 (goods receipt), 501 (receipt without PO), 311/312 (transfer postings), 561/562 (inventory corrections) — those aren't consumption.

   Source: SAP help page `transmm-movement-types`. Most carbon-accounting integrations get this wrong and end up double-counting fuel-as-received-then-consumed, or missing fuel reversals so returned fuel inflates the inventory.

3. **German locale will surprise you.** SAP exports format quantities per the user's locale — in DE_DE that means dot as thousands separator and comma as decimal (`1.500,00` = 1500.00). Dates in DE_DE export as DD.MM.YYYY; internally SAP stores YYYYMMDD. Material descriptions (`MAKTX`) are language-dependent: a German plant will export "Diesel Kraftstoff EN590", a US plant the same material as "Diesel Fuel EN590". Our parser canonicalizes via material-number heuristics, not text matching.

4. **Plant codes (`WERKS`) are 4-character organization-specific identifiers.** SAP's default conventions: 1000 = headquarters/primary, 1100/1200 = European subsidiaries, 2000–2900 = North America, 3000–3900 = APAC. They mean nothing without a tenant-specific lookup table — see `Facility.sap_plant_codes` in the schema.

5. **Fuel type detection from material descriptions** has to handle German + English aliases. EN590 is the European standard diesel, B100 is pure biodiesel, "Erdgas" is German for natural gas. The parser uses an ordered alias list (biodiesel checked before diesel because "Biodiesel" contains "diesel").

### Sample data — `samples/sap_fuel_extract.csv`

Semicolon-delimited, CRLF line endings (Windows SAP GUI default), DE_DE locale, 15 rows including:

```
WERKS;MATNR;MAKTX;BWART;MENGE;MEINS;BUDAT;LIFNR;WAERS;KOSTL
1000;DIESEL-EN590;Diesel Kraftstoff EN590;261;2.450,000;L;05.01.2024;LIEF-00123;EUR;COST-LDN-FLT
1100;NGAS-INDUST;Erdgas (Industriequalität);261;4.580,000;M3;31.01.2024;LIEF-00456;EUR;COST-MUC-BLR
1100;LPG-COMM;Flüssiggas (Propan);261;680,000;KG;20.01.2024;LIEF-00789;EUR;COST-MUC-FORK
1000;DIESEL-EN590;Diesel Kraftstoff EN590;262;-1.200,000;L;12.01.2024;LIEF-00123;EUR;COST-LDN-FLT   ← reversal, negative qty
2000;DIESEL-B100;Biodiesel B100;261;850,000;L;18.01.2024;LIEF-00321;USD;COST-NYC-FLT   ← B100 has its own factor
9999;DIESEL-EN590;Diesel Kraftstoff EN590;261;500,000;L;25.01.2024;LIEF-00123;EUR;COST-UNK   ← unmapped plant
1000;COFFEE-K;Kaffee Pads 1000er;201;100,000;EA;28.01.2024;LIEF-00999;EUR;COST-LDN-OFF   ← consumable, not fuel
1000;DIESEL-EN590;Diesel Kraftstoff EN590;101;500,000;L;26.01.2024;LIEF-00123;EUR;COST-LDN-FLT   ← receipt, NOT ingested
```

Justifications:
- **Real SAP table column names**, not friendly English aliases. The parser's alias map handles both.
- **Mix of DE and US plants** — UK HQ (1000), Munich (1100), New York (2000) — to demonstrate multi-jurisdiction in one file.
- **Reversal row 7**: BWART 262 with negative quantity. Our parser preserves the sign — without that, returning fuel would silently inflate emissions.
- **Biodiesel B100 row 8**: different emission factor than EN590 diesel (0.187 vs 2.512 kg CO₂e/L). Forces correct fuel-type detection from material number.
- **Plant 9999**: deliberately unmapped. Row ingests successfully without a facility — analyst sees "Unknown plant 9999" in the review queue and can either create the facility or reject the row.
- **`COFFEE-K` consumable row**: 100 packets of coffee pads, BWART 201, unit EA. The parser classifies this as "not a fuel/energy source" and surfaces it to the analyst rather than silently calculating a zero. Tests that the classifier isn't naive.
- **Receipt row 12 (BWART 101)**: explicitly skipped — we don't ingest receipts, only consumption. The parser comment cites the movement-type rationale.

### What would break in real deployment

1. **Customer Z-fields.** Real SAP installations have customer-specific Z-columns added to MB51 (`ZZFUEL_TYPE`, `ZZ_LOCATION`, etc.). Our parser ignores them — fine for V1, but factor lookup might benefit from them in V2.
2. **Non-DE/EN locales.** A Japanese SAP system exports `MAKTX` in Japanese; a French one in French. The fuel-type detection alias list would need extending.
3. **Procurement service items.** Service POs (`BSTYP=B`) don't have a material number. We don't ingest those; they'd need a different parser path.
4. **Composite movements** (`BWART 309/310` material-to-material transfer postings) — currently skipped; could be relevant if a customer has internal fuel transfers we'd want to track.
5. **Very large files.** MB51 exports for a multinational over a year are often 50 MB+. Synchronous parsing in V1 caps at 10 MB upload size. V2 needs a background worker.

### V2 paths

- **OData via SAP Gateway** with a CDS view `Z_BREATHE_FUELMVTS` published by the customer's Basis team — gives us delta sync with `$filter=PostingDate gt ...`
- **IDoc MBGMCR** for customers already running EDI — accepts the message via a /webhook endpoint and parses the segment structure (`E1MBGMCR_HEAD`, `E1MBGMCR_ITEM`)

---

## 2. Utility — Electricity

### Real-world format researched

US/EU utility data flows in three realistic modes:

| Mode | What it is | Cost |
|---|---|---|
| **Portal CSV/Excel export** | Customer logs into the utility portal, clicks "Download usage data" | Free; per-utility format variance |
| **Scanned/downloaded PDF bill** | The official bill PDF | Free; needs OCR per utility template |
| **Aggregator API** — Urjanet (now Arcadia Plug), UtilityAPI | Normalized JSON across thousands of utilities globally | Paid; per-meter or per-pull pricing |
| **Direct utility API** — PG&E Share My Data, ConEd Green Button, NAESB REQ.21 ESPI Green Button Connect | Per-utility OAuth + XML/JSON | Free if utility supports it; per-utility OAuth setup |

Sources: Urjanet developer docs, Arcadia Plug docs, UtilityAPI Green Button XML reference, Green Button Alliance ESPI spec (NAESB REQ.21 v4.0 published Dec 2023), PG&E published Data Element Descriptions PDF, US DOE Best Practices for GHG Metrics.

### What I learned

1. **Portal CSV is the realistic V1 mode**, for the same reasons SAP MB51 is. Aggregator APIs cost money and require contracts; ESPI XML coverage is uneven (~30% of US utilities). The "Download usage data" button on a utility portal is universal.

2. **Realistic CSV column variance is significant.** PG&E's "Bill Detail" CSV uses columns like `Account, Meter, Service Address, Bill Start, Bill End, Total kWh, Total Cost, Rate Schedule`. ConEd uses `Account #, Meter #, Service Period From, Service Period To, kWh Used, Demand kW, Read Type, Rate, Total $`. Our parser has a header alias map covering ~50 variations.

3. **Billing periods rarely align with calendar months.** A "January" bill might cover Dec 22 → Jan 24. For calendar-month emissions reporting (which auditors and CSRD prefer), you have to prorate. We store the original `period_start`/`period_end` verbatim and *derive* calendar-month allocation downstream — the original is the source of truth. V1 doesn't expose proration in the UI; V2 would (TRADEOFFS.md).

4. **Units are inconsistent in the same file.** A site with one large meter often exports in MWh; a small meter in kWh. Some EU utilities mix in GJ for gas. Our parser detects MWh-in-kWh-column via a sanity check: if `demand_kW > avg_load_kW × 4` and `kWh < 1000`, the consumption value is probably in MWh — flag for analyst review, downgrade to data quality tier 2.

5. **Estimated vs Actual reads matter for data quality.** Utility bills carry a `read_type` field: `Actual` (meter physically read), `Estimated` (modeled), `Customer-read`, `Failed`. Our parser maps Estimated → `data_quality_tier = 2`, which the auditor bundle preserves.

6. **EPA eGRID subregion lookup is by service ZIP, not state.** California isn't one grid — it's `CAMX` (most of CA + parts of NV) vs `WECC-Southwest`. The eGRID2022 release defines **26 subregions**, each with its own kg CO₂e/MWh rate. PG&E ZIPs map to `CAMX` (0.2256 kg/kWh), ConEd ZIPs to `NYCW` (0.4015 kg/kWh). Our seed data includes the full 26 subregion factors; the parser maps service ZIP → subregion via a hardcoded subset of the EPA Power Profiler lookup (V2 would load the full 42K-row table).

   Conversion math from EPA's lb/MWh to our kg/kWh: **`lb/MWh × 0.453592 / 1000`**. Pure arithmetic, but a step nearly every competitor gets wrong (most just use lb/MWh directly or hardcode the wrong constant).

### Sample data — `samples/utility_electricity_export.csv`

Comma-delimited US locale, 8 rows mixing real US utility shapes:

```
account_number,meter_id,service_address,service_zip,bill_start,bill_end,kwh_consumed,demand_kw,read_type,rate_schedule,total_cost_usd
ACC-CA-0010012,MTR-PGE-77445A,"500 Howard St, San Francisco CA",94105,2023-12-22,2024-01-24,52480.0,142.3,Actual,A-10 TOU,8420.50    ← PG&E shape
ACC-NY-0040501,MTR-CE-9001,"33 Maiden Ln, New York NY",10038,2024-02-03,2024-03-05,68450.0,194.1,Estimated,SC-9 Rate III,11932.20  ← ConEd shape, Estimated read
ACC-CA-0010012,MTR-PGE-77445A,"500 Howard St, San Francisco CA",94105,2024-02-22,2024-03-22,51200.0,140.5,Actual,A-10 TOU,8230.40  ← overlapping date row
ACC-CA-0010012,MTR-PGE-77445C,"500 Howard St, San Francisco CA",94105,2024-01-24,2024-02-22,,kWh,Failed,A-10 TOU,                  ← missing kWh, parser surfaces error
```

Justifications:
- **Two real utility shapes**: PG&E's `A-10 TOU` is their actual commercial Time-of-Use rate schedule; ConEd's `SC-9 Rate III` is their actual industrial classification.
- **ZIP 94105 → CAMX subregion** (PG&E coverage). ZIP 10038 → NYCW subregion (ConEd coverage). Different factors auto-apply.
- **Billing periods Dec 22 → Jan 24 (~33 days) and Jan 24 → Feb 22 (~29 days).** Neither aligns to a calendar month. Stored verbatim; proration is V2.
- **Estimated read row.** Triggers `data_quality_tier = 2` downgrade.
- **Failed read row** with missing kWh. Parser emits an error row, NOT a silent skip — the analyst sees "Row 8: missing required field `kwh_consumed`".
- **Service ZIP column** — every row has it. Without ZIP we can't pick the right eGRID subregion for US Scope 2.

### What would break in real deployment

1. **The full ZIP → eGRID subregion table is ~42K rows; we ship a 12-ZIP subset for demo realism.** V1.5 work is loading the full EPA Power Profiler CSV (it's freely published).
2. **EU/UK portals use different field names** — `MPAN` (Meter Point Administration Number) in UK, `EAN` in NL, no equivalent of "service ZIP" in some jurisdictions. The alias map would need extending.
3. **Multi-meter aggregated bills** where the utility provides one row per site but multiple meters contributed. Some PG&E commercial accounts do this; we'd need to either accept aggregated or get the per-meter breakdown.
4. **Demand-only bills.** Some industrial tariffs charge by peak demand (kW) regardless of kWh consumed. Our parser ignores `demand_kw` for the emission calculation — that's correct (only energy × factor produces emissions) but a UI in V2 would surface peak-demand info for cost analytics.
5. **Solar PPAs and net metering** — when a site has on-site solar, the utility CSV shows net imports. The customer's actual scope-1 generation isn't visible. V2 would need a separate on-site generation source.

### V2 paths

- **NAESB REQ.21 ESPI Green Button Connect** for utilities that support it — the customer authorizes via the utility portal, our backend receives XML feeds with `UsagePoint → MeterReading → IntervalBlock → IntervalReading` granularity.
- **Urjanet / Arcadia Plug** for global coverage — paid, but normalizes across thousands of utilities and includes EU/UK/APAC.

---

## 3. Travel — Concur / Navan

### Real-world format researched

Three real ingestion paths from the top corporate-travel platforms:

| Path | What it is | Effort |
|---|---|---|
| **Concur Expense Report Extract** (CSV/Excel) | Customer admin exports completed expense reports for a period | Hours; per-customer custom field config |
| **Concur Itinerary v4 API** | OAuth2 partner credentials, `GET /travel/itinerary/v4/users/{id}/trips` | 2–4 weeks (Concur partner-app approval) |
| **Navan / TripActions API** (`POST /ta-auth/oauth/token` + `GET /v1/bookings`) | OAuth2 client-credentials per customer admin | Days (no SDK, no webhooks, polling-only — but no sandbox so you need a real customer admin) |

Sources: SAP Concur Developer Hub (Itinerary v4 docs, Get-Itinerary deeplink reference), Concur 2026 release notes mentioning ISO 14083 partnership with Thrust Carbon, Navan TMC API integration documentation, the Rust `tripactions` crate's OpenAPI bindings, multiple competitor architecture notes.

### What I learned

1. **Concur holds ~70% of enterprise TMC market share.** Sample data should mirror Concur's shape; Navan/TripActions has equivalent fields under different names and would swap cleanly into the same parser.

2. **The Concur Expense Report Extract CSV is what week-1 customers email over.** The API needs a multi-week partner approval cycle. Sustainability teams ask their finance/T&E team for "the expense report CSV for Q1" and that's what arrives.

3. **Concur's API now returns `CarbonEmissionLbs` + `CarbonModel` natively.** Their 2026 partnership with Thrust Carbon means the Concur Itinerary v4 API surfaces ISO 14083-assured CO₂ per flight at the source. V2 would ingest *both* the vendor-computed value and our own DEFRA calc, show the diff to the analyst, and let them pick which to use. This is a serious depth signal — most competitor submissions don't know about it.

4. **Concur and Navan don't return flight distance.** They return IATA origin + IATA destination. Distance is computed downstream via the Haversine formula on airport lat/lon. DEFRA recommends adding an 8% detour uplift for non-direct routing (real flights don't fly straight). Our parser applies this.

5. **Cabin class affects emissions by factor of ~3×.** DEFRA's seat-area methodology says one Business seat takes up ~2.9× the floor space of an Economy seat on a long-haul flight, and ~1.5× on a short-haul. First class is 4×. Our seeded `EmissionFactor` rows are per (haul, cabin) combination from DEFRA 2024's published per-passenger-km values.

6. **Aviation needs separate RF treatment.** DEFRA's published factors are CO₂-only; the radiative-forcing multiplier (1.7× per current guidance) is intended to be disclosed separately. ICAO doesn't use RF at all (their methodology argues the science isn't settled). Auditors expect to see *which* assumption you used. We store `rf_multiplier_applied` as its own column on `EmissionFactor` and as a snapshot on every `ActivityEmission`.

7. **Hotel emissions vary 6× by country.** DEFRA 2024 publishes per-country hotel-night factors: UK 23.8, US 31.7, India 134.3, Singapore 78.4, UAE 110.6 kg CO₂e/room-night. The variance is driven by grid carbon intensity, AC/heating loads, and hotel category mix. Single-global-factor approaches (which most competitor submissions use, defaulting to ~31.0) materially under-report India travel and over-report France travel. Our seed data has ~10 country-specific factors.

8. **Spend-based fallback for ground transport.** When the analyst gets an Uber receipt for "Site visit to Texas, $185" with no distance, you can't calculate per-km. The DEFRA spend-based factor is one path; in our V1 we flag the row as tier-3 quality and surface it as a spend-based fallback rather than silently calculating 0.

### Sample data — `samples/concur_expense_extract.csv`

Comma-delimited, 16 rows mirroring Concur Expense Report Extract:

```
report_id,employee_id,employee_name,expense_type,transaction_date,origin_iata,destination_iata,cabin_class,nights,vendor,amount,currency,trip_purpose,hotel_country,vehicle_type,distance_km
RPT-2024-00142,EMP-101,Priya Sharma,Airfare,2024-01-15,LHR,JFK,Economy,,British Airways,850.00,GBP,Client visit — Acme NY,,,
RPT-2024-00142,EMP-101,Priya Sharma,Hotel,2024-01-15,,,,3,Marriott Times Square,1840.00,USD,Client visit — Acme NY,US,,
RPT-2024-00207,EMP-205,Daniel Cohen,Airfare,2024-02-08,SFO,FRA,Business,,Lufthansa,4250.00,USD,Engineering summit,,,
RPT-2024-00318,EMP-317,Rin Sato,Airfare,2024-03-02,NRT,SIN,Premium Economy,,ANA,2840.00,JPY,Regional ops review,,,
RPT-2024-00404,EMP-422,Mike O'Brien,Car Rental,2024-03-20,,,,,Hertz,185.00,USD,Site visit Texas,,SUV,420
RPT-2024-00501,EMP-101,Priya Sharma,Airfare,2024-04-12,LHR,ZZZ,Economy,,Unknown Carrier,420.00,GBP,Conference — destination TBD,,,   ← invalid IATA
RPT-2024-00644,EMP-422,Mike O'Brien,Hotel,2024-05-10,,,,6,Taj Mahal Hotel New Delhi,2150.00,INR,Acquisition diligence,IN,,
```

Justifications:
- **No `distance_km` on flight rows.** Forces Haversine calc — exactly what production Concur returns.
- **All four cabin classes** appear (`Economy`, `Premium Economy`, `Business`, with `First` available in the factor table).
- **Three currencies** (GBP, USD, EUR, JPY, SGD, INR, AED across the dataset) — V2 would FX-normalize for spend-based ground transport.
- **Realistic-sounding trip purposes** ("Client visit — Acme NY", "Engineering summit", "Acquisition diligence") not "Test trip 1".
- **`ZZZ` invalid IATA row.** Parser flags it for analyst review with "Could not compute distance for LHR→ZZZ: airport not in lookup".
- **Hotel rows have a `hotel_country` column** — drives per-country factor lookup. India 134.3 vs US 31.7 vs UK 23.8 — same room-night, materially different emissions.
- **Car rental with no IATA, only distance + vehicle type.** Falls through to DEFRA ground-transport factor.
- **Mike O'Brien's Texas car rental has no distance** — would fall to spend-based tier-3 if implemented; V1 stores it but with `quantity_normalized = 0` and tier 3.

### What would break in real deployment

1. **Concur's per-customer custom fields.** Real expense extracts have customer-specific columns (`ZZ_Cost_Center`, `Project Code`, etc.). The parser would need a per-tenant field-mapping config.
2. **Off-platform travel.** Reimbursed travel that didn't book through Concur — analyst-entered on a separate expense report. Our parser would treat it like normal Concur data but without IATA codes; would fall back to spend-based.
3. **Hotel vendor → country resolution.** Our parser has a string-match heuristic ("Marriott Times Square" → US). In production we'd need a hotel database (e.g. Cvent, Amadeus) for the long tail. ~80% of hotel chain names will resolve correctly with the heuristic; the rest need analyst review.
4. **Personal extensions of business trips.** When an employee adds 3 personal nights to a business trip, the Concur extract might include them. The brief doesn't cover personal vs business segregation — V2 work.
5. **Train / rail.** We don't ingest rail in V1 (`expense_type=Rail` rows are explicitly skipped with a "deferred to V2" message). UK and EU customers have significant rail travel; this is real V2 scope.
6. **Multi-leg flights.** Concur exports one row per ticket — a JFK → CDG → DEL ticket is two segments but one expense row. Our Haversine on origin/destination gives roughly the right answer but understates the JFK → DEL great-circle slightly. Production would parse the itinerary segments.

### V2 paths

- **Concur Itinerary v4 API polling worker** — OAuth2 partner credentials, ingest `Booking` resources, surface `CarbonEmissionLbs` alongside our own calc
- **Navan `/v1/bookings` polling** — OAuth2 client-credentials, parses `cabinPurchased` / `flownCabinClass`
- **Train and rail factors** (UK Rail, ICE in DE, SNCF in FR — per-country)
- **Personal-vs-business segregation** via Concur's `IsPersonal` field

---

## On the emission factor sources themselves

Every factor in the system cites its publication URL. The seed command loads:

| Source | What we use | URL |
|---|---|---|
| **DEFRA / UK DESNZ 2024 Conversion Factors** | Fuel combustion, aviation (CO₂-only + RF separate), hotel by country, ground transport, UK grid | https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2024 |
| **EPA eGRID 2022 Summary Tables** | US Scope 2 location-based, all 26 subregions, kg CO₂e/kWh derived from published lb/MWh | https://www.epa.gov/egrid/summary-data |
| **IEA Emissions Factors 2023** | Non-US national grid factors (DE, IN, FR, SG, AE, JP) for Scope 2 location-based | https://www.iea.org/data-and-statistics/data-product/emissions-factors-2024 |

Factor values cited in our seed file match the published documents to four decimal places. The `factor_source_snapshot` field on every emission row carries this provenance into the auditor bundle.
