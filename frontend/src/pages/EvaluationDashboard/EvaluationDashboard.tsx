import { useEffect, useMemo, useState } from "react";
import {
  Accordion,
  Badge,
  Button,
  Checkbox,
  Code,
  Drawer,
  Group,
  Loader,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconRefresh, IconTrash } from "@tabler/icons-react";
import {
  deleteEvaluations,
  EvaluationCaseResult,
  EvaluationListItem,
  EvaluationMetric,
  EvaluationReport,
  getEvaluation,
  listEvaluations,
} from "../../services/evaluationsApi";
import { formatKstDateTime } from "../../utils/datetime";
import { RunDetail } from "../RunDetail";
import classes from "./EvaluationDashboard.module.css";

function statusColor(status: string) {
  if (status === "passed") return "green";
  if (status === "failed") return "red";
  if (status === "skipped") return "gray";
  return "blue";
}

function evaluationTitle(report: EvaluationListItem | EvaluationReport) {
  return report.name || report.dataset;
}

function evaluationIsRunning(report: EvaluationListItem | EvaluationReport | null) {
  return report?.status === "running";
}

function evaluationIsStopped(report: EvaluationListItem | EvaluationReport | null) {
  return report?.status === "stopped" || report?.status === "cancelled";
}

function evaluationStatusLabel(report: EvaluationListItem | EvaluationReport) {
  if (evaluationIsRunning(report)) return "진행 중";
  if (evaluationIsStopped(report)) return "멈춤";
  if (report.status === "failed") return "실패";
  return "완료";
}

function evaluationStatusColor(report: EvaluationListItem | EvaluationReport) {
  if (evaluationIsRunning(report)) return "blue";
  if (evaluationIsStopped(report)) return "gray";
  if (report.status === "failed") return "red";
  return "green";
}

function evaluationProgressText(report: EvaluationListItem | EvaluationReport) {
  const completed = report.summary?.case_count ?? ("cases" in report ? report.cases.length : report.case_count) ?? 0;
  const total = report.total_case_count ?? completed;
  return `${completed}/${total}`;
}

function metricHasPartialScore(metric: EvaluationMetric) {
  return typeof metric.score === "number" && metric.score < 1;
}

function metricScoreColor(metric: EvaluationMetric) {
  if (metric.score === null || metric.score === undefined) return "gray";
  if (metric.blocking && !metric.passed) return "red";
  if (metricHasPartialScore(metric)) return "yellow";
  if (metric.passed) return "green";
  return "gray";
}

function metricScoreLabel(metric: EvaluationMetric) {
  if (metric.score === null || metric.score === undefined) {
    return "-";
  }
  return String(metric.score);
}

function evaluatorLabel(type?: string) {
  if (type === "llm") return "LLM 평가";
  if (type === "human_planned") return "사람 평가 예정";
  return "코드 검사";
}

function evaluatorColor(type?: string) {
  if (type === "llm") return "violet";
  if (type === "human_planned") return "gray";
  return "blue";
}

function countLabel(value: unknown) {
  return `${typeof value === "number" && Number.isFinite(value) ? value : 0}개`;
}

function metricLabel(name: string) {
  const labels: Record<string, string> = {
    geo_resolution_accuracy: "지역 해석",
    unsupported_or_clarification_accuracy: "지원 불가/확인 필요",
    retrieval_result_count: "검색 결과 수",
    source_document_indexed_count: "색인 문서 수",
    expected_source_family_coverage: "데이터 소스 커버리지",
    enrichment_call_success_rate: "보강 호출 상태",
    evidence_document_validity: "근거 문서 ID",
    product_count_satisfaction: "상품 개수",
    product_source_id_validity: "상품 근거 연결",
    claim_limit_compliance: "Claim 제한 준수",
    qa_issue_detection: "QA 리스크 감지",
    workflow_success: "Workflow 완료",
    latency_ms: "지연 시간",
    llm_cost_usd: "LLM 비용 USD",
    llm_cost_krw: "LLM 비용 KRW",
  };
  return labels[name] ?? name;
}

function shortReason(caseResult: EvaluationCaseResult) {
  if (caseResult.skip_reason) return caseResult.skip_reason;
  const first = caseResult.failures[0];
  if (first?.reason) return first.reason;
  return caseResult.status === "passed" ? "핵심 평가 기준을 통과했습니다." : "-";
}

