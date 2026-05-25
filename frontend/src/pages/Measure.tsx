import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Batch, Paginated } from "../api/types";

interface SampleMeta {
  source_type: string;
  filename: string;
  label: string;
}

const SOURCE_LABELS: Record<string, string> = {
  sap_fuel: "SAP — Fuel & procurement (MB51 extract)",
  utility_electricity: "Utility — Electricity (portal CSV)",
  travel: "Travel — Concur / Navan expense extract",
};

function StatusBadge({ status }: { status: string }) {
  const text = status.replace(/_/g, " ");
  if (status === "succeeded") return <span className="chip-approved">{text}</span>;
  if (status === "succeeded_with_errors") return <span className="chip-warn">{text}</span>;
  if (status === "failed") return <span className="chip-rejected">{text}</span>;
  return <span className="chip-pending">{text}</span>;
}

function DropZone({
  file, onFile,
}: { file: File | null; onFile: (f: File | null) => void }) {
  const [drag, setDrag] = useState(false);
  return (
    <label
      className={`relative block rounded-md border border-dashed px-5 py-7 cursor-pointer transition-colors
                  ${drag ? "border-brand-green-500 bg-brand-green-50" : "border-brand-rule bg-brand-paper hover:bg-brand-green-50/60"}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
    >
      <input
        type="file"
        accept=".csv,.txt,text/csv"
        className="sr-only"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      <div className="flex items-start gap-4">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" className="flex-none mt-0.5">
          <path d="M14 3v4a1 1 0 0 0 1 1h4" stroke="#39B54A" strokeWidth="1.5" strokeLinejoin="round"/>
          <path d="M5 8V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-3" stroke="#161C28" strokeWidth="1.5" strokeLinejoin="round"/>
          <path d="M3 12h7m0 0L7 9m3 3-3 3" stroke="#161C28" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div>
          {file ? (
            <>
              <div className="text-[14px] font-medium">{file.name}</div>
              <div className="meta">{(file.size / 1024).toFixed(1)} KB · ready to ingest</div>
            </>
          ) : (
            <>
              <div className="text-[14px] font-medium">Drop a CSV here or click to choose</div>
              <div className="meta">UTF-8 or Latin-1 · comma, semicolon, or tab delimited · max 10 MB</div>
            </>
          )}
        </div>
        {file && (
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); onFile(null); }}
            className="ml-auto text-[11.5px] text-brand-subtle hover:text-brand-ink underline underline-offset-3"
          >
            clear
          </button>
        )}
      </div>
    </label>
  );
}

function SampleDownloads() {
  const { data } = useQuery<SampleMeta[]>({
    queryKey: ["samples"],
    queryFn: () => api<SampleMeta[]>("/samples/"),
  });
  return (
    <div className="surface p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="font-display font-semibold text-[15px]">No data on hand? Grab a sample.</h3>
        <span className="meta">three realistic shapes · drop them back in above</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {(data ?? []).map((s) => (
          <a
            key={s.source_type}
            href={`/api/samples/${s.source_type}/`}
            className="group block rounded border border-brand-rule px-4 py-3 hover:border-brand-green-500 hover:bg-brand-green-50/40 transition-colors"
          >
            <div className="eyebrow mb-1.5">{s.source_type.replace(/_/g, " ")}</div>
            <div className="text-[13.5px] font-medium leading-snug">{s.label}</div>
            <div className="meta mt-1.5 flex items-center gap-2">
              <span className="code">{s.filename}</span>
              <span className="ml-auto text-brand-green-700 group-hover:translate-x-0.5 transition-transform">↓</span>
            </div>
          </a>
        ))}
      </div>
      <p className="meta mt-3 leading-relaxed">
        Each file contains deliberate edge cases — German decimal commas, mixed
        kWh/MWh units, an invalid IATA code, an unmapped SAP plant. They're the
        shapes a real onboarding analyst would receive in week one.
      </p>
    </div>
  );
}

function Stat({
  label, value, accent, hint,
}: { label: string; value: React.ReactNode; accent?: "green" | "amber" | "orange"; hint?: string }) {
  const c =
    accent === "green" ? "text-brand-green-700"
    : accent === "amber" ? "text-amber-800"
    : accent === "orange" ? "text-orange-800"
    : "text-brand-ink";
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className={`text-2xl font-display font-semibold num-display ${c}`}>{value}</div>
      {hint && <div className="meta mt-0.5">{hint}</div>}
    </div>
  );
}

function UploadCard() {
  const [sourceType, setSourceType] = useState("sap_fuel");
  const [file, setFile] = useState<File | null>(null);
  const [lastResult, setLastResult] = useState<Batch | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Pick a CSV file first.");
      const fd = new FormData();
      fd.append("source_type", sourceType);
      fd.append("file", file);
      return api<Batch>("/ingestion/upload/", { method: "POST", body: fd });
    },
    onSuccess: (b) => {
      setLastResult(b);
      setErr(null);
      setFile(null);
      qc.invalidateQueries({ queryKey: ["batches"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["activities"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div className="surface p-6">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h2 className="font-display text-[19px] font-semibold tracking-tightish">Ingest source data</h2>
          <p className="meta mt-1">CSV only in V1. PDF parsing is deferred — see TRADEOFFS.md.</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-5">
        <div className="space-y-4">
          <label className="block">
            <span className="eyebrow">Source type</span>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="input mt-1.5"
            >
              {Object.entries(SOURCE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          <button
            className="btn-primary w-full"
            disabled={!file || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Ingesting…" : "Ingest CSV"}
          </button>
          {file && (
            <p className="meta">Re-uploading a file you've already ingested
              will report duplicates skipped — content-hashed dedup.</p>
          )}
        </div>
        <DropZone file={file} onFile={setFile} />
      </div>

      {err && (
        <div className="mt-5 text-[13px] text-red-800 bg-red-50 border border-red-100 rounded px-3 py-2">
          {err}
        </div>
      )}
      {lastResult && (
        <div className="mt-6 pt-5 border-t border-brand-rule2 grid grid-cols-2 md:grid-cols-5 gap-x-6 gap-y-3">
          <Stat label="Rows seen" value={lastResult.row_count} />
          <Stat label="Created" value={lastResult.ok_count} accent="green" />
          <Stat
            label="Duplicates skipped"
            value={lastResult.duplicate_count}
            accent={lastResult.duplicate_count > 0 ? "amber" : undefined}
            hint="row_sha256 dedup"
          />
          <Stat label="Errors" value={lastResult.error_count} accent={lastResult.error_count > 0 ? "orange" : undefined} />
          <Stat label="Status" value={<StatusBadge status={lastResult.status} />} />
        </div>
      )}
    </div>
  );
}

function BatchList() {
  const { data, isLoading } = useQuery<Paginated<Batch>>({
    queryKey: ["batches"],
    queryFn: () => api<Paginated<Batch>>("/batches/?ordering=-uploaded_at"),
  });
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) {
    return <div className="surface p-6 text-[13.5px] text-brand-subtle">Loading batches…</div>;
  }
  const batches = data?.results ?? [];

  return (
    <div className="surface overflow-hidden">
      <div className="px-6 py-3.5 border-b border-brand-rule flex items-baseline justify-between">
        <h3 className="font-display font-semibold text-[15px]">Ingestion history</h3>
        <span className="meta">{batches.length} batches</span>
      </div>
      {batches.length === 0 && (
        <div className="p-6 text-[13.5px] text-brand-subtle">
          No batches yet. Upload a CSV above to get started.
        </div>
      )}
      <table className="w-full">
        <thead className="bg-brand-paper">
          <tr>
            <th className="table-th">Source</th>
            <th className="table-th">File</th>
            <th className="table-th">Uploaded</th>
            <th className="table-th text-right">Rows</th>
            <th className="table-th text-right">Ok</th>
            <th className="table-th text-right">Dup</th>
            <th className="table-th text-right">Err</th>
            <th className="table-th">Status</th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <>
              <tr key={b.id} className="row-hover"
                  onClick={() => setExpanded(expanded === b.id ? null : b.id)}>
                <td className="table-td">{b.source_type_display}</td>
                <td className="table-td code">{b.file_name}</td>
                <td className="table-td meta">{new Date(b.uploaded_at).toLocaleString()}</td>
                <td className="table-td text-right tnum">{b.row_count}</td>
                <td className="table-td text-right tnum font-medium text-brand-green-700">{b.ok_count}</td>
                <td className="table-td text-right tnum text-amber-800">{b.duplicate_count}</td>
                <td className="table-td text-right tnum text-orange-800">{b.error_count}</td>
                <td className="table-td"><StatusBadge status={b.status} /></td>
              </tr>
              {expanded === b.id && b.error_summary.length > 0 && (
                <tr key={`${b.id}-detail`} className="bg-orange-50/30">
                  <td colSpan={8} className="px-6 py-4 border-b border-brand-rule2">
                    <div className="eyebrow text-orange-900 mb-2">
                      Row-level errors · {b.error_summary.length}
                    </div>
                    <ul className="text-[12.5px] font-mono space-y-1 leading-relaxed">
                      {b.error_summary.slice(0, 20).map((e, i) => (
                        <li key={i}>
                          <span className="text-brand-subtle">row {e.row}:</span>{" "}
                          {e.errors.join("; ")}
                        </li>
                      ))}
                    </ul>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Measure() {
  return (
    <div className="space-y-7">
      <header>
        <div className="eyebrow mb-1.5">Measure · ingestion</div>
        <h1 className="font-display text-[30px] font-semibold tracking-tightish text-brand-ink">
          Bring messy source files into a canonical, deduplicated activity ledger.
        </h1>
        <p className="meta mt-2 max-w-[68ch]">
          Every parsed row is content-hashed before insertion, so re-uploading the same
          file (or two files with overlapping date ranges) produces zero duplicates.
          Errors stay tied to the source row for analyst review.
        </p>
      </header>
      <SampleDownloads />
      <UploadCard />
      <BatchList />
    </div>
  );
}
