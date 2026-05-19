import { apiGet, apiPost } from "./apiClient";

export type EvaluationMetric = {
  name: string;
  passed: boolean;
  score: number | null;
  value: unknown;
  reason: string;
  blocking: boolean;
  evaluator_type?: "code" | "llm" | "human_planned" | string;
  principle?: string;
  expected?: string;
  actual?: string;
  penalty_reason?: string | null;
  next_check?: string;
  not_applicable_reason?: string | null;
  judge_reasoning_summary?: string;
  evidence_quotes_or_refs?: string[];
};

export type EvaluationCaseResult = {
  case_id: string;
  name: string;
  status: "passed" | "failed" | "skipped";
  score: number | null;
  workflow_run_id: string | null;
  input: Record<string, unknown>;
  tags: string[];
  metrics: EvaluationMetric[];
  failures: Array<{ metric: string; reason: string; value: unknown }>;
  source_family_coverage: Array<{
    source_family: string;
    status: string;
    reason: string;
    call_statuses?: string[];
  }>;
  latency_ms: number | null;
  llm_cost_usd: number;
  llm_cost_krw: number;
  skip_reason?: string;
};

export type EvaluationSummary = {
  case_count: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  average_score: number | null;
  llm_cost_usd: number;
  llm_cost_krw: number;
  latency_ms: number;
};

export type EvaluationListItem = {
  eval_id: string;
  name?: string | null;
  dataset: string;
  status?: "running" | "completed" | "failed" | string;
  started_at: string;
  finished_at: string | null;
  summary: EvaluationSummary;
  case_count: number;
  total_case_count?: number;
  passed_count: number;
  failed_count: number;
  skipped_count: number;
  average_score: number | null;
  llm_cost_usd: number;
  llm_cost_krw: number;
  path: string | null;
};

export type EvaluationReport = {
  eval_id: string;
  name?: string | null;
  dataset: string;
  status?: "running" | "completed" | "failed" | string;
  started_at: string;
  finished_at: string | null;
  summary: EvaluationSummary;
  total_case_count?: number;
  cases: EvaluationCaseResult[];
  options: Record<string, unknown>;
};

export type EvaluationDeletePayload = {
  eval_ids: string[];
};

export type EvaluationDeleteResult = {
  deleted_eval_ids: string[];
  deleted_count: number;
  deleted_workflow_run_ids?: string[];
  deleted_workflow_run_count?: number;
  terminated_eval_processes?: Array<{
    eval_id?: string;
    pid?: number | null;
    status: string;
    error?: string;
  }>;
  missing_eval_ids?: string[];
  invalid_eval_ids?: string[];
};

export async function listEvaluations(): Promise<EvaluationListItem[]> {
  return apiGet<EvaluationListItem[]>("/evaluations");
}

export async function getEvaluation(evalId: string): Promise<EvaluationReport> {
  return apiGet<EvaluationReport>(`/evaluations/${evalId}`);
}

export async function deleteEvaluations(payload: EvaluationDeletePayload): Promise<EvaluationDeleteResult> {
  return apiPost<EvaluationDeleteResult>("/evaluations/delete", payload);
}