function metricPrinciple(name: string) {
  const principles: Record<string, string> = {
    claim_limit_compliance:
      "과거 코드 기반 claim 제한 점검 항목입니다. 신규 평가는 문장 맥락을 보는 LLM Judge가 담당합니다.",
    expected_source_family_coverage:
      "데이터셋이 기대한 KTO source family가 source document metadata 또는 enrichment call 결과에 나타났는지 확인합니다.",
    geo_resolution_accuracy:
      "GeoResolver 결과의 지역 모드와 TourAPI ldong 시도/시군구 코드가 데이터셋 기대값과 일치하는지 확인합니다.",
    product_source_id_validity:
      "상품이 참조한 source_ids가 실제 retrieved_documents의 doc_id에 존재하는지 확인합니다.",
    product_count_satisfaction:
      "요청 상품 수, 최대 20개 제한, 근거 부족 시 가능한 개수 생성 정책을 기준으로 상품 개수를 확인합니다.",
    workflow_success:
      "워크플로우가 승인 대기 등 검토 가능한 상태로 끝났는지, 또는 지원 불가/데이터 부족처럼 통제된 종료인지 확인합니다.",
    qa_issue_detection:
      "과거 코드 기반 QA 리스크 점검 항목입니다. 신규 평가는 문장 맥락을 보는 LLM Judge가 담당합니다.",
  };
  return principles[name] ?? "이 metric은 workflow 결과 JSON과 실행 로그를 기준으로 운영 진단에 필요한 조건을 검사합니다.";
}

function metricPrincipleText(metric: EvaluationMetric) {
  if (metric.name === "claim_limit_compliance" || metric.name === "qa_issue_detection") {
    return metricPrinciple(metric.name);
  }
  return metric.principle || metricPrinciple(metric.name);
}

function metricExpectedText(metric: EvaluationMetric) {
  if (metric.name === "claim_limit_compliance" || metric.name === "qa_issue_detection") {
    return "신규 평가는 LLM Judge의 claim 위험 평가를 기준으로 확인하세요.";
  }
  if (metric.expected) return metric.expected;
  if (metric.name === "retrieval_result_count") {
    const value = metric.value as { expected_min_count_for_full_score?: number } | undefined;
    return `사용 가능한 근거 문서가 ${value?.expected_min_count_for_full_score ?? 3}개 이상이면 1점입니다.`;
  }
  if (metric.name === "source_document_indexed_count") {
    const value = metric.value as { expected_min_count_for_full_score?: number } | undefined;
    return `저장/색인된 source document가 ${value?.expected_min_count_for_full_score ?? 3}개 이상이면 1점입니다.`;
  }
  if (metric.name === "qa_issue_detection") {
    return "이 항목은 과거 코드 기반 평가 결과입니다. 신규 평가는 LLM Judge의 claim 위험 평가를 확인하세요.";
  }
  return metricPrincipleText(metric);
}

function metricActualText(metric: EvaluationMetric) {
  if (metric.name === "retrieval_result_count") {
    if (metric.value === "not_applicable") return "이 케이스는 검색 결과 수 평가 대상이 아닙니다.";
    const value = metric.value as {
      retrieved_documents?: number;
      vector_search_result_count?: number | null;
      post_geo_filter_result_count?: number | null;
    } | undefined;
    if (typeof value?.retrieved_documents === "number") {
      return (
        `사용 가능한 근거 문서가 ${value.retrieved_documents}개입니다. ` +
        `Vector 검색 결과 ${countLabel(value.vector_search_result_count)}, 지역 필터 후 ${countLabel(value.post_geo_filter_result_count)}입니다.`
      );
    }
  }
  if (metric.name === "source_document_indexed_count") {
    if (metric.value === "not_applicable") return "이 케이스는 색인 문서 수 평가 대상이 아닙니다.";
    const value = metric.value as {
      indexed_or_upserted_documents?: number | null;
      indexed_document_count?: number | null;
      source_document_upsert_count?: number | null;
    } | undefined;
    if (typeof value?.indexed_or_upserted_documents === "number") {
      return (
        `저장/색인된 source document가 ${value.indexed_or_upserted_documents}개입니다. ` +
        `색인 ${countLabel(value.indexed_document_count)}, 저장 ${countLabel(value.source_document_upsert_count)}입니다.`
      );
    }
  }
  if (metric.actual) return metric.actual;
  if (metric.name === "qa_issue_detection") {
    const value = metric.value as { issue_count?: number; matched_claim_limits?: string[] } | undefined;
    const matched = Array.isArray(value?.matched_claim_limits) ? value.matched_claim_limits : [];
    if (typeof value?.issue_count === "number" || matched.length > 0) {
      return `QA issue ${value?.issue_count ?? 0}개, 감지된 claim risk ${matched.length}개${matched.length > 0 ? `: ${matched.join(", ")}` : ""}`;
    }
  }
  return metric.reason;
}

