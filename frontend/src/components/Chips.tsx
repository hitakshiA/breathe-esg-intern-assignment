import type { ReviewStatus, ScopeCode } from "../api/types";

export function ScopeChip({ scope }: { scope: ScopeCode }) {
  if (scope === "1") return <span className="chip-scope-1">Scope 1</span>;
  if (scope === "2") return <span className="chip-scope-2">Scope 2</span>;
  return <span className="chip-scope-3">Scope 3</span>;
}

export function ReviewChip({ status }: { status: ReviewStatus }) {
  if (status === "approved") return <span className="chip-approved">Signed off</span>;
  if (status === "rejected") return <span className="chip-rejected">Rejected</span>;
  if (status === "under_review") return <span className="chip-pending">Under review</span>;
  return <span className="chip bg-brand-rule2 text-brand-mid">Draft</span>;
}

export function QualityChip({ tier }: { tier: number }) {
  const label = tier === 1 ? "Tier 1 · actual" : tier === 2 ? "Tier 2 · derived" : "Tier 3 · estimated";
  const cls = tier === 1 ? "chip-quality-1" : tier === 2 ? "chip-quality-2" : "chip-quality-3";
  return <span className={cls} title={`GHG Protocol methodology tier ${tier}`}>{label}</span>;
}
