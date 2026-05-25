export type ScopeCode = "1" | "2" | "3";

export type ReviewStatus = "draft" | "under_review" | "approved" | "rejected";

export interface Organization {
  id: string;
  name: string;
  slug: string;
  consolidation_approach: string;
  disclosure_framework: string;
}

export interface Me {
  id: string;
  username: string;
  email: string;
  role: string;
  organization: Organization | null;
}

export interface Batch {
  id: string;
  source_type: string;
  source_type_display: string;
  file_name: string;
  file_sha256: string;
  uploaded_by_username: string;
  uploaded_at: string;
  status: string;
  status_display: string;
  row_count: number;
  ok_count: number;
  error_count: number;
  duplicate_count: number;
  error_summary: { row: number; errors: string[] }[];
}

export interface ActivityListItem {
  id: string;
  activity_type: string;
  activity_type_display: string;
  scope: ScopeCode;
  scope_display: string;
  scope3_category: number | null;
  facility_name: string;
  period_start: string;
  period_end: string;
  quantity_normalized: string;
  unit_normalized: string;
  fuel_or_energy_type: string;
  cabin_class: string;
  origin_iata: string;
  destination_iata: string;
  distance_km: string | null;
  supplier_name: string;
  description: string;
  data_quality_tier: number;
  review_status: ReviewStatus;
  is_locked: boolean;
  co2e_kg: string | null;
  has_warnings: boolean;
}

export interface ActivityEmission {
  id: string;
  method: string;
  method_display: string;
  factor: EmissionFactor | null;
  factor_value_snapshot: string | null;
  factor_source_snapshot: string;
  rf_multiplier_snapshot: string | null;
  co2e_kg: string | null;
  note: string;
  calculated_at: string;
}

export interface EmissionFactor {
  id: number;
  source: string;
  dataset_version_year: number;
  activity_type: string;
  fuel_or_energy_type: string;
  region_code: string;
  cabin_class: string;
  haul_band: string;
  valid_from: string;
  valid_to: string | null;
  factor_value: string;
  unit_input: string;
  unit_output: string;
  rf_multiplier_applied: string | null;
  gwp_basis: string;
  source_url: string;
  notes: string;
}

export interface Review {
  id: string;
  action: string;
  comment: string;
  reviewer_username: string;
  created_at: string;
}

export interface ActivityDetail extends ActivityListItem {
  raw_row_id: string;
  batch_id: string;
  batch_file: string;
  raw_data: Record<string, string>;
  emissions: ActivityEmission[];
  reviews: Review[];
  flags: { code: string; message: string; severity: string }[];
  quantity_original: string;
  unit_original: string;
}

export interface SummaryResp {
  totals_kg: {
    scope_1: number | string;
    scope_2_location: number | string;
    scope_2_market: number | string | null;
    scope_2_market_pending_rows: number;
    scope_3_cat_6: number | string;
    total: number | string;
  };
  by_facility: { facility: string; co2e_kg: string }[];
  by_quality_tier: Record<string, string>;
  approved_count: number;
  period: { start: string | null; end: string | null };
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
