import { API_BASE_URL, apiDelete, apiGet, apiPost } from "./apiClient";

export type PosterStylePresetId = "editorial_travel" | "night_city" | "minimal_event";

export type PosterIncludedSection =
  | "product_summary"
  | "itinerary"
  | "marketing_copy"
  | "sns_copy"
  | "evidence_summary"
  | "claim_limits";

export type PosterStatus = "pending" | "running" | "succeeded" | "failed";

export type PosterAsset = {
  id: string;
  run_id: string;
  product_id: string;
  product_title: string;
  style_preset: PosterStylePresetId | string;
  included_sections: PosterIncludedSection[];
  prompt: string;
  prompt_language: "en" | string;
  image_model: string;
  image_size: string;
  image_quality: string;
  image_path: string | null;
  image_url: string | null;
  provider: string;
  provider_response_summary: Record<string, unknown>;
  cost_usd: number;
  latency_ms: number | null;
  status: PosterStatus | string;
  error: { message?: string; details?: Record<string, unknown> } | null;
  created_at: string;
  updated_at: string;
};

export type PosterStylePreset = {
  id: PosterStylePresetId;
  label: string;
  description: string;
};

export type PosterOptions = {
  style_presets: PosterStylePreset[];
  default_included_sections: PosterIncludedSection[];
  image_size: string;
  image_quality: string;
  image_model: string;
  usd_krw_rate: number;
  max_posters_per_product: number;
};

export type CreatePosterPayload = {
  style_preset: PosterStylePresetId;
  included_sections: PosterIncludedSection[];
};

export const POSTER_SECTION_LABELS: Record<PosterIncludedSection, string> = {
  product_summary: "상품 요약",
  itinerary: "일정/경험 요소",
  marketing_copy: "마케팅 문구",
  sns_copy: "SNS 문구",
  evidence_summary: "근거 요약",
  claim_limits: "Claim 제한/주의사항",
};

export const DEFAULT_POSTER_INCLUDED_SECTIONS: PosterIncludedSection[] = [
  "product_summary",
  "itinerary",
  "marketing_copy",
  "claim_limits",
];

export const DEFAULT_POSTER_STYLE: PosterStylePresetId = "editorial_travel";

export function getPosterOptions() {
  return apiGet<PosterOptions>("/posters/options");
}

export function listPosters(params: { includeEvaluation?: boolean } = {}) {
  const query = params.includeEvaluation ? "?include_evaluation=true" : "";
  return apiGet<PosterAsset[]>(`/posters${query}`);
}

export function listRunPosters(runId: string) {
  return apiGet<PosterAsset[]>(`/workflow-runs/${runId}/posters`);
}

export function createPoster(runId: string, productId: string, payload: CreatePosterPayload) {
  return apiPost<PosterAsset>(`/workflow-runs/${runId}/products/${productId}/posters`, payload);
}

export function deletePoster(posterId: string) {
  return apiDelete<{ deleted_poster_id: string; deleted_image_path: string | null }>(
    `/posters/${posterId}`
  );
}

export function posterDownloadUrl(posterId: string) {
  return `${API_BASE_URL}/posters/${posterId}/download`;
}

export function posterImageSrc(poster: PosterAsset) {
  if (poster.status !== "succeeded") return "";
  if (poster.image_url?.startsWith("/api/")) {
    return `${API_BASE_URL.replace(/\/api$/, "")}${poster.image_url}`;
  }
  if (poster.image_url?.startsWith("/")) {
    return `${API_BASE_URL}${poster.image_url}`;
  }
  return poster.image_url ?? posterDownloadUrl(poster.id);
}

export function posterCostKrw(poster: PosterAsset, fallbackUsdKrwRate?: number) {
  const breakdown = poster.provider_response_summary?.cost_breakdown;
  if (breakdown && typeof breakdown === "object" && "total_cost_krw" in breakdown) {
    const value = Number((breakdown as { total_cost_krw?: unknown }).total_cost_krw);
    if (Number.isFinite(value)) return value;
  }
  const rateFromBreakdown =
    breakdown && typeof breakdown === "object" && "usd_krw_rate" in breakdown
      ? Number((breakdown as { usd_krw_rate?: unknown }).usd_krw_rate)
      : NaN;
  const rate = Number.isFinite(rateFromBreakdown)
    ? rateFromBreakdown
    : Number(fallbackUsdKrwRate ?? 0);
  return Number.isFinite(rate) ? poster.cost_usd * rate : 0;
}

export function formatPosterCost(poster: PosterAsset, fallbackUsdKrwRate?: number) {
  const costUsd = Number(poster.cost_usd ?? 0);
  const costKrw = posterCostKrw(poster, fallbackUsdKrwRate);
  return `$${costUsd.toFixed(5)} · ₩${Math.round(costKrw).toLocaleString("ko-KR")}`;
}

export function isCountedPosterStatus(status: string) {
  return status === "pending" || status === "running" || status === "succeeded";
}

export function isActivePosterStatus(status: string) {
  return status === "pending" || status === "running";
}
