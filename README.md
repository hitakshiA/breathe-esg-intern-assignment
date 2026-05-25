# Breathe ESG — Analyst Review Prototype

Tech-intern assignment submission. A Django REST + React application that ingests
emissions activity data from three messy enterprise sources — SAP fuel & procurement,
utility electricity portals, and corporate travel platforms — normalizes it to a
canonical model aligned with the GHG Protocol, and exposes a review queue where an
analyst can sign off rows before they lock for audit.

**Live:** <https://breathe-esg.duckdns.org>
**Demo login:** `analyst` / `breathe2024`

---

## What you'll see

1. **Sign in** → land on **Measure**. Three "Grab a sample" tiles let any visitor download a realistic source CSV (SAP MB51 in German locale, US utility portal export, Concur expense extract). Drag the file back into the drop zone above to ingest it — second upload of the same file produces *zero new rows*, with the dedup count surfaced in the UI (content-hashed `row_sha256` unique constraint).
2. **Review** queue → 35 pre-seeded activity rows across Scopes 1, 2, and 3. Filter by scope / status / "suspicious only". Click any row to inspect the raw source-row JSON, the normalized canonical fields, and the factor breakdown — every emission row carries an immutable snapshot of the factor value, source, and RF multiplier it was calculated with.
3. **Report** → an editorial summary, not a four-tile dashboard. A single lede ("Acme Global emitted N t CO₂e across M approved rows"), a typeset scope breakdown table, and a single signature CTA: **Download auditor bundle**, a 26-column CSV with full provenance from the final kg CO₂e back to the source row sha256 and the source file sha256.

---

## Deliverables (assignment-mandated)

| File | What's in it |
|---|---|
| **[MODEL.md](MODEL.md)** | Data model — eleven tables, multi-tenancy approach, Scope 1/2/3 categorization, dual Scope 2 modeling, factor versioning, source-of-truth tracking, append-only audit log, unit normalization |
| **[DECISIONS.md](DECISIONS.md)** | Fifteen ambiguities in the brief, what I'd have asked the PM, what I assumed and why |
| **[TRADEOFFS.md](TRADEOFFS.md)** | Three things I deliberately did *not* build — live API integrations, PDF utility OCR, market-based Scope 2 calculation — each with what I built instead and the V2 path |
| **[SOURCES.md](SOURCES.md)** | Per source: real-world format researched, what I learned, why the sample data looks the way it does, what would break in real deployment |

---

## Architecture

```
Internet :443 (TLS 1.3, Let's Encrypt auto-renewed)
        ↓
   Caddy (systemd, single host)
        ↓ reverse_proxy
   127.0.0.1:8000  ← Docker container (not publicly bound)
        ├── gunicorn 2 workers
        ├── Django 5 + DRF + JWT auth
        ├── WhiteNoise serving the React build
        └── SQLite in /opt/breathe-esg/data
```

Single host, single container, single image. Total resident memory ~130 MiB
on a $4/mo 512 MiB DigitalOcean droplet. Caddy holds another ~48 MiB.

---

## Run it yourself

You need Docker — that's the only dependency. No node, no Python, no Postgres.

```bash
git clone https://github.com/hitakshiA/breathe-esg-intern-assignment.git
cd breathe-esg-intern-assignment
docker build -t breathe-esg .
docker run -p 8000:8000 -v ./data:/data breathe-esg
open http://localhost:8000
```

First boot runs migrations, seeds 56 emission factor rows from DEFRA 2024 and
EPA eGRID 2022, creates the `acme-global` demo tenant + the `analyst` user, and
ingests the three sample CSVs in `samples/`. Subsequent boots are no-ops on
already-seeded data (idempotent management commands).

Health check: `http://localhost:8000/api/health/` → `{"status":"ok"}`.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | Django 5 · Django REST Framework · djangorestframework-simplejwt · WhiteNoise |
| Frontend | Vite · React 18 · TypeScript (strict) · Tailwind 3 · React Query · Recharts |
| Storage | SQLite (mounted volume) — Postgres-ready via single `DATABASES` change |
| Process | gunicorn 2× workers behind WhiteNoise |
| Deploy | Single Docker image, multi-stage build, Caddy in front for TLS |

---

## Highlights worth a closer look

- **`backend/api/models.py`** — the data model in 11 Django models with comments on every load-bearing field
- **`backend/api/parsers/sap.py`** — German-locale CSV parsing, SAP movement-type filtering with the actual BWART codes documented
- **`backend/api/factors.py`** — DEFRA 2024 + EPA eGRID 2022 seed data, every value cited to its publication URL
- **`backend/api/calc.py`** — emission calculation engine, including the dual Scope 2 path
- **`samples/`** — three realistic CSVs with deliberate edge cases (German locale, MWh-in-kWh-column anomaly, invalid IATA, unmapped SAP plant code)
- **`frontend/src/pages/Report.tsx`** — editorial layout, brand tokens lifted from breatheesg.com source CSS
- **`Dockerfile`** — multi-stage Node-builds-React then Python-runs-Django, single container

---

## Not included (intentional — see TRADEOFFS.md)

- PDF utility bill OCR
- Live API integrations (Concur Itinerary v4, Navan, SAP OData, Urjanet)
- Market-based Scope 2 *calculation* (schema is ready, including `EnergyAttributeCertificate`)
