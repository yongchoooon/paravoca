import { apiGet } from "./apiClient";

export type DataSourceOperationCapability = {
  tool_name: string;
  operation: string;
  purpose: string;
  implemented: boolean;
  workflow_enabled: boolean;
  required_for_phase: string;
};

export type DataSourceInventoryStats = {
  tourism_items: number;
  source_documents: number;
  indexed_documents: number;
  visual_assets: number;
  route_assets: number;
  signal_records: number;
  enrichment_calls: number;
  successful_enrichment_calls: number;
  failed_enrichment_calls: number;
  latest_activity_at: string | null;
};

export type DataSourceOverviewItem = {
  source_family: string;
  display_name: string;
  category: string;
  purpose: string;
  input_fields: string[];
  output_fields: string[];
  example_use: string;
  origin_description: string;
  purpose_tags: string[];
  stored_count: number;
  evidence_count: number;
  enabled: boolean;
  requires_service_key: boolean;
  required_env_vars: string[];
  configured_env_vars: string[];
  missing_env_vars: string[];
  source_setting_env: string | null;
  source_setting_enabled: boolean;
  supported_gaps: string[];
  default_ttl_hours: number;
  risk_level: string;
  operations: DataSourceOperationCapability[];
  disabled_reasons: string[];
  notes: string[];
  readiness_status: string;
  status_label: string;
  status_detail: string;
  implemented_operation_count: number;
  workflow_operation_count: number;
  inventory: DataSourceInventoryStats;
};

export type DataSourceCatalogStatus = {
  key: string;
  label: string;
  record_count: number;
  status: string;
  status_label: string;
  last_synced_at: string | null;
};

export type DataSourceDocumentStatus = {
  total: number;
  indexed: number;
  pending: number;
  failed: number;
  status: string;
  status_label: string;
  latest_updated_at: string | null;
};

export type DataSourceTourismInventory = {
  total_items: number;
  items_with_image: number;
  content_type_counts: Record<string, number>;
  latest_synced_at: string | null;
};

export type DataSourcePurposeProfile = {
  key: string;
  label: string;
};

export type DataSourceOverviewSummary = {
  total_sources: number;
  ready_sources: number;
  setup_required_sources: number;
  disabled_sources: number;
  implemented_operation_count: number;
  workflow_operation_count: number;
  tourism_item_count: number;
  source_document_count: number;
  indexed_document_count: number;
  enrichment_run_count: number;
  latest_activity_at: string | null;
};

export type DataSourceOverview = {
  purpose: string;
  purpose_detail: string;
  summary: DataSourceOverviewSummary;
  sources: DataSourceOverviewItem[];
  catalogs: DataSourceCatalogStatus[];
  documents: DataSourceDocumentStatus;
  tourism_inventory: DataSourceTourismInventory;
  purpose_profiles: DataSourcePurposeProfile[];
};

export type DataSourceDocumentPreview = {
  id: string;
  title: string;
  source: string;
  source_family: string;
  source_label: string;
  source_item_id: string;
  source_item_title: string | null;
  content_excerpt: string;
  content: string;
  embedding_status: string;
  status_label: string;
  content_type: string | null;
  address: string | null;
  origin_summary: string;
  usage_summary: string;
  updated_at: string | null;
};

export type DataSourceDocumentBrowserResponse = {
  items: DataSourceDocumentPreview[];
  total: number;
  limit: number;
};

export type DataSourceTourismItemPreview = {
  id: string;
  title: string;
  source: string;
  source_family: string;
  source_label: string;
  content_id: string;
  content_type: string;
  content_type_label: string;
  address: string | null;
  ldong_label: string | null;
  classification_label: string | null;
  has_image: boolean;
  has_ai_evidence: boolean;
  origin_summary: string;
  detail_summary: string;
  last_synced_at: string | null;
};

export type DataSourceTourismItemBrowserResponse = {
  items: DataSourceTourismItemPreview[];
  total: number;
  limit: number;
};

export type DataSourceRegionCatalogItem = {
  id: string;
  region_code: string;
  region_name: string;
  signgu_code: string | null;
  signgu_name: string | null;
  full_name: string;
  tourism_item_count: number;
  synced_at: string | null;
};

export type DataSourceClassificationCatalogItem = {
  id: string;
  code_path: string[];
  name_path: string[];
  content_type_id: string | null;
  content_type_name: string | null;
  full_name: string;
  tourism_item_count: number;
  synced_at: string | null;
};

export type DataSourceCatalogBrowserResponse = {
  regions: DataSourceRegionCatalogItem[];
  classifications: DataSourceClassificationCatalogItem[];
  region_total: number;
  classification_total: number;
  limit: number;
  region_offset: number;
  classification_offset: number;
};

export function getDataSourceOverview() {
  return apiGet<DataSourceOverview>("/data/sources/overview");
}

export function getDataSourceDocuments(params: {
  keyword?: string;
  source_family?: string;
  embedding_status?: string;
  limit?: number;
} = {}) {
  return apiGet<DataSourceDocumentBrowserResponse>(`/data/sources/documents${toQueryString(params)}`);
}

export function getDataSourceTourismItems(params: {
  keyword?: string;
  source_family?: string;
  content_type?: string;
  region?: string;
  has_image?: boolean | null;
  limit?: number;
} = {}) {
  return apiGet<DataSourceTourismItemBrowserResponse>(`/data/sources/tourism-items${toQueryString(params)}`);
}

export function getDataSourceCatalogs(params: {
  region_keyword?: string;
  classification_keyword?: string;
  region_code?: string;
  lcls_systm_1?: string;
  lcls_systm_2?: string;
  region_offset?: number;
  classification_offset?: number;
  limit?: number;
} = { limit: 30 }) {
  return apiGet<DataSourceCatalogBrowserResponse>(`/data/sources/catalogs/browser${toQueryString(params)}`);
}

function toQueryString(params: Record<string, string | number | boolean | null | undefined>) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === "all") return;
    searchParams.set(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}