function metricPenaltyText(metric: EvaluationMetric) {
  if (metric.penalty_reason) return metric.penalty_reason;
  if (metric.name === "retrieval_result_count" && metricHasPartialScore(metric)) {
    const value = metric.value as { expected_min_count_for_full_score?: number } | undefined;
    return `근거 문서가 ${value?.expected_min_count_for_full_score ?? 3}개 미만이라 상품 생성 근거가 약합니다.`;
  }
  if (metric.name === "source_document_indexed_count" && metricHasPartialScore(metric)) {
    const value = metric.value as { expected_min_count_for_full_score?: number } | undefined;
    return `저장/색인 문서가 ${value?.expected_min_count_for_full_score ?? 3}개 미만이라 RAG 입력이 약합니다.`;
  }
  if (metric.name === "qa_issue_detection" && metricHasPartialScore(metric)) {
    const value = metric.value as { matched_claim_limits?: string[] } | undefined;
    const matched = Array.isArray(value?.matched_claim_limits) ? value.matched_claim_limits : [];
    return matched.length > 0
      ? "일부 claim risk만 QA/결과 텍스트에서 확인됐습니다."
      : "기대 claim risk가 QA/결과 텍스트에서 확인되지 않았습니다.";
  }
  return metric.reason;
}

function sameText(left?: string | null, right?: string | null) {
  return (left ?? "").trim() === (right ?? "").trim();
}

function shouldShowPenalty(metric: EvaluationMetric) {
  const penalty = metricPenaltyText(metric);
  if (!penalty) return false;
  return !sameText(penalty, metricActualText(metric)) && !sameText(penalty, metric.reason);
}

function shouldShowNextCheck(metric: EvaluationMetric) {
  if (!metric.next_check) return false;
  return metric.next_check !== "Developer JSON과 연결된 workflow run detail을 확인하세요.";
}

