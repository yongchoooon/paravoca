import { apiGet, apiPost } from "./apiClient";

export type WorkflowRunInput = {
  message: string;
  region?: string;
  period?: string;
  target_customer?: string;
  product_count: number;
  preferences: string[];
  avoid: string[];
  output_language: "ko" | "en";
};

export type WorkflowRun = {
  id: string;
  template_id: string;
  parent_run_id: string | null;
  revision_number: number;
  revision_mode: string | null;
  status: string;
  input: WorkflowRunInput;
  normalized_input: Record<string, unknown> | null;
  final_output: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  cost_total_usd: number;
  latency_ms: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ProductIdea = {
  id: string;
  title: string;
  one_liner: string;
  target_customer: string;
  core_value: string[];
  itinerary: Array<Record<string, unknown>>;
  estimated_duration: string;
  operation_difficulty: string;
  source_ids: string[];
  assumptions: string[];
  not_to_claim: string[];
  evidence_summary?: string;
  needs_review?: string[];
  coverage_notes?: string[];
  claim_limits?: string[];
};

export type MarketingAsset = {
  product_id: string;
  sales_copy: {
    headline: string;
    subheadline: string;
    sections: Array<{ title: string; body: string }>;
    disclaimer: string;
  };
  faq: Array<{ question: string; answer: string }>;
  sns_posts: string[];
  search_keywords: string[];
  evidence_disclaimer?: string;
  claim_limits?: string[];
};

export type EvidenceDocument = {
  doc_id: string;
  title: string;
  content: string;
  snippet: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type QAIssue = {
  product_id?: string;
  severity: string;
  type: string;
  message: string;
  field_path?: string;
  suggested_fix?: string;
};

export type QAReport = {
  overall_status: string;
  summary: string;
  issues: QAIssue[];
  dismissed_issues?: Array<Record<string, unknown>>;
  pass_count: number;
  needs_review_count: number;
  fail_count: number;
};

export type WorkflowResult = {
  status: string;
  reason?: string;
  normalized_request: Record<string, unknown>;
  geo_scope: Record<string, unknown>;
  user_message?: Record<string, unknown>;
  source_items: Array<Record<string, unknown>>;
  retrieved_documents: EvidenceDocument[];
  retrieval_diagnostics?: Record<string, unknown>;
  suggested_next_requests?: string[];
  data_gap_report: Record<string, unknown>;
  enrichment_plan: Record<string, unknown>;
  enrichment_summary: Record<string, unknown>;
  evidence_profile: Record<string, unknown>;
  productization_advice: Record<string, unknown>;
  data_coverage: Record<string, unknown>;
  unresolved_gaps: Array<Record<string, unknown>>;
  source_confidence: number;
  ui_highlights: Array<Record<string, unknown>>;
  research_summary: Record<string, unknown>;
  products: ProductIdea[];
  marketing_assets: MarketingAsset[];
  qa_report: QAReport;
  agent_execution: Array<Record<string, unknown>>;
  cost_summary: Record<string, unknown>;
  revision: Record<string, unknown>;
  approval: Record<string, unknown>;
};

export type AgentStep = {
  id: string;
  run_id: string;
  agent_name: string;
  step_type: string;
  status: string;
  input: unknown;
  output: unknown;
  error: Record<string, unknown> | null;
  latency_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ToolCall = {
  id: string;
  run_id: string;
  step_id: string | null;
  tool_name: string;
  status: string;
  arguments: Record<string, unknown>;
  response_summary: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  source: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type EnrichmentToolCall = {
  id: string;
  plan_id: string | null;
  tool_name: string;
  source_family: string;
  arguments: Record<string, unknown>;
  status: string;
  response_summary: Record<string, unknown> | null;
  error: Record<string, unknown> | null;
  cache_hit: boolean;
  latency_ms: number | null;
  created_at: string | null;
};

export type EnrichmentRun = {
  id: string;
  workflow_run_id: string;
  trigger_type: string;
  status: string;
  gap_report: Record<string, unknown>;
  plan: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  tool_calls: EnrichmentToolCall[];
};

export type WorkflowEnrichmentSummary = {
  latest: EnrichmentRun | null;
  runs: EnrichmentRun[];
};

export type LLMCall = {
  id: string;
  run_id: string;
  step_id: string | null;
  provider: string;
  model: string;
  purpose: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  cache_hit: boolean;
  request_hash: string | null;
  created_at: string;
};

export type Approval = {
  id: string;
  run_id: string;
  decision: string;
  reviewer: string;
  comment: string | null;
  approval_metadata: Record<string, unknown>;
  created_at: string;
};

export type ApprovalActionPayload = {
  reviewer?: string;
  comment?: string | null;
  high_risk_override?: boolean;
  requested_changes?: string[];
};

export type ApprovalActionResult = {
  run: WorkflowRun;
  approval: Approval;
};

export type RevisionMode = "manual_save" | "manual_edit" | "llm_partial_rewrite" | "qa_only";

export type WorkflowRevisionPayload = {
  revision_mode: RevisionMode;
  comment?: string | null;
  requested_changes?: string[];
  qa_issues?: QAIssue[];
  qa_settings?: Record<string, unknown>;
  products?: ProductIdea[];
  marketing_assets?: MarketingAsset[];
};

export type QAIssueDeletePayload = {
  issue_indices: number[];
};

export type QAIssueDeleteResult = {
  run: WorkflowRun;
  qa_report: QAReport;
  removed_count: number;
};

export type WorkflowRunDeletePayload = {
  run_ids: string[];
};

export type WorkflowRunDeleteResult = {
  deleted_run_ids: string[];
  deleted_count: number;
};

export type WorkflowTemplate = {
  id: string;
  name: string;
  description: string;
  version: number;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export function listWorkflowRuns() {
  return apiGet<WorkflowRun[]>("/workflow-runs");
}

export function getWorkflowRun(runId: string) {
  return apiGet<WorkflowRun>(`/workflow-runs/${runId}`);
}

export function getWorkflowRunResult(runId: string) {
  return apiGet<WorkflowResult>(`/workflow-runs/${runId}/result`);
}

export function getWorkflowRunEnrichment(runId: string) {
  return apiGet<WorkflowEnrichmentSummary>(`/workflow-runs/${runId}/enrichment`);
}

export function listRunSteps(runId: string) {
  return apiGet<AgentStep[]>(`/workflow-runs/${runId}/steps`);
}

export function listRunToolCalls(runId: string) {
  return apiGet<ToolCall[]>(`/workflow-runs/${runId}/tool-calls`);
}

export function listRunLlmCalls(runId: string) {
  return apiGet<LLMCall[]>(`/workflow-runs/${runId}/llm-calls`);
}

export function listRunApprovals(runId: string) {
  return apiGet<Approval[]>(`/workflow-runs/${runId}/approvals`);
}

export function listWorkflowTemplates() {
  return apiGet<WorkflowTemplate[]>("/workflows");
}

export function createWorkflowRun(input: WorkflowRunInput) {
  return apiPost<WorkflowRun>("/workflow-runs", {
    template_id: "default_product_planning",
    input,
  });
}

export function approveWorkflowRun(runId: string, payload: ApprovalActionPayload) {
  return apiPost<ApprovalActionResult>(`/workflow-runs/${runId}/approve`, payload);
}

export function rejectWorkflowRun(runId: string, payload: ApprovalActionPayload) {
  return apiPost<ApprovalActionResult>(`/workflow-runs/${runId}/reject`, payload);
}

export function requestWorkflowRunChanges(runId: string, payload: ApprovalActionPayload) {
  return apiPost<ApprovalActionResult>(`/workflow-runs/${runId}/request-changes`, payload);
}

export function createWorkflowRevision(runId: string, payload: WorkflowRevisionPayload) {
  return apiPost<WorkflowRun>(`/workflow-runs/${runId}/revisions`, payload);
}

export function deleteWorkflowRuns(payload: WorkflowRunDeletePayload) {
  return apiPost<WorkflowRunDeleteResult>("/workflow-runs/delete", payload);
}

export function deleteWorkflowRunQaIssues(runId: string, payload: QAIssueDeletePayload) {
  return apiPost<QAIssueDeleteResult>(`/workflow-runs/${runId}/qa-issues/delete`, payload);
}
