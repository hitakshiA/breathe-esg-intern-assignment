import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/client";
import type { SummaryResp } from "../api/types";

function fmtTonnes(kg: number | string | null | undefined, dp = 2): string {
  if (kg === null || kg === undefined || kg === "") return "—";
  const n = Number(kg);
  if (Number.isNaN(n)) return "—";
  return (n / 1000).toLocaleString(undefined, { maximumFractionDigits: dp, minimumFractionDigits: dp });
}

const TIER_LABEL: Record<string, string> = {
  "1": "Tier 1 — actual",
  "2": "Tier 2 — derived",
  "3": "Tier 3 — estimated",
};
const TIER_COLOR: Record<string, string> = {
  "1": "#39B54A",
  "2": "#E0A100",
  "3": "#D8650F",
};

export default function Report() {
  const { data, isLoading } = useQuery<SummaryResp>({
    queryKey: ["summary"],
    queryFn: () => api<SummaryResp>("/summary/"),
  });

  if (isLoading || !data) {
    return <div className="text-[13.5px] text-brand-subtle">Loading…</div>;
  }

  const totals = data.totals_kg;
  const s1 = Number(totals.scope_1);
  const s2loc = Number(totals.scope_2_location);
  const s2mkt = totals.scope_2_market === null ? null : Number(totals.scope_2_market);
  const s3 = Number(totals.scope_3_cat_6);
  const total = s1 + s2loc + s3;

  const facilityData = data.by_facility.slice(0, 8).map((f) => ({
    name: f.facility,
    kg: Number(f.co2e_kg),
  }));
  const qualityData = Object.entries(data.by_quality_tier).map(([k, v]) => ({
    name: TIER_LABEL[k] || `Tier ${k}`,
    value: Number(v),
    tier: k,
  }));

  const reportingDate = new Date().toLocaleDateString(undefined, {
    year: "numeric", month: "long", day: "numeric",
  });

  return (
    <article className="max-w-[1080px] mx-auto">
      {/* ── Lede ─────────────────────────────────────────────────────── */}
      <header className="mb-12">
        <div className="flex items-center gap-3 mb-5">
          <span className="eyebrow text-brand-green-700">Carbon position</span>
          <span className="h-px bg-brand-rule flex-1" />
          <span className="meta">as of {reportingDate}</span>
        </div>
        <h1 className="lede font-display max-w-[28ch]">
          <span className="text-brand-ink">Acme Global emitted </span>
          <span className="text-brand-green-700 num-display">
            {fmtTonnes(total, 1)}
          </span>
          <span className="text-brand-ink"> t CO₂e across {data.approved_count} approved activity rows.</span>
        </h1>
        <p className="mt-5 max-w-[60ch] text-brand-mid text-[15px] leading-relaxed">
          The figure rolls up Scope 1 fuel combustion, Scope 2 purchased
          electricity (location-based per GHG Protocol Scope 2 Guidance §6.1),
          and Scope 3 Category 6 business travel. Market-based Scope 2 is modeled
          in the schema but not yet calculated — see <span className="font-mono text-[13.5px]">TRADEOFFS.md</span>.
        </p>
        <div className="mt-7">
          <a
            href="/api/export/auditor-bundle.csv"
            className="btn-brand"
            target="_blank"
            rel="noreferrer"
          >
            Download auditor bundle
            <span aria-hidden>↓</span>
          </a>
          <span className="meta ml-3">26 columns · full provenance from kg CO₂e back to source row sha256</span>
        </div>
      </header>

      <hr className="border-brand-rule" />

      {/* ── Scope breakdown — typeset table, not tiles ────────────────── */}
      <section className="py-10">
        <h2 className="eyebrow mb-6">Breakdown by scope</h2>
        <table className="w-full">
          <thead>
            <tr className="border-b border-brand-rule">
              <th className="text-left py-3 text-[11px] uppercase tracking-widerlabel text-brand-subtle font-semibold">Scope</th>
              <th className="text-left py-3 text-[11px] uppercase tracking-widerlabel text-brand-subtle font-semibold">Method</th>
              <th className="text-left py-3 text-[11px] uppercase tracking-widerlabel text-brand-subtle font-semibold">Activity</th>
              <th className="text-right py-3 text-[11px] uppercase tracking-widerlabel text-brand-subtle font-semibold">t CO₂e</th>
            </tr>
          </thead>
          <tbody>
            <ScopeRow scope="1" tone="green" method="Activity-based" activity="Stationary + mobile combustion · DEFRA 2024" value={s1} />
            <ScopeRow scope="2" tone="teal" method="Location-based"
                      activity="Grid electricity · EPA eGRID 2022 (US) + DEFRA/IEA national grids"
                      value={s2loc} />
            <ScopeRow scope="2" tone="teal" method="Market-based" muted
                      activity={`Pending REC/PPA Quality Criteria validation · ${totals.scope_2_market_pending_rows} rows`}
                      value={s2mkt} />
            <ScopeRow scope="3" tone="purple" method="Activity-based"
                      activity="Cat 6 business travel · DEFRA 2024 with RF 1.7× applied separately"
                      value={s3} />
            <tr>
              <td colSpan={3} className="py-4 pt-6 font-display font-semibold text-[15px]">Total · location-based view</td>
              <td className="py-4 pt-6 text-right font-display font-semibold text-[19px] num-display text-brand-ink">
                {fmtTonnes(total, 2)}
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <hr className="border-brand-rule" />

      {/* ── Two side-by-side small visuals, in editorial register ─────── */}
      <section className="py-10 grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-10">
        <div>
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="eyebrow">By facility</h2>
            <span className="meta">top {facilityData.length} · approved activities</span>
          </div>
          <div className="h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={facilityData} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="#EFF1EE" horizontal={false} />
                <XAxis type="number"
                       tickFormatter={(v: number) => `${(v / 1000).toFixed(1)} t`}
                       fontSize={11}
                       stroke="#727988" />
                <YAxis type="category" dataKey="name" fontSize={12} width={150} stroke="#161C28" />
                <Tooltip
                  formatter={(v: number) => [`${(v / 1000).toFixed(2)} t CO₂e`, "Emissions"]}
                  cursor={{ fill: "#E1F1E5", opacity: 0.6 }}
                  contentStyle={{
                    borderRadius: 6,
                    fontSize: 12,
                    border: "1px solid #E3E6E2",
                    boxShadow: "none",
                  }}
                />
                <Bar dataKey="kg" fill="#39B54A" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <div className="flex items-baseline justify-between mb-4">
            <h2 className="eyebrow">Data quality mix</h2>
            <span className="meta">GHG Protocol tiers</span>
          </div>
          <div className="h-[220px] -mx-2">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={qualityData} dataKey="value" nameKey="name"
                     innerRadius={48} outerRadius={86} paddingAngle={2} stroke="#FAFBFA" strokeWidth={2}>
                  {qualityData.map((q) => (
                    <Cell key={q.tier} fill={TIER_COLOR[q.tier] || "#9CA3AF"} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => `${(v / 1000).toFixed(2)} t CO₂e`}
                  contentStyle={{
                    borderRadius: 6,
                    fontSize: 12,
                    border: "1px solid #E3E6E2",
                    boxShadow: "none",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="mt-3 space-y-1.5">
            {qualityData.map((q) => (
              <li key={q.tier} className="flex items-baseline gap-3 text-[12.5px]">
                <span className="w-2 h-2 rounded-sm" style={{ background: TIER_COLOR[q.tier] }} />
                <span className="text-brand-mid">{q.name}</span>
                <span className="ml-auto tnum text-brand-ink">{fmtTonnes(q.value, 2)} t</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <hr className="border-brand-rule" />

      {/* ── Methodology note ──────────────────────────────────────────── */}
      <section className="py-10">
        <h2 className="eyebrow mb-3">On the numbers</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-5 text-[14px] leading-relaxed text-brand-mid max-w-[80ch]">
          <p>
            <strong className="text-brand-ink">Scope 1.</strong> DEFRA 2024 fuel
            combustion factors — diesel EN590 2.51233 kg CO₂e/L, natural gas
            2.04428 kg CO₂e/m³, etc. Each factor row in the calculation snapshots
            value, source, and version on the activity, so updating the factor
            table never silently restates an approved figure.
          </p>
          <p>
            <strong className="text-brand-ink">Scope 2.</strong> Dual-method per
            GHG Protocol Scope 2 Guidance. Location-based uses EPA eGRID 2022
            subregion factors for US facilities (e.g.{" "}
            <span className="code">CAMX</span> = 0.2256 kg/kWh) and DEFRA/IEA
            national grids elsewhere. Market-based requires REC/PPA Quality
            Criteria validation — schema is ready, calculation deferred to V2.
          </p>
          <p>
            <strong className="text-brand-ink">Scope 3 Cat 6.</strong> Flight
            distance is great-circle (Haversine) plus DEFRA's 8% detour uplift.
            Aviation factors are CO₂-only; the radiative-forcing multiplier
            (1.7× per current DEFRA guidance) is applied and disclosed as a
            separate field so auditors can compare across 1.0 / 1.7 / 1.9.
          </p>
          <p>
            <strong className="text-brand-ink">Provenance.</strong> The auditor
            bundle CSV exports 26 columns per emission row: factor value
            snapshot, factor source URL, RF multiplier applied, the raw row's
            sha256, the source file's sha256, the analyst who signed off, and
            when. Every reported tonne can be reconstructed.
          </p>
        </div>
      </section>
    </article>
  );
}

function ScopeRow({
  scope, tone, method, activity, value, muted,
}: {
  scope: "1" | "2" | "3";
  tone: "green" | "teal" | "purple";
  method: string;
  activity: string;
  value: number | null;
  muted?: boolean;
}) {
  const toneCls = tone === "green"
    ? "text-brand-green-700"
    : tone === "teal" ? "text-brand-teal-700" : "text-brand-purple-700";
  return (
    <tr className="border-b border-brand-rule2">
      <td className="py-4 align-top">
        <span className={`font-display font-semibold text-[15px] ${toneCls}`}>Scope {scope}</span>
      </td>
      <td className="py-4 align-top text-[13px] text-brand-mid">{method}</td>
      <td className="py-4 align-top text-[13px] text-brand-mid max-w-[44ch]">{activity}</td>
      <td className={`py-4 align-top text-right font-display font-semibold text-[17px] num-display ${muted ? "text-brand-subtle" : "text-brand-ink"}`}>
        {value === null || (muted && (value === 0)) ? "—" : fmtTonnes(value, 2)}
      </td>
    </tr>
  );
}
