import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { ActivityDetail, ActivityListItem, Paginated, ScopeCode } from "../api/types";
import { QualityChip, ReviewChip, ScopeChip } from "../components/Chips";

type Filter = {
  scope: ScopeCode | "";
  review_status: string;
  suspicious: boolean;
};

function num(v: string | null | undefined, dp = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString(undefined, { maximumFractionDigits: dp });
}

export default function Review() {
  const [filter, setFilter] = useState<Filter>({ scope: "", review_status: "under_review", suspicious: false });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const params = useMemo(() => {
    const q = new URLSearchParams();
    if (filter.scope) q.set("scope", filter.scope);
    if (filter.review_status) q.set("review_status", filter.review_status);
    if (filter.suspicious) q.set("suspicious", "1");
    q.set("limit", "200");
    return q.toString();
  }, [filter]);

  const list = useQuery<Paginated<ActivityListItem>>({
    queryKey: ["activities", params],
    queryFn: () => api<Paginated<ActivityListItem>>(`/activities/?${params}`),
  });

  return (
    <div className="space-y-7">
      <header>
        <div className="eyebrow mb-1.5">Review · sign-off queue</div>
        <h1 className="font-display text-[30px] font-semibold tracking-tightish text-brand-ink">
          Approve each row before it locks for audit.
        </h1>
        <p className="meta mt-2 max-w-[68ch]">
          Every activity carries its raw source-row payload, the factor used,
          and the value snapshot. Rejecting a row requires a comment that
          becomes part of the auditor's evidence trail.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        <FilterPills
          options={[
            { v: "", label: "All scopes" },
            { v: "1", label: "Scope 1" },
            { v: "2", label: "Scope 2" },
            { v: "3", label: "Scope 3" },
          ]}
          value={filter.scope}
          onChange={(scope) => setFilter((f) => ({ ...f, scope: scope as ScopeCode | "" }))}
        />
        <span className="mx-1 text-brand-rule">·</span>
        <FilterPills
          options={[
            { v: "under_review", label: "Under review" },
            { v: "approved", label: "Signed off" },
            { v: "rejected", label: "Rejected" },
            { v: "", label: "All" },
          ]}
          value={filter.review_status}
          onChange={(review_status) => setFilter((f) => ({ ...f, review_status }))}
        />
        <label className="ml-auto inline-flex items-center gap-2 text-[12px] text-brand-mid">
          <input type="checkbox" checked={filter.suspicious}
                 className="accent-brand-green-500"
                 onChange={(e) => setFilter((f) => ({ ...f, suspicious: e.target.checked }))} />
          Suspicious only
        </label>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_500px] gap-6 items-start">
        <div className="surface overflow-hidden">
          {list.isLoading && <div className="p-6 text-[13.5px] text-brand-subtle">Loading…</div>}
          {!list.isLoading && (list.data?.results ?? []).length === 0 && (
            <div className="p-6 text-[13.5px] text-brand-subtle">No activities match the current filters.</div>
          )}
          <table className="w-full">
            <thead className="bg-brand-paper">
              <tr>
                <th className="table-th">Scope</th>
                <th className="table-th">Activity</th>
                <th className="table-th">Period</th>
                <th className="table-th">Facility</th>
                <th className="table-th text-right">Quantity</th>
                <th className="table-th text-right">kg CO₂e</th>
                <th className="table-th">Quality</th>
                <th className="table-th">Status</th>
              </tr>
            </thead>
            <tbody>
              {(list.data?.results ?? []).map((a) => (
                <tr
                  key={a.id}
                  className={`row-hover ${selectedId === a.id ? "row-selected" : ""}`}
                  onClick={() => setSelectedId(a.id)}
                >
                  <td className="table-td"><ScopeChip scope={a.scope} /></td>
                  <td className="table-td">
                    <div className="font-medium text-brand-ink">{a.activity_type_display}</div>
                    <div className="meta truncate max-w-[28ch]">
                      {a.fuel_or_energy_type || a.cabin_class || a.description || "—"}
                    </div>
                  </td>
                  <td className="table-td meta whitespace-nowrap">
                    {a.period_start === a.period_end
                      ? a.period_start
                      : <>{a.period_start} <span className="text-brand-rule">→</span> {a.period_end}</>}
                  </td>
                  <td className="table-td">
                    <div className="font-medium">{a.facility_name || "—"}</div>
                    <div className="meta truncate max-w-[30ch]">{a.supplier_name}</div>
                  </td>
                  <td className="table-td text-right tnum">
                    {num(a.quantity_normalized)} <span className="text-brand-subtle">{a.unit_normalized}</span>
                  </td>
                  <td className="table-td text-right tnum font-medium">{num(a.co2e_kg)}</td>
                  <td className="table-td"><QualityChip tier={a.data_quality_tier} /></td>
                  <td className="table-td">
                    <div className="flex items-center gap-1.5">
                      <ReviewChip status={a.review_status} />
                      {a.has_warnings && <span className="chip-warn">flag</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DetailPane id={selectedId} onClose={() => setSelectedId(null)} onChanged={() => list.refetch()} />
      </div>
    </div>
  );
}

function FilterPills({
  options, value, onChange,
}: {
  options: { v: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="inline-flex bg-brand-surface rounded border border-brand-rule p-0.5">
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={`px-2.5 py-1 text-[11.5px] rounded transition-colors ${
            value === o.v ? "bg-brand-ink text-white" : "text-brand-mid hover:bg-brand-rule2"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function DetailPane({
  id, onClose, onChanged,
}: { id: string | null; onClose: () => void; onChanged: () => void }) {
  if (!id) {
    return (
      <div className="surface p-7 text-[13.5px] text-brand-subtle leading-relaxed">
        Select a row to inspect its raw payload, the factor breakdown, and
        sign it off. Rejection requires a comment that the auditor will see.
      </div>
    );
  }
  return <DetailPaneInner id={id} onClose={onClose} onChanged={onChanged} />;
}

function DetailPaneInner({
  id, onClose, onChanged,
}: { id: string; onClose: () => void; onChanged: () => void }) {
  const qc = useQueryClient();
  const { data, isLoading, refetch } = useQuery<ActivityDetail>({
    queryKey: ["activity", id],
    queryFn: () => api<ActivityDetail>(`/activities/${id}/`),
  });
  const [comment, setComment] = useState("");

  const review = useMutation({
    mutationFn: async (action: "approve" | "reject" | "request_changes") =>
      api<ActivityDetail>(`/activities/${id}/review/`, {
        method: "POST",
        body: JSON.stringify({ action, comment }),
      }),
    onSuccess: () => {
      setComment("");
      qc.invalidateQueries({ queryKey: ["activities"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      refetch();
      onChanged();
    },
  });

  if (isLoading || !data) {
    return <div className="surface p-6 text-[13.5px] text-brand-subtle">Loading…</div>;
  }

  return (
    <div className="surface divide-y divide-brand-rule2">
      <div className="p-6 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <ScopeChip scope={data.scope} />
            <span className="meta">
              {data.activity_type_display}
              {data.scope3_category ? ` · Cat ${data.scope3_category}` : ""}
            </span>
          </div>
          <h3 className="font-display font-semibold text-[16px] tracking-tightish leading-snug">
            {data.description || data.facility_name || "Activity"}
          </h3>
          <p className="meta mt-1">
            {data.period_start === data.period_end
              ? data.period_start
              : `${data.period_start} → ${data.period_end}`}{" "}
            · {data.facility_name || "Unassigned facility"}
          </p>
        </div>
        <button onClick={onClose} className="btn-ghost px-2 py-1 text-[16px] leading-none">×</button>
      </div>

      {data.flags.length > 0 && (
        <div className="p-5 bg-orange-50/40">
          <div className="eyebrow text-orange-900 mb-2">Parser flags</div>
          <ul className="text-[12.5px] text-orange-900 space-y-1 leading-relaxed">
            {data.flags.map((f, i) => <li key={i}>· {f.message}</li>)}
          </ul>
        </div>
      )}

      <div className="p-6">
        <h4 className="eyebrow mb-3">Normalized</h4>
        <dl className="grid grid-cols-2 gap-x-5 gap-y-2.5 text-[13.5px]">
          <Field k="Quantity (original)" v={<><span className="tnum">{num(data.quantity_original)}</span> <span className="text-brand-subtle">{data.unit_original}</span></>} />
          <Field k="Quantity (normalized)" v={<><span className="tnum">{num(data.quantity_normalized)}</span> <span className="text-brand-subtle">{data.unit_normalized}</span></>} />
          {data.cabin_class && <Field k="Cabin class" v={data.cabin_class} />}
          {data.fuel_or_energy_type && <Field k="Fuel / energy" v={<span className="code">{data.fuel_or_energy_type}</span>} />}
          {data.origin_iata && (
            <Field k="Route"
                   v={<span className="code">{data.origin_iata} → {data.destination_iata}</span>} />
          )}
          {data.distance_km && (
            <Field k="Distance" v={<><span className="tnum">{num(data.distance_km)}</span> <span className="text-brand-subtle">km</span></>} />
          )}
          <Field k="Data quality" v={<QualityChip tier={data.data_quality_tier} />} />
          <Field k="Review status" v={<ReviewChip status={data.review_status} />} />
        </dl>
      </div>

      <div className="p-6">
        <h4 className="eyebrow mb-3">Emission calculation</h4>
        <div className="space-y-2.5">
          {data.emissions.map((e) => (
            <div key={e.id} className="border border-brand-rule2 rounded p-3.5">
              <div className="flex items-baseline justify-between">
                <span className="font-medium text-[13.5px]">{e.method_display}</span>
                <span className="font-display font-semibold text-[15px] tnum">
                  {e.co2e_kg ? `${num(e.co2e_kg)} kg CO₂e` : "—"}
                </span>
              </div>
              <div className="meta mt-1 break-words">{e.factor_source_snapshot || "no factor"}</div>
              <div className="flex items-center gap-3 mt-1.5 text-[11.5px] text-brand-subtle">
                {e.factor_value_snapshot && (
                  <span className="code">
                    × {Number(e.factor_value_snapshot).toFixed(5)}
                    {e.factor?.unit_input ? ` /${e.factor.unit_input}` : ""}
                  </span>
                )}
                {e.rf_multiplier_snapshot && (
                  <span className="code">× RF {e.rf_multiplier_snapshot}</span>
                )}
                {e.factor?.source_url && (
                  <a href={e.factor.source_url} target="_blank" rel="noreferrer"
                     className="ml-auto text-brand-green-700 hover:underline underline-offset-3">
                    source ↗
                  </a>
                )}
              </div>
              {e.note && <div className="text-[11.5px] text-brand-mid mt-1.5 italic">{e.note}</div>}
            </div>
          ))}
        </div>
      </div>

      <div className="p-6">
        <details className="group">
          <summary className="eyebrow cursor-pointer hover:text-brand-ink flex items-center gap-1.5">
            <span className="transition-transform group-open:rotate-90">›</span>
            Raw source-row payload
          </summary>
          <pre className="mt-3 text-[11.5px] font-mono bg-brand-ink text-white p-3 rounded overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
{JSON.stringify(data.raw_data, null, 2)}
          </pre>
          <div className="text-[11px] text-brand-subtle mt-1.5 font-mono break-all">
            row {data.raw_row_id} · batch {data.batch_file}
          </div>
        </details>
      </div>

      {data.reviews.length > 0 && (
        <div className="p-6">
          <h4 className="eyebrow mb-3">Review history</h4>
          <ul className="space-y-3 text-[13px]">
            {data.reviews.map((r) => (
              <li key={r.id} className="pl-3 border-l border-brand-green-300">
                <div className="meta">
                  {r.reviewer_username} · {r.action} · {new Date(r.created_at).toLocaleString()}
                </div>
                {r.comment && <div className="text-brand-ink mt-0.5">{r.comment}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="p-6 space-y-3 bg-brand-paper">
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Comment (required for reject)…"
          rows={2}
          className="input resize-none"
        />
        <div className="flex items-center gap-2 justify-end">
          <button className="btn-ghost"
                  disabled={review.isPending}
                  onClick={() => review.mutate("request_changes")}>Request changes</button>
          <button className="btn-danger"
                  disabled={review.isPending || !comment.trim()}
                  onClick={() => review.mutate("reject")}>Reject</button>
          <button className="btn-brand"
                  disabled={review.isPending}
                  onClick={() => review.mutate("approve")}>
            {review.isPending ? "Saving…" : "Sign off row"}
          </button>
        </div>
        {review.error && (
          <div className="text-[12px] text-red-800">{(review.error as Error).message}</div>
        )}
      </div>
    </div>
  );
}

function Field({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <dt className="text-[11px] text-brand-subtle uppercase tracking-widerlabel">{k}</dt>
      <dd className="text-[13.5px] text-brand-ink">{v}</dd>
    </>
  );
}
