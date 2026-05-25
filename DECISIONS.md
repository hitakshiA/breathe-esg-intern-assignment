# DECISIONS.md — ambiguities resolved

Format for each entry:
1. **What the brief said** (or didn't)
2. **What I'd have asked the PM** in a real engagement
3. **What I assumed and why**

---

### Q1. Which jurisdiction is the primary client, and which disclosure framework do they ultimately report under?

**Brief:** silent. The PM scenario just says "a new enterprise client".

**Would ask:** *"Are they CSRD-bound (EU large companies, mandatory now), California SB 253 (US, $1B+ revenue, 2026), CDP voluntary, or India BRSR? Each has different mandatory categories and different verification thresholds (limited vs reasonable assurance)."*

**Assumed:** GHG Protocol Corporate Standard as the universal baseline — every named framework above accepts a GHG Protocol-aligned inventory. Demo data spreads across UK HQ (DEFRA), US operations (EPA eGRID), and a DE subsidiary (DEFRA/IEA) — the three jurisdictions a real multinational like Bosch or Embassy has. `Organization.disclosure_framework` field is in the schema so V2 can validate per-framework mandatory categories.

---

### Q2. Which subset of the 15 Scope 3 categories?

**Brief:** mentions "business travel" explicitly; doesn't say anything about the rest.

**Would ask:** *"For V1, are we only doing Cat 6 (business travel), or also Cat 1 (purchased goods — the spend-based 80% of most companies' Scope 3)? Cat 1 would re-use the SAP procurement export but with an EEIO / USEEIO factor mapping by NAICS code."*

**Assumed:** Cat 6 only. The brief calls out business travel; spend-based Cat 1 would mean adding a NAICS taxonomy + a separate factor source (USEEIO / EXIOBASE) and a different methodology defense in the Q&A. Out of scope for a 4-day prototype. SAP procurement rows that *aren't* fuel get classified by the parser as "not a Scope 1/2/3 source" and surfaced to the analyst (see the `COFFEE-K` row in the sample data).

---

### Q3. Consolidation approach — operational control, financial control, or equity share?

**Brief:** silent.

**Would ask:** *"Per GHG Protocol Corporate Standard Ch.3, this is set at onboarding and rarely changes. Operational control is the most common default for B2B SaaS customers; financial control matters for JV-heavy portfolios; equity share is mainly oil & gas."*

**Assumed:** operational control. Field is `Organization.consolidation_approach`, default chosen, alternatives modelled. A future V2 would change `Facility → Organization` weighting under equity share.

---

### Q4. Live API integration or file upload?

**Brief:** "We need to ingest all of it." Doesn't specify.

**Would ask:** *"The Concur Itinerary v4 API and Navan `/v1/bookings` would give us continuous sync. But Concur partner OAuth requires a multi-week approval process with SAP; Navan needs the customer's admin to generate client credentials and isn't sandboxable. Do we go straight to API for V1, or accept the longer enterprise sales cycle?"*

**Assumed:** CSV upload for all three sources in V1. This is what the facilities team actually emails over in week one of onboarding — the brief's exact language ("electricity data their facilities team pulls from utility portals"). API pull is the V2 path, and the data model is API-shaped so adding pull workers is mechanical (no schema change). The full reasoning is in SOURCES.md per source.

---

### Q5. Location-based or market-based Scope 2 — or both?

**Brief:** silent.

**Would ask:** *"GHG Protocol Scope 2 Guidance §6.1 mandates dual reporting where contractual instruments (RECs, PPAs, green tariffs) exist. Do we want to compute both in V1 or just location-based?"*

**Assumed:** **model both, compute only location-based in V1**. The `ActivityEmission` table is keyed by `(activity, method)` and every Scope 2 electricity activity gets two rows — one `location_based` (computed, eGRID/national grid), one `market_based` (null in V1). The `EnergyAttributeCertificate` model is in the schema. The market-based *calculation* requires GHG Protocol Quality Criteria validation (ownership matching, retirement period, geographic proximity, supplier-specific factor lookup) — those rules are too elaborate to do correctly in 4 days, and silently doing them wrong is worse than not doing them. See TRADEOFFS.md.

---

### Q6. Which radiative-forcing multiplier for aviation?

**Brief:** silent.

**Would ask:** *"DEFRA 2024 uses 1.7×, older DEFRA was 1.9×, ICAO uses 1.0 (no RF). Which one do we adopt, and is it disclosed in the report?"*

**Assumed:** 1.7× per current DEFRA guidance, **stored as a separate field** (`rf_multiplier_applied`) rather than baked into the factor value. This is the audit-disclosure best practice from DEFRA's 2024 methodology paper §4.3 and from Thrust Carbon's published methodology. It means the report can show "with RF 1.7×" and an auditor can compare against ICAO's 1.0×. Every competitor submission I read bakes RF into the factor — they can't show this distinction.

---

### Q7. How realistic does the sample data need to be?

**Brief:** explicitly: *"We will ask why your sample data looks the way it does."*

**Would ask:** *"Should the sample SAP CSV mirror a real MB51 export (semicolon-delimited, German locale, real BWART codes, real WERKS conventions), or is a stripped-down English-locale CSV fine for the prototype?"*

**Assumed:** mirror reality. The SAP CSV uses real SAP table column names (`WERKS, MATNR, MAKTX, BWART, MENGE, MEINS, BUDAT, LIFNR, WAERS, KOSTL`), semicolon delimiter, German decimal comma, DD.MM.YYYY dates, German fuel material text (`Diesel Kraftstoff EN590`, `Erdgas (Industriequalität)`, `Flüssiggas (Propan)`), real movement type codes (261 consumption, 262 reversal — preserves negative sign so reversals offset the original entry; 101 receipt — explicitly *not* ingested), real plant code conventions (1000 = HQ, 1100 = DE subsidiary, 2000 = US ops, 9999 = deliberately unmapped to demo the analyst-review path). Justifications per file are in SOURCES.md.

---

### Q8. SAP export mechanism — IDoc, OData, BAPI, flat file?

**Brief:** says "Research SAP export formats. […] Decide what subset of SAP reality you're handling."

**Would ask:** *"All four are real production paths. IDoc MBGMCR is the asynchronous EDI standard for goods movements but needs ALE setup and the BD21 change-pointer dance. OData via SAP Gateway needs Basis to activate the catalog service. BAPI_PO_GETDETAIL is per-document RFC. Flat-file MB51 is what the facilities team actually emails in week one."*

**Assumed:** **flat-file MB51 (Material Document List)** for V1. Documented in SOURCES.md with the alternatives and what we'd change to ingest each. The parser explicitly handles BWART filtering (261/201 consumption, 262/202 reversals; 101/501/311/312/561 receipts and transfers explicitly *skipped*) — this is the SAP integrator's first decision and the brief asked us to make it.

---

### Q9. Utility ingestion mode — CSV, PDF, or API?

**Brief:** "a portal CSV export, a PDF bill, an API if the utility offers one. Pick one mode and justify the choice."

**Would ask:** *"PDF OCR has highest analyst-friction relief but is multi-utility template work. API (Urjanet/Arcadia Plug/UtilityAPI/Green Button) gives continuous data but needs paid integrations or per-utility OAuth setup. Portal CSV is the lowest common denominator."*

**Assumed:** **portal CSV**. Lowest implementation barrier, broadest coverage (every US utility portal has a "Download usage data" button), matches the brief's "facilities team pulls from utility portals" language. PDF and API are explicitly deferred in TRADEOFFS.md. Sample CSV mirrors PG&E's "Bill Detail" and ConEd's "Account Detail" data dictionaries — verified against their published API responses.

---

### Q10. Where do plant codes get resolved to facilities?

**Brief:** silent on the lookup table.

**Would ask:** *"Should the analyst maintain SAP plant code → facility mapping in our UI, or should it come from a master data sync against the customer's HR/finance system?"*

**Assumed:** stored on `Facility.sap_plant_codes` as a comma-separated string (CSV-portable for SQLite — Postgres would use `ArrayField`). Resolved at ingest time. Unmapped plant codes (like `9999` in the sample data) don't get rejected — they ingest successfully without a facility FK and get surfaced in the review queue so the analyst can either create a facility or send the row back. V2 would add a "create facility from unmapped plant code" inline action.

---

### Q11. Authentication UI scope?

**Brief:** doesn't mention auth.

**Would ask:** *"For the prototype, is SSO (which is what real ESG SaaS customers expect — Okta/Azure AD/Google Workspace via SAML or OIDC) in scope, or is a basic login form enough?"*

**Assumed:** basic login form with seeded demo credentials. No signup, no password reset, no profile, no settings. The brief didn't ask for auth UX and grading weight is 10% on analyst UX, where the wins are in the review queue and the auditor bundle, not in a login flow. JWT issued by the seed_demo management command; one analyst user is created automatically.

---

### Q12. Reporting period model — do approved figures lock?

**Brief:** "approve rows before they're locked for audit."

**Would ask:** *"Once Q1 2024 closes and gets signed off, do the rows freeze individually, or is there a 'reporting period' object that snapshots a set of activities into an immutable disclosure? The latter is what's needed for restatement audit when DEFRA refreshes factors."*

**Assumed:** **row-level `is_locked`** for V1. A `ReportingPeriod` + `EmissionsSnapshot` table is the right next step (called out in TRADEOFFS.md) — without it, restating when DEFRA updates is awkward. But for the prototype's analyst review flow, `is_locked` is sufficient and the audit log carries the trail.

---

### Q13. Deployment platform — Render, Railway, Fly, or DigitalOcean?

**Brief:** "Render, Railway, Fly, or any provider of your choice."

**Would ask:** *"Render free tier sleeps after 15 minutes of inactivity — first reviewer hit takes ~30 seconds to wake. Is that acceptable, or do we pay for warm?"*

**Assumed:** **DigitalOcean droplet, 512 MB, $4/month**. No spin-down. Single Docker container — gunicorn serves both the Django API and the WhiteNoise-bundled React build off the same port. Caddy in front terminates Let's Encrypt TLS at `https://breathe-esg.duckdns.org`. The whole stack fits in ~130 MiB resident; the auditor can clone the repo and `docker run` it locally if our droplet is down (no Vercel/Postgres/Redis dependencies).

Of the 9 competitor submissions I saw with working backends, 7 used Render free tier — they'll all show "503 Application loading" on first reviewer hit. The single-container design avoids that.

---

### Q14. Database — SQLite or Postgres?

**Brief:** silent.

**Would ask:** *"Will the prototype need to handle the actual data volume of a real enterprise rollout (~100K+ activity rows / customer / quarter), or is the demo scale (35 rows) fine?"*

**Assumed:** **SQLite in the mounted Docker volume** for V1. Prototype scale, zero ops, file-based backup is trivial (`scp /opt/breathe-esg/data/db.sqlite3`). Migration to Postgres is a `DATABASES` change + `dumpdata/loaddata` — no model code touches. At a real customer it would be Postgres day one.

---

### Q15. Frontend framework conventions — Tailwind, MUI, shadcn, custom?

**Brief:** silent.

**Would ask:** *"Customer-facing aesthetic — do we match Breathe ESG's marketing site visual identity (the green-and-teal Webflow brand) or build a more generic enterprise dashboard?"*

**Assumed:** **match the brand**. Lifted the design tokens directly from `breatheesg.com`'s source CSS (primary `#39B54A`, teal `#0BAFD0`, light green `#97CCA2`, lavender `#AFB5DD`, neutrals tinted toward brand-green). Typography pair is Public Sans (US Web Design System — has the "audit-ready" institutional feel) + Bricolage Grotesque (variable display sans). Inter was deliberately rejected — it's a reflex AI font and would converge with every other submission. Card drop shadows removed (1px borders only) per the same principle: the product feels expensive because it doesn't try.

The Report view is editorial — single lede ("Acme Global emitted X t CO₂e across N approved rows") + a typeset breakdown table + two small visuals — instead of the four-KPI-tile dashboard template that every competitor used.
