import type {
  EvidenceDocument,
  MarketingAsset,
  ProductIdea,
  QAIssue,
  QAReport,
  WorkflowResult,
  WorkflowRun,
} from "../services/runsApi";

export type WorkflowStage = {
  key: string;
  label: string;
  description: string;
  agentName: string;
  stepType: string;
};

export type RevisionQaSettings = {
  region: string;
  period: string;
  target_customer: string;
  product_count: number;
  preferences: string[];
  avoid: string[];
  output_language: "ko" | "en";
};

export const workflowStages: WorkflowStage[] = [
  {
    key: "revision_context",
    label: "Revision",
    description: "원본 run과 수정 요청을 revision context로 정리합니다.",
    agentName: "RevisionContextAgent",
    stepType: "revision_context",
  },
  {
    key: "planner",
    label: "Planner",
    description: "요청을 정규화하고 실행 계획을 만듭니다.",
    agentName: "PlannerAgent",
    stepType: "planner",
  },
  {
    key: "geo",
    label: "Geo",
    description: "자연어 요청에서 지역 범위를 해석합니다.",
    agentName: "GeoResolverAgent",
    stepType: "geo_resolution",
  },
  {
    key: "data",
    label: "Data",
    description: "해석된 지역 범위로 TourAPI 데이터를 수집합니다.",
    agentName: "DataAgent",
    stepType: "data_collection",
  },
  {
    key: "research",
    label: "Research",
    description: "RAG 근거를 검색하고 지역/시즌 맥락을 요약합니다.",
    agentName: "ResearchAgent",
    stepType: "research",
  },
  {
    key: "product",
    label: "Product",
    description: "근거 문서를 바탕으로 상품 초안을 생성합니다.",
    agentName: "ProductAgent",
    stepType: "product_generation",
  },
  {
    key: "marketing",
    label: "Marketing",
    description: "상세페이지 카피, FAQ, SNS 문구, 검색 키워드를 생성합니다.",
    agentName: "MarketingAgent",
    stepType: "marketing_generation",
  },
  {
    key: "qa",
    label: "QA",
    description: "과장 표현, 출처 누락, 날짜/가격 단정 표현을 검수합니다.",
    agentName: "QAComplianceAgent",
    stepType: "qa_review",
  },
  {
    key: "approval",
    label: "Human Approval",
    description: "검토 담당자의 승인 단계로 전환합니다.",
    agentName: "HumanApprovalNode",
    stepType: "human_approval",
  },
];

export const revisionModeLabel: Record<string, string> = {
  manual_save: "저장",
  manual_edit: "직접 수정",
  llm_partial_rewrite: "AI 수정",
  qa_only: "QA 재검수",
};

export const preferenceOptions = ["야간 관광", "축제", "전통시장", "해변", "요트", "푸드투어"];

export const avoidOptions = [
  "가격 단정 표현",
  "과장 표현",
  "출처 없는 주장",
  "예약 가능 여부 단정",
  "일정 단정 표현",
  "절대적 안전 보장",
  "외국어 지원 과장 표현",
];

export const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);

const severityConfig: Record<string, { label: string; color: string }> = {
  critical: { label: "치명", color: "red" },
  high: { label: "높음", color: "red" },
  medium: { label: "보통", color: "yellow" },
  low: { label: "낮음", color: "blue" },
  info: { label: "정보", color: "gray" },
};

const issueTypeLabel: Record<string, string> = {
  general: "일반",
  prohibited_phrase: "금지 표현",
  source_missing: "출처 누락",
  source_evidence: "출처 근거",
  price_claim: "가격 단정",
  schedule_claim: "일정 단정",
  reservation_claim: "예약 단정",
  availability_claim: "예약 단정",
  safety_claim: "안전 보장",
  language_claim: "외국어 지원",
};

export function arrayOrEmpty<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function splitLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function joinLines(value: string[] | undefined) {
  return (value ?? []).join("\n");
}