export function EvaluationDashboard() {
  const [reports, setReports] = useState<EvaluationListItem[]>([]);
  const [selectedEvalId, setSelectedEvalId] = useState<string | null>(null);
  const [selectedReport, setSelectedReport] = useState<EvaluationReport | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDeleteEvalIds, setSelectedDeleteEvalIds] = useState<string[]>([]);
  const [deletingReports, setDeletingReports] = useState(false);
  const [selectedWorkflowRunId, setSelectedWorkflowRunId] = useState<string | null>(null);

  async function loadReports(preferredEvalId: string | null = selectedEvalId, options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setLoading(true);
      }
      setError(null);
      const nextReports = await listEvaluations();
      setReports(nextReports);
      const nextId =
        preferredEvalId && nextReports.some((report) => report.eval_id === preferredEvalId)
          ? preferredEvalId
          : nextReports[0]?.eval_id ?? null;
      setSelectedEvalId(nextId);
      if (nextId) {
        await loadReport(nextId, { silent: options.silent });
      } else {
        setSelectedReport(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation report를 불러오지 못했습니다.");
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  async function loadReport(evalId: string, options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setDetailLoading(true);
      }
      setError(null);
      const report = await getEvaluation(evalId);
      setSelectedReport(report);
      setSelectedEvalId(evalId);
      setSelectedCaseId((current) =>
        current && report.cases.some((caseResult) => caseResult.case_id === current)
          ? current
          : report.cases[0]?.case_id ?? null
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation detail을 불러오지 못했습니다.");
    } finally {
      if (!options.silent) {
        setDetailLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadReports();
  }, []);

  useEffect(() => {
    const hasRunningReport = reports.some(evaluationIsRunning) || evaluationIsRunning(selectedReport);
    if (!hasRunningReport) return undefined;
    const timer = window.setInterval(() => {
      void loadReports(selectedEvalId, { silent: true });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [reports, selectedEvalId, selectedReport]);

  useEffect(() => {
    const existingIds = new Set(reports.map((report) => report.eval_id));
    setSelectedDeleteEvalIds((current) => current.filter((evalId) => existingIds.has(evalId)));
  }, [reports]);

  const selectedCase = useMemo(
    () => selectedReport?.cases.find((caseResult) => caseResult.case_id === selectedCaseId) ?? null,
    [selectedCaseId, selectedReport]
  );

  const deletableReports = useMemo(() => reports, [reports]);
  const allReportsSelected =
    deletableReports.length > 0 && deletableReports.every((report) => selectedDeleteEvalIds.includes(report.eval_id));
  const someReportsSelected =
    deletableReports.some((report) => selectedDeleteEvalIds.includes(report.eval_id)) && !allReportsSelected;

  function toggleReportSelection(evalId: string, checked: boolean) {
    setSelectedDeleteEvalIds((current) =>
      checked
        ? Array.from(new Set([...current, evalId]))
        : current.filter((item) => item !== evalId)
    );
  }

  function toggleAllReports(checked: boolean) {
    setSelectedDeleteEvalIds(checked ? deletableReports.map((report) => report.eval_id) : []);
  }

  async function deleteSelectedReports() {
    if (selectedDeleteEvalIds.length === 0) return;
    const confirmed = window.confirm(
      `선택한 evaluation report ${selectedDeleteEvalIds.length}개를 삭제할까요? 실행 중인 평가는 터미널 프로세스를 종료하고, 이 평가가 생성한 workflow run도 함께 삭제됩니다.`
    );
    if (!confirmed) return;
    try {
      setDeletingReports(true);
      const result = await deleteEvaluations({ eval_ids: selectedDeleteEvalIds });
      const deleted = new Set(result.deleted_eval_ids);
      const nextSelectedId =
        selectedEvalId && !deleted.has(selectedEvalId)
          ? selectedEvalId
          : reports.find((report) => !deleted.has(report.eval_id))?.eval_id ?? null;
      setSelectedDeleteEvalIds([]);
      notifications.show({
        color: "green",
        title: "Evaluation deleted",
        message: `${result.deleted_count}개 evaluation report와 연결된 workflow run ${result.deleted_workflow_run_count ?? 0}개를 삭제했습니다. 종료 요청 ${result.terminated_eval_processes?.length ?? 0}건.`,
      });
      await loadReports(nextSelectedId);
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Evaluation 삭제 실패",
        message: err instanceof Error ? err.message : "선택한 evaluation report를 삭제하지 못했습니다.",
      });
    } finally {
      setDeletingReports(false);
    }
  }

  if (loading) {
    return (
      <Stack align="center" py="xl">
        <Loader />
        <Text c="dimmed" size="sm">Evaluation reports loading...</Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <div>
          <Title order={2}>Evaluation</Title>
          <Text c="dimmed" size="sm">
            지역 해석, 데이터 수집, enrichment, 근거 기반 상품 생성, QA claim 제한을 run 단위로 진단합니다.
          </Text>
        </div>
        <Button variant="light" leftSection={<IconRefresh size={16} />} onClick={() => void loadReports()}>
          Refresh
        </Button>
      </Group>

      {error ? (
        <Paper withBorder p="md">
          <Text c="red">{error}</Text>
        </Paper>
      ) : null}

      {reports.length === 0 ? (
        <Paper withBorder p="md">
          <Text fw={700}>아직 evaluation report가 없습니다.</Text>
          <Text c="dimmed" size="sm">
            backend에서 `python -m app.evals.run_eval --dataset smoke --limit 3 --no-live-api`를 실행하면 이 화면에 report가 표시됩니다.
          </Text>
        </Paper>
      ) : (
        <div className={classes.layout}>
          <Paper withBorder p="md">
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={700}>Recent eval runs</Text>
                <Badge variant="light" color="gray">{reports.length}</Badge>
              </Group>
              <Group justify="space-between" gap="xs">
                <Checkbox
                  size="xs"
                  label="전체 선택"
                  checked={allReportsSelected}
                  indeterminate={someReportsSelected}
                  disabled={deletableReports.length === 0}
                  onChange={(event) => toggleAllReports(event.currentTarget.checked)}
                />
                <Button
                  size="xs"
                  color="red"
                  variant="light"
                  leftSection={<IconTrash size={14} />}
                  disabled={selectedDeleteEvalIds.length === 0}
                  loading={deletingReports}
                  onClick={deleteSelectedReports}
                >
                  선택 삭제{selectedDeleteEvalIds.length > 0 ? ` (${selectedDeleteEvalIds.length})` : ""}
                </Button>
              </Group>
              <div className={classes.reportList}>
                <Stack gap="xs">
                  {reports.map((report) => {
                    const reportTitle = evaluationTitle(report);
                    const isRunning = evaluationIsRunning(report);
                    return (
                      <Paper
                        key={report.eval_id}
                        className={`${classes.reportButton} ${isRunning ? classes.runningReportButton : ""}`}
                        withBorder={report.eval_id === selectedEvalId}
                        p="xs"
                        onClick={() => void loadReport(report.eval_id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            void loadReport(report.eval_id);
                          }
                        }}
                      >
                        <Group wrap="nowrap" align="flex-start">
                          <Checkbox
                            size="xs"
                            checked={selectedDeleteEvalIds.includes(report.eval_id)}
                            aria-label={`${reportTitle} evaluation 선택`}
                            onClick={(event) => event.stopPropagation()}
                            onChange={(event) => toggleReportSelection(report.eval_id, event.currentTarget.checked)}
                            mt={2}
                          />
                          <Stack gap={2} align="flex-start" className={classes.reportButtonContent}>
                            <Group gap="xs" wrap="nowrap">
                              <Text size="sm" fw={700}>{reportTitle}</Text>
                              <Badge size="xs" color={evaluationStatusColor(report)} variant="light">
                                {evaluationStatusLabel(report)}
                              </Badge>
                            </Group>
                            {report.name ? (
                              <Text size="xs" c="dimmed">Dataset: {report.dataset}</Text>
                            ) : null}
                            <Text size="xs" c="dimmed">{formatKstDateTime(report.started_at)}</Text>
                            <Group gap="xs">
                              {isRunning ? (
                                <Badge size="xs" color="blue" variant="light">진행 {evaluationProgressText(report)}</Badge>
                              ) : null}
                              <Badge size="xs" color="green" variant="light">P {report.passed_count}</Badge>
                              <Badge size="xs" color="red" variant="light">F {report.failed_count}</Badge>
                              <Badge size="xs" color="gray" variant="light">S {report.skipped_count}</Badge>
                            </Group>
                          </Stack>
                        </Group>
                      </Paper>
                    );
                  })}
                </Stack>
              </div>
              <Stack gap={4} className={classes.judgeHint}>
                <Group gap="xs">
                  <Text fw={700} size="xs">LLM Judge</Text>
                  <Badge size="xs" variant="light" color="violet">선택 실행</Badge>
                </Group>
                <Text size="xs" c="dimmed">- 완성된 상품, 근거, 마케팅 문구를 함께 봅니다.</Text>
                <Text size="xs" c="dimmed">- 요청에 맞는지와 근거 활용이 자연스러운지 확인합니다.</Text>
                <Text size="xs" c="dimmed">- 과장되거나 위험한 단정 표현을 보조로 잡습니다.</Text>
                <Text size="xs" c="dimmed">- 점수는 최종 판정이 아니라 재검토 참고입니다.</Text>
              </Stack>
            </Stack>
          </Paper>

          <Stack gap="md">
            {detailLoading ? (
              <Paper withBorder p="md">
                <Group>
                  <Loader size="sm" />
                  <Text c="dimmed" size="sm">Report detail loading...</Text>
                </Group>
              </Paper>
            ) : null}

            {selectedReport ? (
              <>
                <Paper withBorder p="md">
                  <Group justify="space-between" align="flex-start">
                    <div>
                      <Group gap="xs">
                        <Title order={3}>{evaluationTitle(selectedReport)}</Title>
                        <Badge color={evaluationStatusColor(selectedReport)} variant="light">
                          {evaluationStatusLabel(selectedReport)}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed">
                        Dataset: {selectedReport.dataset}
                      </Text>
                    </div>
                    <Text size="xs" ff="monospace" c="dimmed">
                      {selectedReport.eval_id}
                    </Text>
                  </Group>
                </Paper>

                {evaluationIsRunning(selectedReport) ? (
                  <Paper withBorder p="md" className={classes.runningNotice}>
                    <Group gap="sm" align="flex-start">
                      <Loader size="sm" />
                      <div>
                        <Text fw={700}>Evaluation 진행 중입니다.</Text>
                        <Text size="sm" c="dimmed">
                          완료된 케이스 {evaluationProgressText(selectedReport)}개를 표시합니다. 아직 완료된 케이스가 없으면 상세 내용은 비어 있을 수 있습니다.
                        </Text>
                      </div>
                    </Group>
                  </Paper>
                ) : null}

                <SimpleGrid cols={{ base: 1, md: 4 }}>
                  <Paper withBorder p="md">
                    <Text c="dimmed" size="sm">Pass / Fail / Skip</Text>
                    <Title order={3}>
                      {selectedReport.summary.passed_count} / {selectedReport.summary.failed_count} / {selectedReport.summary.skipped_count}
                    </Title>
                  </Paper>
                  <Paper withBorder p="md">
                    <Text c="dimmed" size="sm">Average score</Text>
                    <Title order={3}>{selectedReport.summary.average_score ?? "-"}</Title>
                  </Paper>
                  <Paper withBorder p="md">
                    <Text c="dimmed" size="sm">LLM cost</Text>
                    <Title order={3}>₩{Math.round(selectedReport.summary.llm_cost_krw ?? 0).toLocaleString()}</Title>
                    <Text c="dimmed" size="xs">${(selectedReport.summary.llm_cost_usd ?? 0).toFixed(4)}</Text>
                  </Paper>
                  <Paper withBorder p="md">
                    <Text c="dimmed" size="sm">Latency</Text>
                    <Title order={3}>{Math.round((selectedReport.summary.latency_ms ?? 0) / 1000)}s</Title>
                  </Paper>
                </SimpleGrid>

                {selectedReport.cases.length > 0 ? (
                  <Paper withBorder>
                    <ScrollArea>
                      <Table striped highlightOnHover verticalSpacing="sm" className={classes.caseTable}>
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th className={classes.caseColumn}>Case</Table.Th>
                            <Table.Th className={classes.statusColumn}>Status</Table.Th>
                            <Table.Th className={classes.scoreColumn}>Score</Table.Th>
                            <Table.Th className={classes.runColumn}>Run</Table.Th>
                            <Table.Th className={classes.costColumn}>Cost</Table.Th>
                            <Table.Th className={classes.reasonColumn}>Reason</Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {selectedReport.cases.map((caseResult) => (
                            <Table.Tr
                              key={caseResult.case_id}
                              onClick={() => setSelectedCaseId(caseResult.case_id)}
                              style={{ cursor: "pointer" }}
                            >
                              <Table.Td>
                                <Text fw={700} size="sm" lineClamp={1}>{caseResult.name}</Text>
                                <Text ff="monospace" size="xs" c="dimmed">{caseResult.case_id}</Text>
                              </Table.Td>
                              <Table.Td>
                                <Badge color={statusColor(caseResult.status)} variant="light">
                                  {caseResult.status}
                                </Badge>
                              </Table.Td>
                              <Table.Td>{caseResult.score ?? "-"}</Table.Td>
                              <Table.Td>
                                <Text ff="monospace" size="xs" lineClamp={1}>{caseResult.workflow_run_id ?? "-"}</Text>
                              </Table.Td>
                              <Table.Td>₩{Math.round(caseResult.llm_cost_krw ?? 0).toLocaleString()}</Table.Td>
                              <Table.Td>
                                <Text size="sm" lineClamp={2}>{shortReason(caseResult)}</Text>
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </ScrollArea>
                  </Paper>
                ) : (
                  <Paper withBorder p="md">
                    <Text fw={700}>아직 완료된 evaluation case가 없습니다.</Text>
                    <Text size="sm" c="dimmed">첫 케이스가 끝나면 결과가 이 영역에 표시됩니다.</Text>
                  </Paper>
                )}

                {selectedCase ? (
                  <CaseDetail
                    caseResult={selectedCase}
                    onOpenRun={(runId) => setSelectedWorkflowRunId(runId)}
                  />
                ) : null}
              </>
            ) : null}
          </Stack>
        </div>
      )}

      <Drawer
        opened={selectedWorkflowRunId !== null}
        onClose={() => setSelectedWorkflowRunId(null)}
        title="Evaluation workflow run"
        position="right"
        size="90%"
        padding="md"
      >
        {selectedWorkflowRunId ? (
          <RunDetail
            runId={selectedWorkflowRunId}
            onStatusChanged={() => (selectedEvalId ? loadReport(selectedEvalId) : undefined)}
          />
        ) : null}
      </Drawer>
    </Stack>
  );
}

function CaseDetail({
  caseResult,
  onOpenRun,
}: {
  caseResult: EvaluationCaseResult;
  onOpenRun: (runId: string) => void;
}) {
  const diagnosticMetrics = caseResult.metrics.filter(
    (metric) => (metric.blocking && !metric.passed) || metricHasPartialScore(metric)
  );
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700}>{caseResult.name}</Text>
            <Text c="dimmed" size="sm">
              {caseResult.workflow_run_id ? `run_id: ${caseResult.workflow_run_id}` : caseResult.skip_reason ?? "workflow run 없음"}
            </Text>
          </div>
          <Group gap="xs">
            {caseResult.workflow_run_id ? (
              <Button size="xs" variant="light" onClick={() => onOpenRun(caseResult.workflow_run_id as string)}>
                Run detail
              </Button>
            ) : null}
            <Badge color={statusColor(caseResult.status)} variant="light">{caseResult.status}</Badge>
          </Group>
        </Group>

        {diagnosticMetrics.length > 0 ? (
          <Stack gap={4}>
            <Text fw={700} size="sm">평가 진단</Text>
            {diagnosticMetrics.map((metric) => {
              const isFailure = metric.blocking && !metric.passed;
              const showPenalty = shouldShowPenalty(metric);
              const showNextCheck = shouldShowNextCheck(metric);
              return (
              <Paper
                key={metric.name}
                withBorder
                p="sm"
                className={isFailure ? classes.metricFailure : classes.metricWarning}
              >
                <Stack gap={6}>
                  <Group justify="space-between" align="flex-start">
                    <Stack gap={4} className={classes.metricDiagnosticText}>
                      <Group gap="xs">
                        <Text size="sm" c={isFailure ? "red" : "yellow.9"} fw={700}>
                          {metricLabel(metric.name)} {isFailure ? "실패" : "감점"}
                        </Text>
                        <Badge size="xs" color={evaluatorColor(metric.evaluator_type)} variant="light">
                          {evaluatorLabel(metric.evaluator_type)}
                        </Badge>
                      </Group>
                      <Text size="xs" c="dimmed">
                        기준: {metricExpectedText(metric)}
                      </Text>
                    </Stack>
                    <Badge color={isFailure ? "red" : "yellow"} variant="light" className={classes.metricScoreBadge}>
                      {metricScoreLabel(metric)}
                    </Badge>
                  </Group>
                  <Text size="xs" c="dimmed">
                    결과: {metricActualText(metric)}
                  </Text>
                  {showPenalty ? (
                    <Text size="xs" c={isFailure ? "red" : "yellow.9"}>
                      감점 이유: {metricPenaltyText(metric)}
                    </Text>
                  ) : null}
                  {showNextCheck ? (
                    <Text size="xs" c="dimmed">
                      다음 확인: {metric.next_check}
                    </Text>
                  ) : null}
                  <MetricFailureValue metric={metric} compact />
                </Stack>
              </Paper>
              );
            })}
          </Stack>
        ) : (
          <Text size="sm" c="dimmed">차단 수준의 평가 실패나 1점 미만 진단 항목이 없습니다.</Text>
        )}

        {caseResult.source_family_coverage.length > 0 ? (
          <Stack gap={4}>
            <Text fw={700} size="sm">Source family coverage</Text>
            <Group gap="xs">
              {caseResult.source_family_coverage.map((item) => (
                <Badge key={item.source_family} variant="light" color={item.status === "covered" ? "green" : "gray"}>
                  {item.source_family}: {item.status}
                </Badge>
              ))}
            </Group>
          </Stack>
        ) : null}

        <Accordion variant="separated">
          <Accordion.Item value="metrics">
            <Accordion.Control>Metric detail</Accordion.Control>
            <Accordion.Panel>
              <Stack gap="xs">
                {caseResult.metrics.map((metric) => (
                  <MetricDetailRow key={metric.name} metric={metric} />
                ))}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
          <Accordion.Item value="raw">
            <Accordion.Control>Developer JSON</Accordion.Control>
            <Accordion.Panel>
              <Code block className={classes.jsonBlock}>
                {JSON.stringify(caseResult, null, 2)}
              </Code>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Stack>
    </Paper>
  );
}

function MetricFailureValue({ metric, compact = false }: { metric: EvaluationMetric; compact?: boolean }) {
  if (metric.evaluator_type === "llm") {
    const refs = Array.isArray(metric.evidence_quotes_or_refs) ? metric.evidence_quotes_or_refs : [];
    return (
      <Stack gap={3}>
        {metric.judge_reasoning_summary ? (
          <Text size="xs" c="dimmed">
            Judge 요약: {metric.judge_reasoning_summary}
          </Text>
        ) : null}
        {!compact && refs.length > 0 ? (
          <Stack gap={2}>
            <Text size="xs" c="dimmed" fw={600}>참고 근거</Text>
            {refs.slice(0, 3).map((item, index) => (
              <Text key={`${metric.name}-ref-${index}`} size="xs" c="dimmed">
                {index + 1}. {item}
              </Text>
            ))}
          </Stack>
        ) : null}
      </Stack>
    );
  }

  if (metric.name === "claim_limit_compliance") {
    const value = metric.value as {
      expected_claim_limits?: Array<{ limit?: string; terms?: string[]; reflected?: boolean }>;
      unsupported_public_claims?: Array<{ category?: string; terms?: string[] }>;
    };
    const limits = Array.isArray(value?.expected_claim_limits) ? value.expected_claim_limits : [];
    const unsupported = Array.isArray(value?.unsupported_public_claims) ? value.unsupported_public_claims : [];
    return (
      <Stack gap={4}>
        {limits.map((item) => (
          <Group key={item.limit} gap="xs" align="flex-start">
            <Badge size="xs" color={item.reflected ? "green" : "red"} variant="light">
              {item.reflected ? "반영됨" : "미반영"}
            </Badge>
            <div>
              <Text size="xs" fw={600}>{item.limit}</Text>
            </div>
          </Group>
        ))}
        {unsupported.length > 0 ? (
          <Stack gap={2}>
            <Text size="xs" c="red" fw={600}>공개 문구에서 근거 없는 단정 표현 후보가 감지됐습니다.</Text>
            {unsupported.map((item) => (
              <Text key={item.category} size="xs" c="dimmed">
                {item.category}: {(item.terms ?? []).join(", ")}
              </Text>
            ))}
          </Stack>
        ) : null}
      </Stack>
    );
  }

  if (metric.name === "expected_source_family_coverage" && Array.isArray(metric.value)) {
    return (
      <Group gap="xs">
        {metric.value.map((item) => {
          const row = item as { source_family?: string; status?: string; reason?: string };
          return (
            <Badge key={row.source_family} size="xs" color={row.status === "covered" ? "green" : "red"} variant="light">
              {row.source_family}: {row.status}
            </Badge>
          );
        })}
      </Group>
    );
  }

  if (metric.name === "retrieval_result_count") {
    if (metric.value === "not_applicable") {
      return <Text size="xs" c="dimmed">이 케이스에서는 검색 단계가 평가 대상이 아닙니다.</Text>;
    }
    const value = metric.value as {
      retrieved_documents?: number;
      expected_min_count_for_full_score?: number;
      vector_search_result_count?: number | null;
      post_geo_filter_result_count?: number | null;
    };
    return (
      <Stack gap={2}>
        <Text size="xs" c="dimmed">
          사용 가능한 근거 문서: {countLabel(value?.retrieved_documents)} (만점 기준 {countLabel(value?.expected_min_count_for_full_score ?? 3)})
        </Text>
        {!compact ? (
          <Text size="xs" c="dimmed">
            Vector 검색 결과: {countLabel(value?.vector_search_result_count)}, 지역 필터 후: {countLabel(value?.post_geo_filter_result_count)}
          </Text>
        ) : null}
      </Stack>
    );
  }

  if (metric.name === "source_document_indexed_count") {
    if (metric.value === "not_applicable") {
      return <Text size="xs" c="dimmed">이 케이스에서는 색인 단계가 평가 대상이 아닙니다.</Text>;
    }
    const value = metric.value as {
      indexed_or_upserted_documents?: number | null;
      expected_min_count_for_full_score?: number;
      indexed_document_count?: number | null;
      source_document_upsert_count?: number | null;
    };
    return (
      <Stack gap={2}>
        <Text size="xs" c="dimmed">
          색인/저장 문서: {countLabel(value?.indexed_or_upserted_documents)} (만점 기준 {countLabel(value?.expected_min_count_for_full_score ?? 3)})
        </Text>
        {!compact ? (
          <Text size="xs" c="dimmed">
            색인: {countLabel(value?.indexed_document_count)}, 저장: {countLabel(value?.source_document_upsert_count)}
          </Text>
        ) : null}
      </Stack>
    );
  }

  if (compact) return null;
  return (
    <Code block className={classes.metricValueBlock}>
      {JSON.stringify(metric.value, null, 2)}
    </Code>
  );
}

function MetricDetailRow({ metric }: { metric: EvaluationMetric }) {
  const showPenalty = shouldShowPenalty(metric);
  const showNextCheck = shouldShowNextCheck(metric);
  return (
    <Group justify="space-between" align="flex-start" wrap="nowrap" className={classes.metricDetailRow}>
      <div className={classes.metricDetailText}>
        <Group gap="xs" mb={4}>
          <Text fw={700} size="sm">{metricLabel(metric.name)}</Text>
          <Badge size="xs" color={evaluatorColor(metric.evaluator_type)} variant="light">
            {evaluatorLabel(metric.evaluator_type)}
          </Badge>
        </Group>
        {metric.not_applicable_reason ? (
          <Text c="dimmed" size="xs">평가 제외: {metric.not_applicable_reason}</Text>
        ) : null}
        <Text c="dimmed" size="xs">기준: {metricExpectedText(metric)}</Text>
        <Text c="dimmed" size="xs">결과: {metricActualText(metric)}</Text>
        {showPenalty ? (
          <Text c={metric.blocking && !metric.passed ? "red" : "yellow.9"} size="xs">
            감점 이유: {metricPenaltyText(metric)}
          </Text>
        ) : null}
        {showNextCheck ? (
          <Text c="dimmed" size="xs">다음 확인: {metric.next_check}</Text>
        ) : null}
        <MetricFailureValue metric={metric} compact />
      </div>
      <Badge className={classes.metricScoreBadge} color={metricScoreColor(metric)} variant="light">
        {metricScoreLabel(metric)}
      </Badge>
    </Group>
  );
}