export function revisionQaSettingsFromRun(run: WorkflowRun | null): RevisionQaSettings {
  return {
    region: run?.input.region ?? "",
    period: run?.input.period ?? "",
    target_customer: run?.input.target_customer ?? "외국인",
    product_count: run?.input.product_count ?? 3,
    preferences: run?.input.preferences ?? [],
    avoid: run?.input.avoid ?? [],
    output_language: run?.input.output_language ?? "ko",
  };
}

export function qaIssueKey(issue: QAIssue, index: number) {
  return `${issue.product_id ?? "all"}:${issue.type}:${issue.severity}:${index}`;
}

export function qaIssueKeys(report: QAReport) {
  return report.issues.map((issue, index) => qaIssueKey(issue, index));
}

export function qaIssueRevisionText(
  issue: QAIssue,
  index: number,
  productTitleById: Map<string, string>
) {
  const product = issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체 상품";
  const fix = formatSuggestedFix(issue);
  return [
    `${index + 1}. ${product} - ${formatIssueType(issue.type)} / ${formatSeverity(issue.severity)}`,
    `문제: ${formatQaMessage(issue)}`,
    `수정 방향: ${fix}`,
  ].join("\n");
}

export function recordOrEmpty(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function formatJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function errorMessage(value: unknown) {
  const record = recordOrEmpty(value);
  if (typeof record.message === "string" && record.message.trim()) {
    return record.message;
  }
  if (typeof record.type === "string" && record.type.trim()) {
    return record.type;
  }
  if (value == null) {
    return "";
  }
  return JSON.stringify(value);
}

export function formatSeverity(value: string) {
  const key = value.toLowerCase();
  return severityConfig[key]?.label ?? value;
}

export function severityColor(value: string) {
  const key = value.toLowerCase();
  return severityConfig[key]?.color ?? "gray";
}

export function formatIssueType(value: string) {
  const key = value.toLowerCase();
  return issueTypeLabel[key] ?? "일반";
}

export function formatQaMessage(issue: QAIssue) {
  return stripQaFixSentence(stripInternalFieldPaths(issue.message));
}

export function formatSuggestedFix(issue: QAIssue) {
  const directFix = issue.suggested_fix?.trim();
  if (directFix) {
    return stripInternalFieldPaths(directFix);
  }
  return extractSuggestedFix(issue.message);
}

export function stripInternalFieldPaths(text: string) {
  const withPathLabels = text.replace(
    /['"]?([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\]|\.[A-Za-z_][A-Za-z0-9_]*)+)['"]?/g,
    (_match, path: string) => fieldPathLabel(path)
  );
  return withPathLabels
    .replace(/\bdisclaimer\b/g, "유의 문구")
    .replace(/\bnot_to_claim\b/g, "운영 주의사항")
    .replace(/\bassumptions\b/g, "운영 가정")
    .replace(/\bsales_copy\b/g, "판매 문구")
    .replace(/\bmarketing_assets\b/g, "마케팅 문구");
}

export function fieldPathLabel(path: string) {
  const normalized = path.toLowerCase();
  if (normalized === "disclaimer") return "유의 문구";
  if (normalized === "not_to_claim") return "운영 주의사항";
  if (normalized === "assumptions") return "운영 가정";
  if (normalized.includes("sales_copy.headline")) return "헤드라인";
  if (normalized.includes("sales_copy.subheadline")) return "보조 문구";
  if (normalized.includes("sales_copy.disclaimer")) return "유의 문구";
  if (normalized.includes("sales_copy.sections")) return "상세 설명";
  if (normalized.startsWith("faq") && normalized.includes(".question")) return "FAQ 질문";
  if (normalized.startsWith("faq") && normalized.includes(".answer")) return "FAQ 답변";
  if (normalized.startsWith("sns_posts")) return "SNS 문구";
  if (normalized.startsWith("search_keywords")) return "검색 키워드";
  if (normalized.startsWith("marketing_assets")) return "마케팅 자산";
  if (normalized.startsWith("products")) return "상품 정보";
  return "해당 항목";
}

export function extractSuggestedFix(message: string) {
  const sanitizedMessage = stripInternalFieldPaths(message);
  const patterns = [
    /'([^']+)'(?:와|과) 같이 수정하는 것을 권장합니다/,
    /"([^"]+)"(?:와|과) 같이 수정하는 것을 권장합니다/,
    /'([^']+)'(?:로|으로) 수정/,
    /"([^"]+)"(?:로|으로) 수정/,
  ];
  for (const pattern of patterns) {
    const match = sanitizedMessage.match(pattern);
    if (match?.[1]) {
      return `'${match[1]}'처럼 완화된 표현으로 수정하세요.`;
    }
  }
  return "표현을 완화하고, 운영자가 확인 가능한 조건형 문장으로 수정하세요.";
}

export function stripQaFixSentence(text: string) {
  return [
    /\s*['"][^'"]+['"](?:와|과) 같이 수정하는 것을 권장합니다\.?/g,
    /\s*['"][^'"]+['"](?:로|으로) 수정하는 것을 권장합니다\.?/g,
    /\s*['"][^'"]+['"](?:처럼) 완화된 표현으로 수정하세요\.?/g,
  ].reduce((result, pattern) => result.replace(pattern, ""), text).trim();
}

export function normalizeQaReport(value: unknown): QAReport {
  const report = recordOrEmpty(value);
  const issues = arrayOrEmpty<QAIssue>(report.issues);
  const rawStatus = typeof report.overall_status === "string" ? report.overall_status : "-";
  const rawNeedsReviewCount =
    typeof report.needs_review_count === "number" ? report.needs_review_count : 0;
  const rawFailCount = typeof report.fail_count === "number" ? report.fail_count : 0;
  const hasInconsistentEmptyIssues =
    issues.length === 0 && (rawStatus !== "pass" || rawNeedsReviewCount > 0 || rawFailCount > 0);

  if (hasInconsistentEmptyIssues) {
    return {
      overall_status: "pass",
      summary: "QA 검수 완료. 차단 수준의 이슈가 없습니다.",
      issues: [],
      dismissed_issues: arrayOrEmpty<Record<string, unknown>>(report.dismissed_issues),
      pass_count: typeof report.pass_count === "number" ? report.pass_count : 0,
      needs_review_count: 0,
      fail_count: 0,
    };
  }

  return {
    overall_status: rawStatus,
    summary: typeof report.summary === "string" ? report.summary : "이 run에서 확인할 수 있는 QA report가 없습니다.",
    issues,
    dismissed_issues: arrayOrEmpty<Record<string, unknown>>(report.dismissed_issues),
    pass_count: typeof report.pass_count === "number" ? report.pass_count : 0,
    needs_review_count: rawNeedsReviewCount,
    fail_count: rawFailCount,
  };
}

export function normalizeWorkflowResult(raw: unknown): WorkflowResult {
  const result = recordOrEmpty(raw);
  return {
    status: typeof result.status === "string" ? result.status : "not_available",
    normalized_request: recordOrEmpty(result.normalized_request),
    geo_scope: recordOrEmpty(result.geo_scope),
    user_message: recordOrEmpty(result.user_message),
    source_items: arrayOrEmpty(result.source_items),
    retrieved_documents: arrayOrEmpty<EvidenceDocument>(result.retrieved_documents),
    research_summary: recordOrEmpty(result.research_summary),
    products: arrayOrEmpty<ProductIdea>(result.products),
    marketing_assets: arrayOrEmpty<MarketingAsset>(result.marketing_assets),
    qa_report: normalizeQaReport(result.qa_report),
    agent_execution: arrayOrEmpty<Record<string, unknown>>(result.agent_execution),
    cost_summary: recordOrEmpty(result.cost_summary),
    revision: recordOrEmpty(result.revision),
    approval: recordOrEmpty(result.approval),
  };
}
