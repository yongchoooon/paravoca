import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  Code,
  Divider,
  Drawer,
  Group,
  Image,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconDownload,
  IconEdit,
  IconEye,
  IconGitBranch,
  IconRefresh,
  IconX,
} from "@tabler/icons-react";
import { StatusBadge } from "../components/StatusBadge";
import {
  AgentStep,
  Approval,
  approveWorkflowRun,
  createWorkflowRevision,
  deleteWorkflowRunQaIssues,
  EvidenceDocument,
  getWorkflowRun,
  getWorkflowRunResult,
  listRunApprovals,
  listRunLlmCalls,
  listRunSteps,
  listRunToolCalls,
  LLMCall,
  MarketingAsset,
  ProductIdea,
  QAIssue,
  QAReport,
  rejectWorkflowRun,
  requestWorkflowRunChanges,
  RevisionMode,
  ToolCall,
  WorkflowResult,
  WorkflowRun,
} from "../services/runsApi";
import { formatKstDateTime } from "../utils/datetime";
import { RunLogs } from "./RunLogs";
import classes from "./RunDetail.module.css";
import {
  ACTIVE_RUN_STATUSES,
  arrayOrEmpty,
  avoidOptions,
  cloneJson,
  errorMessage,
  formatIssueType,
  formatQaMessage,
  formatSeverity,
  formatSuggestedFix,
  joinLines,
  normalizeWorkflowResult,
  preferenceOptions,
  qaIssueKey,
  qaIssueKeys,
  qaIssueRevisionText,
  revisionModeLabel,
  revisionQaSettingsFromRun,
  RevisionQaSettings,
  severityColor,
  splitLines,
  workflowStages,
} from "./runDetailUtils";

type ApprovalAction = "approve" | "reject" | "request_changes";
type RunDetailTab = "review" | "evidence" | "logs" | "json";

type ApprovalModalState = {
  action: ApprovalAction;
  title: string;
  confirmLabel: string;
  color: string;
} | null;

type RunDetailProps = {
  runId: string;
  onStatusChanged: () => Promise<void> | void;
  onRevisionCreated?: (run: WorkflowRun) => Promise<void> | void;
  relatedRuns?: WorkflowRun[];
  onSelectRun?: (runId: string) => void;
};

const actionConfig: Record<ApprovalAction, Omit<NonNullable<ApprovalModalState>, "action">> = {
  approve: {
    title: "Approve run",
    confirmLabel: "Approve",
    color: "green",
  },
  reject: {
    title: "Reject run",
    confirmLabel: "Reject",
    color: "red",
  },
  request_changes: {
    title: "Request changes",
    confirmLabel: "Request changes",
    color: "yellow",
  },
};

export function RunDetail({
  runId,
  onStatusChanged,
  onRevisionCreated,
  relatedRuns = [],
  onSelectRun,
}: RunDetailProps) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [llmCalls, setLlmCalls] = useState<LLMCall[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceDocument | null>(null);
  const [showSelectedProductEvidenceOnly, setShowSelectedProductEvidenceOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approvalModal, setApprovalModal] = useState<ApprovalModalState>(null);
  const [approvalComment, setApprovalComment] = useState("");
  const [requestedChanges, setRequestedChanges] = useState("");
  const [highRiskOverride, setHighRiskOverride] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [revisionModalOpen, setRevisionModalOpen] = useState(false);
  const [revisionMode, setRevisionMode] = useState<RevisionMode>("manual_edit");
  const [revisionComment, setRevisionComment] = useState("");
  const [revisionRequestedChanges, setRevisionRequestedChanges] = useState("");
  const [revisionQaSettings, setRevisionQaSettings] = useState<RevisionQaSettings>(() =>
    revisionQaSettingsFromRun(null)
  );
  const [editableProducts, setEditableProducts] = useState<ProductIdea[]>([]);
  const [editableMarketingAssets, setEditableMarketingAssets] = useState<MarketingAsset[]>([]);
  const [editProductId, setEditProductId] = useState<string | null>(null);
  const [revisionSubmitting, setRevisionSubmitting] = useState(false);
  const [selectedQaIssueKeys, setSelectedQaIssueKeys] = useState<string[]>([]);
  const [qaIssueDeleting, setQaIssueDeleting] = useState(false);
  const [activeTab, setActiveTab] = useState<RunDetailTab>("review");

  async function loadRunDetail(options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setLoading(true);
      }
      setError(null);
      const nextRun = await getWorkflowRun(runId);
      const [resultResponse, stepsResponse, toolCallsResponse, llmCallsResponse, approvalsResponse] =
        await Promise.allSettled([
          getWorkflowRunResult(runId),
          listRunSteps(runId),
          listRunToolCalls(runId),
          listRunLlmCalls(runId),
          listRunApprovals(runId),
        ]);
      setRun(nextRun);
      const nextSteps = stepsResponse.status === "fulfilled" ? stepsResponse.value : [];
      const nextToolCalls = toolCallsResponse.status === "fulfilled" ? toolCallsResponse.value : [];
      const nextLlmCalls = llmCallsResponse.status === "fulfilled" ? llmCallsResponse.value : [];
      const nextApprovals = approvalsResponse.status === "fulfilled" ? approvalsResponse.value : [];
      setSteps(nextSteps);
      setToolCalls(nextToolCalls);
      setLlmCalls(nextLlmCalls);
      setApprovals(nextApprovals);
      if (resultResponse.status === "fulfilled") {
        const normalizedResult = normalizeWorkflowResult(resultResponse.value);
        setResult(normalizedResult);
        const nextIssueKeys = new Set(qaIssueKeys(normalizedResult.qa_report));
        setSelectedQaIssueKeys((current) => current.filter((key) => nextIssueKeys.has(key)));
        setSelectedProductId((current) =>
          current && normalizedResult.products.some((product) => product.id === current)
            ? current
            : normalizedResult.products[0]?.id ?? null
        );
      } else {
        setResult(null);
        setSelectedProductId(null);
        if (nextRun.status !== "failed") {
          throw resultResponse.reason;
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run detail");
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadRunDetail();
  }, [runId]);

  const isActiveRun = run ? ACTIVE_RUN_STATUSES.has(run.status) : false;

  useEffect(() => {
    if (!isActiveRun) return;
    const timer = window.setInterval(() => {
      void loadRunDetail({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isActiveRun, runId]);

  const selectedProduct = useMemo(() => {
    if (!result?.products.length) return null;
    return (
      result.products.find((product) => product.id === selectedProductId) ??
      result.products[0]
    );
  }, [result, selectedProductId]);

  const selectedMarketing = useMemo(() => {
    if (!result || !selectedProduct) return null;
    return result.marketing_assets.find((asset) => asset.product_id === selectedProduct.id) ?? null;
  }, [result, selectedProduct]);

  const selectedEvidenceRows = useMemo(() => {
    if (!result) return [];
    if (!showSelectedProductEvidenceOnly || !selectedProduct?.source_ids.length) {
      return result.retrieved_documents;
    }
    const sourceIds = new Set(selectedProduct.source_ids);
    return result.retrieved_documents.filter((doc) => sourceIds.has(doc.doc_id));
  }, [result, selectedProduct, showSelectedProductEvidenceOnly]);

  const canReview = run?.status === "awaiting_approval" || run?.status === "changes_requested";
  const canCreateRevision = Boolean(run?.final_output && (result?.products.length ?? 0) > 0 && !isActiveRun);

  const editableProduct = useMemo(() => {
    if (!editProductId) return editableProducts[0] ?? null;
    return editableProducts.find((product) => product.id === editProductId) ?? editableProducts[0] ?? null;
  }, [editableProducts, editProductId]);

  const editableMarketing = useMemo(() => {
    if (!editableProduct) return null;
    return (
      editableMarketingAssets.find((asset) => asset.product_id === editableProduct.id) ??
      editableMarketingAssets[0] ??
      null
    );
  }, [editableMarketingAssets, editableProduct]);

  const productTitleById = useMemo(() => {
    return new Map((result?.products ?? []).map((product) => [product.id, product.title]));
  }, [result]);

  const selectedQaIssues = useMemo(() => {
    if (!result) return [];
    const selected = new Set(selectedQaIssueKeys);
    return result.qa_report.issues.filter((issue, index) => selected.has(qaIssueKey(issue, index)));
  }, [result, selectedQaIssueKeys]);

  const selectedQaIssueIndices = useMemo(() => {
    if (!result) return [];
    const selected = new Set(selectedQaIssueKeys);
    return result.qa_report.issues
      .map((issue, index) => (selected.has(qaIssueKey(issue, index)) ? index : -1))
      .filter((index) => index >= 0);
  }, [result, selectedQaIssueKeys]);

  const parentRun = useMemo(
    () => relatedRuns.find((item) => item.id === run?.parent_run_id) ?? null,
    [relatedRuns, run]
  );

  const rootRun = run?.parent_run_id ? parentRun : run;

  const revisionRuns = useMemo(
    () =>
      relatedRuns
        .filter((item) => item.parent_run_id === rootRun?.id)
        .sort((a, b) => (a.revision_number ?? 0) - (b.revision_number ?? 0)),
    [relatedRuns, rootRun]
  );

  function openApprovalModal(action: ApprovalAction) {
    const config = actionConfig[action];
    setApprovalComment("");
    setRequestedChanges("");
    setHighRiskOverride(false);
    setApprovalModal({ action, ...config });
  }

  async function submitApprovalAction() {
    if (!approvalModal || !run) return;

    const payload = {
      reviewer: "operator",
      comment: approvalComment || null,
      high_risk_override: highRiskOverride,
      requested_changes:
        approvalModal.action === "request_changes"
          ? requestedChanges
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
          : [],
    };

    try {
      setSubmitting(true);
      if (approvalModal.action === "approve") {
        await approveWorkflowRun(run.id, payload);
      } else if (approvalModal.action === "reject") {
        await rejectWorkflowRun(run.id, payload);
      } else {
        await requestWorkflowRunChanges(run.id, payload);
      }
      notifications.show({
        title: "검토 결과 저장",
        message: "선택한 검토 결과가 저장되었습니다. Run 상태와 승인 이력에 반영됩니다.",
        color: approvalModal.color,
      });
      setApprovalModal(null);
      await loadRunDetail();
      await onStatusChanged();
    } catch (err) {
      notifications.show({
        title: "검토 결과 저장 실패",
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setSubmitting(false);
    }
  }

  function requestChangesFromHistory() {
    const changes: string[] = [];
    for (const approval of approvals) {
      if (approval.decision !== "request_changes") continue;
      const metadataChanges = approval.approval_metadata.requested_changes;
      if (Array.isArray(metadataChanges)) {
        changes.push(...metadataChanges.map(String).filter((item) => item.trim()));
      }
      if (approval.comment?.trim()) {
        changes.push(approval.comment.trim());
      }
    }
    return changes;
  }

  function openRevisionModal(mode: Exclude<RevisionMode, "manual_save">, requested?: string[]) {
    if (!result) return;
    const historyChanges = requestChangesFromHistory();
    setRevisionMode(mode);
    setRevisionComment(mode === "qa_only" ? "QA 재검수" : "");
    setRevisionRequestedChanges(
      (requested && requested.length > 0
        ? requested
        : mode === "qa_only"
          ? ["현재 결과를 유지하고 QA/Compliance 검수만 다시 실행"]
          : historyChanges
      ).join("\n")
    );
    setRevisionQaSettings(revisionQaSettingsFromRun(run));
    setEditableProducts(cloneJson(result.products));
    setEditableMarketingAssets(cloneJson(result.marketing_assets));
    setEditProductId(result.products[0]?.id ?? null);
    setRevisionModalOpen(true);
  }

  function openAiRevisionFromQaIssues() {
    if (!result || selectedQaIssues.length === 0) return;
    const requested = selectedQaIssues.map((issue) => {
      const index = result.qa_report.issues.indexOf(issue);
      return qaIssueRevisionText(issue, index >= 0 ? index : 0, productTitleById);
    });
    openRevisionModal("llm_partial_rewrite", requested);
  }

  function resetRevisionQaSettings() {
    setRevisionQaSettings(revisionQaSettingsFromRun(run));
  }

  function toggleQaIssue(issue: QAIssue, index: number) {
    const key = qaIssueKey(issue, index);
    setSelectedQaIssueKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
    );
  }

  function toggleAllQaIssues(checked: boolean) {
    setSelectedQaIssueKeys(checked && result ? qaIssueKeys(result.qa_report) : []);
  }

  async function deleteSelectedQaIssues() {
    if (!run || selectedQaIssueIndices.length === 0) return;
    try {
      setQaIssueDeleting(true);
      setActiveTab("evidence");
      const response = await deleteWorkflowRunQaIssues(run.id, {
        issue_indices: selectedQaIssueIndices,
      });
      notifications.show({
        title: "QA 리뷰 삭제",
        message: `선택한 QA 리뷰 ${response.removed_count}건을 삭제했습니다.`,
        color: "blue",
      });
      await loadRunDetail();
      setSelectedQaIssueKeys([]);
      setActiveTab("evidence");
      await onStatusChanged();
    } catch (err) {
      notifications.show({
        title: "QA 리뷰 삭제 실패",
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setQaIssueDeleting(false);
    }
  }

  function updateEditableProduct(productId: string, patch: Partial<ProductIdea>) {
    setEditableProducts((current) =>
      current.map((product) => (product.id === productId ? { ...product, ...patch } : product))
    );
  }

  function updateEditableMarketing(productId: string, patch: Partial<MarketingAsset>) {
    setEditableMarketingAssets((current) =>
      current.map((asset) => (asset.product_id === productId ? { ...asset, ...patch } : asset))
    );
  }

  function updateSalesCopy(
    productId: string,
    patch: Partial<MarketingAsset["sales_copy"]>
  ) {
    setEditableMarketingAssets((current) =>
      current.map((asset) =>
        asset.product_id === productId
          ? { ...asset, sales_copy: { ...asset.sales_copy, ...patch } }
          : asset
      )
    );
  }

  function updateSalesCopySection(
    productId: string,
    index: number,
    patch: Partial<{ title: string; body: string }>
  ) {
    const asset = editableMarketingAssets.find((item) => item.product_id === productId);
    if (!asset) return;
    const sections = asset.sales_copy.sections.map((section, sectionIndex) =>
      sectionIndex === index ? { ...section, ...patch } : section
    );
    updateSalesCopy(productId, { sections });
  }

  function updateFaq(
    productId: string,
    index: number,
    patch: Partial<{ question: string; answer: string }>
  ) {
    const asset = editableMarketingAssets.find((item) => item.product_id === productId);
    if (!asset) return;
    const faq = asset.faq.map((item, faqIndex) =>
      faqIndex === index ? { ...item, ...patch } : item
    );
    updateEditableMarketing(productId, { faq });
  }

  async function submitRevision(modeOverride?: RevisionMode) {
    if (!run || !result) return;
    const requested = splitLines(revisionRequestedChanges);
    const mode = modeOverride ?? revisionMode;
    const payload = {
      revision_mode: mode,
      comment: revisionComment.trim() || null,
      requested_changes: requested,
      qa_issues: mode === "llm_partial_rewrite" ? selectedQaIssues : [],
      qa_settings: revisionQaSettings,
      ...(mode === "manual_save" || mode === "manual_edit"
        ? {
            products: editableProducts,
            marketing_assets: editableMarketingAssets,
          }
        : {}),
    };

    try {
      setRevisionSubmitting(true);
      const revisionRun = await createWorkflowRevision(run.id, payload);
      notifications.show({
        title: "Revision run 시작",
        message: "새 Revision 실행을 시작했습니다. 진행 상태는 자동으로 갱신됩니다.",
        color: "blue",
      });
      setRevisionModalOpen(false);
      await onStatusChanged();
      if (onRevisionCreated) {
        await onRevisionCreated(revisionRun);
      }
    } catch (err) {
      notifications.show({
        title: "Revision 생성 실패",
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setRevisionSubmitting(false);
    }
  }

  function exportJson() {
    const revision = {
      ...(result?.revision ?? {}),
      parent_run_id: run?.parent_run_id ?? null,
      revision_number: run?.revision_number ?? 0,
      revision_mode: run?.revision_mode ?? null,
    };
    const payload = {
      run,
      result,
      revision,
      steps,
      tool_calls: toolCalls,
      llm_calls: llmCalls,
      approvals,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${runId}.json`;
    link.click();
    URL.revokeObjectURL(url);
    notifications.show({
      title: "JSON export 완료",
      message: "현재 run의 결과, 로그, 승인 이력을 JSON 파일로 내보냈습니다.",
      color: "blue",
    });
  }

  if (loading) {
    return (
      <Paper withBorder p="md">
        <Group gap="sm">
          <Loader size="sm" type="oval" />
          <Text c="dimmed">Run detail을 불러오는 중입니다.</Text>
        </Group>
      </Paper>
    );
  }

  if (error || !run) {
    return (
      <Alert color="red">
        {error ?? "Run detail을 확인할 수 없습니다."}
      </Alert>
    );
  }

  if (!result) {
    return (
      <Paper withBorder p="md">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <div>
              <Group gap="sm">
                <Title order={3}>Run Detail</Title>
                <StatusBadge status={run.status} />
              </Group>
              <Text ff="monospace" size="sm" c="dimmed">
                {run.id}
              </Text>
            </div>
          </Group>
          <Alert
            color={run.status === "failed" ? "red" : "blue"}
            title={run.status === "failed" ? "Workflow failed" : "Result is not ready"}
          >
            {run.error ? errorMessage(run.error) : "아직 생성된 result가 없습니다."}
          </Alert>
          <GeoClarificationFromSteps steps={steps} />
          <WorkflowProgress steps={steps} />
          <RunLogs
            run={run}
            steps={steps}
            toolCalls={toolCalls}
            llmCalls={llmCalls}
            agentExecution={[]}
          />
        </Stack>
      </Paper>
    );
  }

  return (
    <Paper withBorder p="md">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Group gap="sm">
              <Title order={3}>Run Detail</Title>
              <StatusBadge status={run.status} />
            </Group>
            <Text ff="monospace" size="sm" c="dimmed">
              {run.id}
            </Text>
            <RevisionMeta
              run={run}
              parentRun={parentRun}
              childRuns={revisionRuns}
              onSelectRun={onSelectRun}
            />
          </div>
          <Group gap="xs">
            <Tooltip label="Reload">
              <ActionIcon variant="light" aria-label="Reload run detail" onClick={() => void loadRunDetail()}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
            <Button
              variant="light"
              leftSection={<IconGitBranch size={16} />}
              disabled={!canCreateRevision || selectedQaIssues.length === 0}
              onClick={openAiRevisionFromQaIssues}
            >
              AI 수정
            </Button>
            <Button
              variant="light"
              disabled={!canCreateRevision}
              onClick={() => openRevisionModal("manual_edit")}
            >
              직접 수정
            </Button>
            <Button
              variant="subtle"
              disabled={!canCreateRevision}
              loading={revisionSubmitting && !revisionModalOpen}
              onClick={() => openRevisionModal("qa_only")}
            >
              QA 재검수
            </Button>
            <Button
              variant="light"
              leftSection={<IconDownload size={16} />}
              onClick={exportJson}
            >
              Export JSON
            </Button>
          </Group>
        </Group>

        {isActiveRun ? (
          <Alert color="blue">
            <Group gap="sm" align="flex-start">
              <Loader size="sm" type="oval" mt={2} />
              <div>
                <Text fw={700}>Workflow is running</Text>
                <WorkflowProgress steps={steps} />
              </div>
            </Group>
          </Alert>
        ) : null}

        {run.status === "failed" && !isGeoClarificationResult(result) ? (
          <Alert color="red" title="Workflow failed">
            {run.error ? errorMessage(run.error) : "Run Logs의 Errors 탭에서 실패한 step을 확인하세요."}
          </Alert>
        ) : null}

        {result.status === "unsupported" ? (
          <SupportScopeNotice result={result} />
        ) : null}

        {isGeoClarificationResult(result) ? (
          <GeoClarificationNotice result={result} />
        ) : null}

        <SimpleGrid cols={{ base: 1, sm: 4 }}>
          <Metric label="Products" value={String(result.products.length)} />
          <Metric label="Evidence" value={String(result.retrieved_documents.length)} />
          <Metric label="QA status" value={result.qa_report.overall_status} />
          <Metric label="LLM mode" value={String(result.cost_summary.mode ?? "-")} />
        </SimpleGrid>

        <GeoScopePanel scope={geoScopeFromResult(result)} />

        <Tabs
          value={activeTab}
          onChange={(value) => setActiveTab((value as RunDetailTab | null) ?? "review")}
        >
          <Tabs.List>
            <Tabs.Tab value="review">Result Review</Tabs.Tab>
            <Tabs.Tab value="evidence">Evidence + QA</Tabs.Tab>
            <Tabs.Tab value="logs">Run Logs</Tabs.Tab>
            <Tabs.Tab value="json">Raw JSON</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="review" pt="md">
            {result.products.length > 0 ? (
              <div className={classes.detailGrid}>
                <Paper withBorder p="sm" className={classes.productList}>
                  <Stack gap="xs">
                    <Text fw={700} size="sm">Products</Text>
                    {result.products.map((product) => (
                      <Button
                        key={product.id}
                        className={classes.productButton}
                        variant={product.id === selectedProduct?.id ? "light" : "subtle"}
                        color="opsBlue"
                        onClick={() => setSelectedProductId(product.id)}
                      >
                        <span className={classes.productButtonLabel}>{product.title}</span>
                      </Button>
                    ))}
                  </Stack>
                </Paper>

                <Paper withBorder p="md" className={classes.panel}>
                  {selectedProduct ? (
                    <ProductDetail product={selectedProduct} marketing={selectedMarketing} />
                  ) : (
                    <Text c="dimmed">생성된 상품이 없습니다.</Text>
                  )}
                </Paper>
              </div>
            ) : result.status === "unsupported" ? (
              <SupportScopeNotice result={result} />
            ) : isGeoClarificationResult(result) ? (
              <GeoClarificationReviewNotice />
            ) : (
              <Alert color="gray">
                <Group gap="sm" align="flex-start">
                  {isActiveRun ? <Loader size="sm" type="oval" mt={2} /> : null}
                  <div>
                    <Text fw={700}>No generated product result</Text>
                    <Text size="sm">
                      {isActiveRun
                        ? "Workflow output을 아직 생성하고 있습니다."
                        : "이 run은 실패했을 수 있습니다. 상태와 에러는 Run Logs 또는 Raw JSON에서 확인하세요."}
                    </Text>
                  </div>
                </Group>
              </Alert>
            )}
          </Tabs.Panel>

          <Tabs.Panel value="evidence" pt="md">
            <Stack gap="md">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text fw={700} size="sm">Evidence documents</Text>
                  <Text size="sm" c="dimmed">
                    Showing {selectedEvidenceRows.length} of {result.retrieved_documents.length}
                    {showSelectedProductEvidenceOnly && selectedProduct
                      ? ` linked to ${selectedProduct.title}`
                      : " retrieved documents"}
                  </Text>
                </div>
                <Checkbox
                  checked={showSelectedProductEvidenceOnly}
                  disabled={!selectedProduct?.source_ids.length}
                  label="Selected product only"
                  onChange={(event) => setShowSelectedProductEvidenceOnly(event.currentTarget.checked)}
                />
              </Group>
              <EvidenceTable
                rows={selectedEvidenceRows}
                onOpenEvidence={setSelectedEvidence}
              />
              <QASection
                report={result.qa_report}
                products={result.products}
                selectedIssueKeys={selectedQaIssueKeys}
                onToggleIssue={toggleQaIssue}
                onToggleAll={toggleAllQaIssues}
                onDeleteSelected={deleteSelectedQaIssues}
                deleteLoading={qaIssueDeleting}
              />
              <ApprovalHistory
                approvals={approvals}
                sourceApprovals={arrayOrEmpty<Approval>(result.revision.approval_history)}
              />
              <Group justify="flex-end">
                <Button
                  color="green"
                  leftSection={<IconCheck size={16} />}
                  disabled={!canReview}
                  onClick={() => openApprovalModal("approve")}
                >
                  Approve
                </Button>
                <Button
                  color="yellow"
                  variant="light"
                  leftSection={<IconEdit size={16} />}
                  disabled={!canReview}
                  onClick={() => openApprovalModal("request_changes")}
                >
                  Request changes
                </Button>
                <Button
                  color="red"
                  variant="light"
                  leftSection={<IconX size={16} />}
                  disabled={!canReview}
                  onClick={() => openApprovalModal("reject")}
                >
                  Reject
                </Button>
              </Group>
            </Stack>
          </Tabs.Panel>

          <Tabs.Panel value="logs" pt="md">
            <RunLogs
              run={run}
              steps={steps}
              toolCalls={toolCalls}
              llmCalls={llmCalls}
              agentExecution={result.agent_execution}
            />
          </Tabs.Panel>

          <Tabs.Panel value="json" pt="md">
            <Code block className={classes.jsonBlock}>
              {JSON.stringify(
                {
                  run,
                  result,
                  revision: {
                    ...(result?.revision ?? {}),
                    parent_run_id: run.parent_run_id,
                    revision_number: run.revision_number,
                    revision_mode: run.revision_mode,
                  },
                  steps,
                  toolCalls,
                  llmCalls,
                  approvals,
                },
                null,
                2
              )}
            </Code>
          </Tabs.Panel>
        </Tabs>
      </Stack>

      <Drawer
        opened={Boolean(selectedEvidence)}
        onClose={() => setSelectedEvidence(null)}
        position="right"
        size="lg"
        title={selectedEvidence?.title ?? "Evidence"}
      >
        {selectedEvidence ? (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge variant="light">{evidenceTypeLabel(selectedEvidence)}</Badge>
              <EvidenceDetailBadge row={selectedEvidence} />
            </Group>
            <Text size="sm" c="dimmed">
              {selectedEvidence.doc_id}
            </Text>
            <EvidenceImageCandidates row={selectedEvidence} />
            <EvidenceMetadataSummary row={selectedEvidence} />
            <Text size="sm">{selectedEvidence.content}</Text>
            <Divider />
            <Code block>
              {JSON.stringify(selectedEvidence.metadata, null, 2)}
            </Code>
          </Stack>
        ) : null}
      </Drawer>

      <Modal
        opened={approvalModal !== null}
        onClose={() => setApprovalModal(null)}
        title={approvalModal?.title}
        size="lg"
      >
        <Stack gap="sm">
          <Textarea
            label="Comment"
            placeholder="검토 결정의 이유나 운영자가 참고해야 할 내용을 적습니다."
            minRows={3}
            value={approvalComment}
            onChange={(event) => setApprovalComment(event.currentTarget.value)}
          />
          {approvalModal?.action === "request_changes" ? (
            <Textarea
              label="Requested changes"
              placeholder={"수정해야 할 내용을 한 줄에 하나씩 적습니다.\n예: 외국어 안내 가능 여부를 단정하지 않게 수정\n예: 집결지 확인 필요 문구 추가"}
              minRows={4}
              value={requestedChanges}
              onChange={(event) => setRequestedChanges(event.currentTarget.value)}
            />
          ) : null}
          <Checkbox
            label="High risk override"
            checked={highRiskOverride}
            onChange={(event) => setHighRiskOverride(event.currentTarget.checked)}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setApprovalModal(null)}>
              Cancel
            </Button>
            <Button
              color={approvalModal?.color}
              loading={submitting}
              onClick={() => void submitApprovalAction()}
            >
              {approvalModal?.confirmLabel}
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={revisionModalOpen}
        onClose={() => setRevisionModalOpen(false)}
        title={revisionModeLabel[revisionMode] ?? "Revision"}
        size="90%"
      >
        <Stack gap="md">
          <Alert color={revisionMode === "manual_edit" ? "gray" : "blue"}>
            {revisionMode === "manual_edit"
              ? "수정한 내용을 새 Revision으로 기록합니다. QA 재검수를 선택하면 아래 검수 설정으로 다시 확인합니다."
              : revisionMode === "qa_only"
                ? "상품 내용은 바꾸지 않고 아래 검수 설정으로 QA만 다시 실행합니다."
                : "선택한 QA 이슈와 추가 요청을 바탕으로 필요한 필드만 AI가 수정합니다. 선택되지 않은 내용은 그대로 유지합니다."}
          </Alert>

          <Textarea
            label="Comment"
            placeholder={
              revisionMode === "manual_edit"
                ? "직접 수정한 이유나 확인해야 할 내용을 적습니다. 예: 제목의 불필요한 숫자를 제거함"
                : revisionMode === "qa_only"
                  ? "이번 재검수에서 확인할 배경을 적습니다. 예: 고객 노출 문구만 다시 확인"
                  : "AI 수정 요청의 배경을 적습니다. 예: QA에서 지적된 과장 표현을 먼저 정리"
            }
            minRows={4}
            value={revisionComment}
            onChange={(event) => setRevisionComment(event.currentTarget.value)}
          />

          <RevisionQaSettingsPanel
            settings={revisionQaSettings}
            onChange={(patch) =>
              setRevisionQaSettings((current) => ({ ...current, ...patch }))
            }
            onReset={resetRevisionQaSettings}
          />

          <Textarea
            label="Requested changes"
            placeholder={
              revisionMode === "manual_edit"
                ? "직접 수정 후에도 QA가 다시 확인해야 할 내용을 적습니다. 예: 제목 수정 후 과장 표현 재검수"
                : revisionMode === "qa_only"
                  ? "QA가 다시 확인해야 할 기준을 한 줄에 하나씩 적습니다. 예: 가격/일정 확정 표현만 확인"
                  : "AI가 반영해야 할 수정 지시를 한 줄에 하나씩 적습니다. 예: 선택된 QA 이슈의 suggested fix를 반영하되 운영 시간은 단정하지 않기"
            }
            minRows={6}
            value={revisionRequestedChanges}
            onChange={(event) => setRevisionRequestedChanges(event.currentTarget.value)}
          />

          {revisionMode === "llm_partial_rewrite" ? (
            <SelectedQaIssuesPreview issues={selectedQaIssues} productTitleById={productTitleById} />
          ) : revisionMode === "qa_only" ? null : (
            <Stack gap="sm">
              <div className={classes.revisionEditGrid}>
                <Paper withBorder p="sm" className={classes.productList}>
                  <Stack gap="xs">
                    <Text fw={700} size="sm">Products</Text>
                    {editableProducts.map((product) => (
                      <Button
                        key={product.id}
                        className={classes.productButton}
                        variant={product.id === editableProduct?.id ? "light" : "subtle"}
                        color="opsBlue"
                        onClick={() => setEditProductId(product.id)}
                      >
                        <span className={classes.productButtonLabel}>{product.title}</span>
                      </Button>
                    ))}
                  </Stack>
                </Paper>
                <Paper withBorder p="md" className={classes.panel}>
                  {editableProduct && editableMarketing ? (
                    <RevisionEditor
                      product={editableProduct}
                      marketing={editableMarketing}
                      onProductChange={(patch) => updateEditableProduct(editableProduct.id, patch)}
                      onMarketingChange={(patch) =>
                        updateEditableMarketing(editableProduct.id, patch)
                      }
                      onSalesCopyChange={(patch) => updateSalesCopy(editableProduct.id, patch)}
                      onSalesCopySectionChange={(index, patch) =>
                        updateSalesCopySection(editableProduct.id, index, patch)
                      }
                      onFaqChange={(index, patch) => updateFaq(editableProduct.id, index, patch)}
                    />
                  ) : (
                    <Text c="dimmed">수정 가능한 상품 결과가 없습니다.</Text>
                  )}
                </Paper>
              </div>
            </Stack>
          )}

          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              원본 결과는 그대로 두고 새 Revision으로 기록합니다.
            </Text>
            <Group>
              <Button variant="subtle" onClick={() => setRevisionModalOpen(false)}>
                Cancel
              </Button>
              {revisionMode === "manual_edit" ? (
                <Button
                  variant="light"
                  loading={revisionSubmitting}
                  onClick={() => void submitRevision("manual_save")}
                >
                  저장
                </Button>
              ) : null}
              <Button loading={revisionSubmitting} onClick={() => void submitRevision()}>
                {revisionMode === "manual_edit"
                  ? "저장 후 QA 재검수"
                  : revisionMode === "qa_only"
                    ? "QA 재검수 실행"
                    : "AI 수정 실행"}
              </Button>
            </Group>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}

function SupportScopeNotice({ result }: { result: WorkflowResult }) {
  const userMessage = recordOrNull(result.user_message);
  const title = String(userMessage?.title ?? "지원 범위 안내");
  const message = String(userMessage?.message ?? "PARAVOCA는 현재 국내 관광 데이터만 지원합니다.");
  const detail = String(userMessage?.detail ?? "국내 지역을 포함해 다시 요청하면 상품 기획을 진행할 수 있습니다.");
  return (
    <Alert color="blue" title={title}>
      <Stack gap={4}>
        <Text size="sm">{message}</Text>
        <Text size="sm" c="dimmed">{detail}</Text>
      </Stack>
    </Alert>
  );
}

function GeoClarificationNotice({ result }: { result: WorkflowResult }) {
  return (
    <Alert color="yellow" title="지역을 하나로 좁혀 주세요">
      <Stack gap={4}>
        <Text size="sm">
          요청 문장만으로는 어느 지역인지 확정하기 어려워 데이터 수집을 시작하지 않았습니다.
        </Text>
        <Text size="sm" c="dimmed">
          예: `서울 중구 야간 관광 상품`처럼 시도와 시군구를 함께 넣어 다시 요청해 주세요.
        </Text>
      </Stack>
    </Alert>
  );
}

function GeoClarificationReviewNotice() {
  return (
    <Alert color="gray" title="아직 상품을 만들지 않았습니다">
      <Stack gap={4}>
        <Text size="sm">
          요청한 지역을 하나로 정하지 못해 관광 데이터 검색 전에 멈췄습니다.
        </Text>
        <Text size="sm" c="dimmed">
          위의 지역 후보를 보고 원하는 지역명을 더 구체적으로 넣어 새 run을 만들어 주세요.
        </Text>
      </Stack>
    </Alert>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <Paper withBorder p="sm">
      <Text c="dimmed" size="xs">{label}</Text>
      <Text fw={700}>{value}</Text>
    </Paper>
  );
}

function RevisionMeta({
  run,
  parentRun,
  childRuns,
  onSelectRun,
}: {
  run: WorkflowRun;
  parentRun: WorkflowRun | null;
  childRuns: WorkflowRun[];
  onSelectRun?: (runId: string) => void;
}) {
  return (
    <Stack gap={4} mt={6}>
      <Group gap="xs">
        <Badge variant={run.revision_number > 0 ? "light" : "outline"} color="opsBlue">
          {run.revision_number > 0 ? `Revision #${run.revision_number}` : "Original run"}
        </Badge>
        {run.revision_mode ? (
          <Badge variant="light" color="gray">
            {revisionModeLabel[run.revision_mode] ?? run.revision_mode}
          </Badge>
        ) : null}
      </Group>
      {parentRun ? (
        <Group gap="xs">
          <Text size="xs" c="dimmed">Parent</Text>
          <Button size="compact-xs" variant="subtle" onClick={() => onSelectRun?.(parentRun.id)}>
            {parentRun.id}
          </Button>
        </Group>
      ) : null}
      {childRuns.length > 0 ? (
        <Group gap="xs">
          <Text size="xs" c="dimmed">Revisions</Text>
          {childRuns.map((child) => (
            <Button
              key={child.id}
              size="compact-xs"
              variant="subtle"
              onClick={() => onSelectRun?.(child.id)}
            >
              Rev {child.revision_number}
            </Button>
          ))}
        </Group>
      ) : null}
    </Stack>
  );
}

function WorkflowProgress({ steps }: { steps: AgentStep[] }) {
  const visibleStages = workflowStages
    .map((stage) => {
      const step = steps.find(
        (item) => item.agent_name === stage.agentName && item.step_type === stage.stepType
      );
      return { stage, step };
    })
    .filter((item) => item.step);

  return (
    <Stack gap={4} mt={6}>
      {visibleStages.map(({ stage, step }) => {
        const status = step?.status ?? "pending";
        const isRunning = status === "running";
        const isDone = status === "succeeded";
        const isFailed = status === "failed";

        return (
          <Group key={stage.key} gap="xs" align="center" wrap="nowrap">
            <StageIndicator status={status} />
            <Text size="sm" c={isRunning ? undefined : "dimmed"} fw={isRunning ? 650 : 400}>
              {stage.label}
            </Text>
            {isRunning ? (
              <Badge size="xs" color="blue" variant="light">진행 중</Badge>
            ) : null}
            {isDone ? (
              <Badge size="xs" color="green" variant="light">완료</Badge>
            ) : null}
            {isFailed ? (
              <Badge size="xs" color="red" variant="light">실패</Badge>
            ) : null}
            <Text size="sm" c="dimmed" lineClamp={1}>
              {stage.description}
            </Text>
          </Group>
        );
      })}
    </Stack>
  );
}

function GeoClarificationFromSteps({ steps }: { steps: AgentStep[] }) {
  const geoStep = steps.find(
    (step) => step.agent_name === "GeoResolverAgent" && step.step_type === "geo_resolution"
  );
  const output = recordOrNull(geoStep?.output);
  const scope = recordOrNull(output?.geo_scope);
  return scope ? <GeoScopePanel scope={scope} /> : null;
}

function GeoScopePanel({ scope }: { scope: Record<string, unknown> | null }) {
  if (!scope) return null;
  const locations = arrayOfRecords(scope.locations);
  const candidates = arrayOfRecords(scope.candidates);
  const unresolved = arrayOfRecords(scope.unresolved_locations);
  const displayCandidates = geoCandidateNames(candidates, unresolved);
  const needsClarification = scope.needs_clarification === true;
  const isUnsupported = scope.status === "unsupported" || scope.mode === "unsupported_region";
  const unsupportedLocations = Array.isArray(scope.unsupported_locations)
    ? scope.unsupported_locations.map(String).filter(Boolean)
    : [];
  const statusLabel = isUnsupported
    ? "지원 범위 안내"
    : needsClarification
      ? "확인 필요"
      : scope.allow_nationwide === true
        ? "전국"
        : scope.mode === "route"
          ? "동선"
          : "지역 확정";
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700} size="sm">해석된 지역 범위</Text>
            <Text size="sm" c="dimmed">
              {geoScopeLabel(scope)}
            </Text>
          </div>
          <Badge variant="light" color={needsClarification ? "yellow" : isUnsupported ? "gray" : "opsBlue"}>
            {statusLabel}
          </Badge>
        </Group>
        {isUnsupported ? (
          <Alert color="blue" title="지원 범위 안내">
            <Text size="sm">
              {String(scope.unsupported_reason ?? "PARAVOCA는 현재 국내 관광 데이터만 지원합니다.")}
              {unsupportedLocations.length > 0 ? ` 감지된 지역: ${unsupportedLocations.join(", ")}` : ""}
            </Text>
          </Alert>
        ) : null}
        {needsClarification ? (
          <Alert color="yellow" title="지역을 하나로 좁혀 주세요">
            <Stack gap="xs">
              <Text size="sm">
                요청 문장만으로는 어느 지역인지 확정하기 어렵습니다. 아래 후보 중 원하는 지역명을 포함해 다시 요청해 주세요.
              </Text>
            </Stack>
          </Alert>
        ) : null}
        {needsClarification && displayCandidates.length > 0 ? (
          <Group gap="xs">
            {displayCandidates.slice(0, 8).map((name) => (
              <Text key={name} span size="sm" c="blue.7" fw={650}>
                {name}
              </Text>
            ))}
          </Group>
        ) : null}
        {!needsClarification && locations.length > 0 ? (
          <Group gap="xs">
            {locations.map((location) => (
              <Badge
                key={`${location.role}-${location.ldong_regn_cd}-${location.ldong_signgu_cd}-${location.name}`}
                variant="light"
                color="opsBlue"
              >
                {geoRoleLabel(location.role)}{String(location.name ?? "-")}
              </Badge>
            ))}
          </Group>
        ) : scope.allow_nationwide === true ? (
          <Badge variant="light" color="opsBlue">전국 검색 허용</Badge>
        ) : null}
      </Stack>
    </Paper>
  );
}

function geoScopeFromResult(result: WorkflowResult): Record<string, unknown> | null {
  return recordOrNull(result.geo_scope) ?? recordOrNull(result.normalized_request.geo_scope);
}

function isGeoClarificationResult(result: WorkflowResult) {
  const scope = geoScopeFromResult(result);
  return result.status === "needs_clarification" || scope?.needs_clarification === true;
}

function geoScopeLabel(scope: Record<string, unknown>) {
  if (scope.status === "unsupported" || scope.mode === "unsupported_region") return "지원 범위 밖";
  if (scope.allow_nationwide === true) return "전국";
  if (scope.needs_clarification === true) return "지역을 더 구체적으로 입력해 주세요";
  const locations = arrayOfRecords(scope.locations);
  const names = locations.map((location) => String(location.name ?? "").trim()).filter(Boolean);
  const separator = scope.mode === "route" ? " → " : ", ";
  return names.length > 0 ? names.join(separator) : "-";
}

function geoCandidateNames(
  candidates: Array<Record<string, unknown>>,
  unresolved: Array<Record<string, unknown>>,
) {
  const names = new Map<string, string>();
  const collect = (items: Array<Record<string, unknown>>) => {
    items.forEach((item) => {
      const name = String(item.name ?? "").replace(/\s+/g, " ").trim();
      if (name && !names.has(name)) {
        names.set(name, name);
      }
    });
  };
  collect(candidates);
  unresolved.forEach((item) => collect(arrayOfRecords(item.candidates)));
  return Array.from(names.values());
}

function geoRoleLabel(value: unknown) {
  const role = String(value ?? "primary");
  return {
    origin: "출발: ",
    destination: "도착: ",
    stopover: "경유: ",
    primary: "",
    comparison: "비교: ",
    nearby_anchor: "주변: ",
  }[role] ?? "";
}

function evidenceTypeLabel(row: EvidenceDocument) {
  const rawType = String(row.metadata.content_type ?? "").trim().toLowerCase();
  return {
    attraction: "관광지",
    culture: "문화시설",
    event: "행사/축제",
    course: "여행코스",
    leisure: "레포츠",
    accommodation: "숙박",
    shopping: "쇼핑",
    restaurant: "음식점",
  }[rawType] ?? (rawType ? rawType : "-");
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function arrayOfRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item && typeof item === "object" && !Array.isArray(item))
      )
    : [];
}

function StageIndicator({ status }: { status: string }) {
  if (status === "running") {
    return <Loader size={14} type="oval" />;
  }
  if (status === "succeeded") {
    return <IconCheck size={15} color="var(--mantine-color-green-6)" />;
  }
  if (status === "failed") {
    return <IconX size={15} color="var(--mantine-color-red-6)" />;
  }
  return (
    <span
      aria-hidden="true"
      style={{
        width: 8,
        height: 8,
        borderRadius: 999,
        background: "var(--mantine-color-gray-4)",
        flex: "0 0 auto",
      }}
    />
  );
}

function ProductDetail({
  product,
  marketing,
}: {
  product: ProductIdea;
  marketing: MarketingAsset | null;
}) {
  return (
    <Stack gap="md">
      <div>
        <Title order={4}>{product.title}</Title>
        <Text size="sm" c="dimmed">{product.one_liner}</Text>
      </div>
      <Group gap="xs">
        {product.core_value.map((value) => (
          <Badge key={value} variant="light">{value}</Badge>
        ))}
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Metric label="Target" value={product.target_customer} />
        <Metric label="Duration" value={product.estimated_duration} />
        <Metric label="Difficulty" value={product.operation_difficulty} />
      </SimpleGrid>

      <Tabs defaultValue="copy">
        <Tabs.List>
          <Tabs.Tab value="copy">Sales Copy</Tabs.Tab>
          <Tabs.Tab value="faq">FAQ</Tabs.Tab>
          <Tabs.Tab value="sns">SNS</Tabs.Tab>
          <Tabs.Tab value="rules">Claims</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="copy" pt="sm">
          {marketing ? (
            <Stack gap="sm">
              <Text fw={700}>{marketing.sales_copy.headline}</Text>
              <Text size="sm">{marketing.sales_copy.subheadline}</Text>
              {marketing.sales_copy.sections.map((section) => (
                <Paper key={section.title} withBorder p="sm">
                  <Text fw={700} size="sm">{section.title}</Text>
                  <Text size="sm">{section.body}</Text>
                </Paper>
              ))}
              <Alert color="gray">{marketing.sales_copy.disclaimer}</Alert>
            </Stack>
          ) : (
            <Text c="dimmed">생성된 마케팅 자산이 없습니다.</Text>
          )}
        </Tabs.Panel>

        <Tabs.Panel value="faq" pt="sm">
          <Table verticalSpacing="sm">
            <Table.Tbody>
              {(marketing?.faq ?? []).map((item) => (
                <Table.Tr key={item.question}>
                  <Table.Td w="35%"><Text fw={600} size="sm">{item.question}</Text></Table.Td>
                  <Table.Td><Text size="sm">{item.answer}</Text></Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="sns" pt="sm">
          <Stack gap="sm">
            {(marketing?.sns_posts ?? []).map((post) => (
              <Paper key={post} withBorder p="sm">
                <Text size="sm">{post}</Text>
              </Paper>
            ))}
            <Group gap="xs">
              {(marketing?.search_keywords ?? []).map((keyword) => (
                <Badge key={keyword} variant="outline">{keyword}</Badge>
              ))}
            </Group>
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="rules" pt="sm">
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Paper withBorder p="sm">
              <Text fw={700} size="sm">Assumptions</Text>
              {product.assumptions.map((item) => (
                <Text key={item} size="sm">- {item}</Text>
              ))}
            </Paper>
            <Paper withBorder p="sm">
              <Text fw={700} size="sm">Do not claim</Text>
              {product.not_to_claim.map((item) => (
                <Text key={item} size="sm">- {item}</Text>
              ))}
            </Paper>
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}

function RevisionEditor({
  product,
  marketing,
  onProductChange,
  onMarketingChange,
  onSalesCopyChange,
  onSalesCopySectionChange,
  onFaqChange,
}: {
  product: ProductIdea;
  marketing: MarketingAsset;
  onProductChange: (patch: Partial<ProductIdea>) => void;
  onMarketingChange: (patch: Partial<MarketingAsset>) => void;
  onSalesCopyChange: (patch: Partial<MarketingAsset["sales_copy"]>) => void;
  onSalesCopySectionChange: (
    index: number,
    patch: Partial<{ title: string; body: string }>
  ) => void;
  onFaqChange: (index: number, patch: Partial<{ question: string; answer: string }>) => void;
}) {
  return (
    <Tabs defaultValue="product">
      <Tabs.List>
        <Tabs.Tab value="product">Product</Tabs.Tab>
        <Tabs.Tab value="copy">Sales Copy</Tabs.Tab>
        <Tabs.Tab value="faq">FAQ</Tabs.Tab>
        <Tabs.Tab value="sns">SNS / Keywords</Tabs.Tab>
        <Tabs.Tab value="claims">Claims</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="product" pt="md">
        <Stack gap="sm">
          <TextInput
            label="Title"
            value={product.title}
            onChange={(event) => onProductChange({ title: event.currentTarget.value })}
          />
          <Textarea
            label="One-liner"
            minRows={4}
            value={product.one_liner}
            onChange={(event) => onProductChange({ one_liner: event.currentTarget.value })}
          />
          <Group grow>
            <TextInput
              label="Duration"
              value={product.estimated_duration}
              onChange={(event) =>
                onProductChange({ estimated_duration: event.currentTarget.value })
              }
            />
            <TextInput
              label="Difficulty"
              value={product.operation_difficulty}
              onChange={(event) =>
                onProductChange({ operation_difficulty: event.currentTarget.value })
              }
            />
          </Group>
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="copy" pt="md">
        <Stack gap="sm">
          <TextInput
            label="Headline"
            value={marketing.sales_copy.headline}
            onChange={(event) => onSalesCopyChange({ headline: event.currentTarget.value })}
          />
          <Textarea
            label="Subheadline"
            minRows={4}
            value={marketing.sales_copy.subheadline}
            onChange={(event) => onSalesCopyChange({ subheadline: event.currentTarget.value })}
          />
          {marketing.sales_copy.sections.map((section, index) => (
            <Paper key={`${product.id}-section-${index}`} withBorder p="sm">
              <Stack gap="xs">
                <TextInput
                  label={`Section ${index + 1} title`}
                  value={section.title}
                  onChange={(event) =>
                    onSalesCopySectionChange(index, { title: event.currentTarget.value })
                  }
                />
                <Textarea
                  label={`Section ${index + 1} body`}
                  minRows={6}
                  value={section.body}
                  onChange={(event) =>
                    onSalesCopySectionChange(index, { body: event.currentTarget.value })
                  }
                />
              </Stack>
            </Paper>
          ))}
          <Textarea
            label="Disclaimer"
            minRows={4}
            value={marketing.sales_copy.disclaimer}
            onChange={(event) => onSalesCopyChange({ disclaimer: event.currentTarget.value })}
          />
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="faq" pt="md">
        <Stack gap="sm">
          {marketing.faq.map((item, index) => (
            <Paper key={`${product.id}-faq-${index}`} withBorder p="sm">
              <Stack gap="xs">
                <TextInput
                  label={`Question ${index + 1}`}
                  value={item.question}
                  onChange={(event) => onFaqChange(index, { question: event.currentTarget.value })}
                />
                <Textarea
                  label={`Answer ${index + 1}`}
                  minRows={5}
                  value={item.answer}
                  onChange={(event) => onFaqChange(index, { answer: event.currentTarget.value })}
                />
              </Stack>
            </Paper>
          ))}
        </Stack>
      </Tabs.Panel>

      <Tabs.Panel value="sns" pt="md">
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Textarea
            label="SNS posts"
            minRows={12}
            value={joinLines(marketing.sns_posts)}
            onChange={(event) =>
              onMarketingChange({ sns_posts: splitLines(event.currentTarget.value) })
            }
          />
          <Textarea
            label="Search keywords"
            minRows={12}
            value={joinLines(marketing.search_keywords)}
            onChange={(event) =>
              onMarketingChange({ search_keywords: splitLines(event.currentTarget.value) })
            }
          />
        </SimpleGrid>
      </Tabs.Panel>

      <Tabs.Panel value="claims" pt="md">
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Textarea
            label="Assumptions"
            minRows={12}
            value={joinLines(product.assumptions)}
            onChange={(event) => onProductChange({ assumptions: splitLines(event.currentTarget.value) })}
          />
          <Textarea
            label="Do not claim"
            minRows={12}
            value={joinLines(product.not_to_claim)}
            onChange={(event) => onProductChange({ not_to_claim: splitLines(event.currentTarget.value) })}
          />
        </SimpleGrid>
      </Tabs.Panel>
    </Tabs>
  );
}

function RevisionQaSettingsPanel({
  settings,
  onChange,
  onReset,
}: {
  settings: RevisionQaSettings;
  onChange: (patch: Partial<RevisionQaSettings>) => void;
  onReset: () => void;
}) {
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700}>Run settings</Text>
            <Text size="sm" c="dimmed">
              처음 run 생성 시 사용한 설정입니다. 그대로 실행하거나 필요한 값만 수정할 수 있습니다.
            </Text>
          </div>
          <Button size="xs" variant="subtle" onClick={onReset}>
            초기 설정으로 되돌리기
          </Button>
        </Group>
        <SimpleGrid cols={{ base: 1, md: 3 }}>
          <TextInput
            label="Period"
            type="month"
            value={settings.period}
            onChange={(event) => onChange({ period: event.currentTarget.value })}
          />
          <TextInput
            label="Target"
            value={settings.target_customer}
            onChange={(event) => onChange({ target_customer: event.currentTarget.value })}
          />
          <NumberInput
            label="Product count"
            min={1}
            max={10}
            value={settings.product_count}
            onChange={(value) => onChange({ product_count: Number(value) || 1 })}
          />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <MultiSelect
            label="Preferences"
            data={[...new Set([...preferenceOptions, ...settings.preferences])]}
            value={settings.preferences}
            searchable
            onChange={(value) => onChange({ preferences: value })}
          />
          <MultiSelect
            label="Avoid"
            data={[...new Set([...avoidOptions, ...settings.avoid])]}
            value={settings.avoid}
            searchable
            onChange={(value) => onChange({ avoid: value })}
          />
        </SimpleGrid>
      </Stack>
    </Paper>
  );
}

function SelectedQaIssuesPreview({
  issues,
  productTitleById,
}: {
  issues: QAIssue[];
  productTitleById: Map<string, string>;
}) {
  if (issues.length === 0) {
    return (
      <Alert color="yellow">
        AI가 반영할 QA 이슈가 선택되지 않았습니다. QA Review에서 수정할 이슈를 체크한 뒤 다시 실행하세요.
      </Alert>
    );
  }

  return (
    <Paper withBorder p="sm">
      <Stack gap="xs">
        <Text fw={700} size="sm">선택한 QA 이슈</Text>
        {issues.map((issue, index) => (
          <Paper key={`${issue.type}-${index}`} withBorder p="sm">
            <Text size="sm" fw={600}>
              {issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체"}
            </Text>
            <Text size="sm">{formatQaMessage(issue)}</Text>
            <Text size="sm" c="dimmed">
              수정 방향: {formatSuggestedFix(issue)}
            </Text>
          </Paper>
        ))}
      </Stack>
    </Paper>
  );
}

function EvidenceTable({
  rows,
  onOpenEvidence,
}: {
  rows: EvidenceDocument[];
  onOpenEvidence: (row: EvidenceDocument) => void;
}) {
  return (
    <Paper withBorder className={classes.evidenceTable}>
      <ScrollArea>
        <Table striped highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Source</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Detail</Table.Th>
              <Table.Th>Images</Table.Th>
              <Table.Th>Score</Table.Th>
              <Table.Th>Snippet</Table.Th>
              <Table.Th>Action</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => (
              <Table.Tr key={row.doc_id}>
                <Table.Td>
                  <Text fw={600} size="sm">{row.title}</Text>
                  <Text ff="monospace" size="xs" c="dimmed">{row.doc_id}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light">{evidenceTypeLabel(row)}</Badge>
                </Table.Td>
                <Table.Td>
                  <EvidenceDetailBadge row={row} />
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" color={evidenceImageCandidates(row).length > 0 ? "green" : "gray"}>
                    {evidenceImageCandidates(row).length}
                  </Badge>
                </Table.Td>
                <Table.Td>{row.score}</Table.Td>
                <Table.Td maw={420}>
                  <Text size="sm" lineClamp={2}>{row.snippet}</Text>
                </Table.Td>
                <Table.Td>
                  <Tooltip label="Open evidence">
                    <ActionIcon
                      variant="light"
                      aria-label="Open evidence"
                      onClick={() => onOpenEvidence(row)}
                    >
                      <IconEye size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
    </Paper>
  );
}

type EvidenceImageCandidate = {
  image_url: string;
  thumbnail_url?: string;
  title?: string;
  usage_status?: string;
  source?: string;
};

function EvidenceDetailBadge({ row }: { row: EvidenceDocument }) {
  const hasDetail = row.metadata.detail_common_available === true || row.metadata.detail_common_available === "true";
  const detailInfoCount = numberFromMetadata(row.metadata.detail_info_count);
  if (!hasDetail && detailInfoCount === 0) {
    return <Badge variant="light" color="gray">basic</Badge>;
  }
  return (
    <Badge variant="light" color="green">
      detail {detailInfoCount > 0 ? `+ info ${detailInfoCount}` : ""}
    </Badge>
  );
}

function EvidenceMetadataSummary({ row }: { row: EvidenceDocument }) {
  const detailInfoCount = numberFromMetadata(row.metadata.detail_info_count);
  const imageCount = evidenceImageCandidates(row).length;
  const notes = stringListFromMetadata(row.metadata.interpretation_notes);
  const flags = stringListFromMetadata(row.metadata.data_quality_flags);
  return (
    <Paper withBorder p="sm">
      <Stack gap="xs">
        <Group gap="xs">
          <Badge variant="light">content_id: {String(row.metadata.content_id ?? "-")}</Badge>
          <Badge variant="light">detail info: {detailInfoCount}</Badge>
          <Badge variant="light">images: {imageCount}</Badge>
        </Group>
        {flags.length > 0 ? (
          <Text size="xs" c="dimmed">Data flags: {flags.join(", ")}</Text>
        ) : null}
        {notes.length > 0 ? (
          <Text size="xs" c="dimmed">{notes.join(" ")}</Text>
        ) : null}
      </Stack>
    </Paper>
  );
}

function EvidenceImageCandidates({ row }: { row: EvidenceDocument }) {
  const candidates = evidenceImageCandidates(row);
  if (candidates.length === 0) return null;

  return (
    <Stack gap="xs">
      <Text fw={700} size="sm">Image candidates</Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {candidates.slice(0, 4).map((candidate) => (
          <Paper key={candidate.image_url} withBorder p="xs">
            <Stack gap={6}>
              <Image
                src={candidate.thumbnail_url || candidate.image_url}
                alt={candidate.title || row.title}
                h={120}
                fit="cover"
                radius="sm"
              />
              <Text size="xs" fw={600} lineClamp={1}>
                {candidate.title || row.title}
              </Text>
              <Group gap={6}>
                <Badge size="xs" variant="light" color="yellow">
                  {candidate.usage_status || "candidate"}
                </Badge>
                <Badge size="xs" variant="light">
                  {candidate.source || "TourAPI"}
                </Badge>
              </Group>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>
    </Stack>
  );
}

function evidenceImageCandidates(row: EvidenceDocument): EvidenceImageCandidate[] {
  const rawCandidates = parseMetadataJson(row.metadata.image_candidates);
  const candidates = Array.isArray(rawCandidates) ? rawCandidates : [];
  const normalized = candidates
    .map((candidate) => {
      if (!candidate || typeof candidate !== "object") return null;
      const record = candidate as Record<string, unknown>;
      const imageUrl = String(record.image_url || "");
      if (!imageUrl) return null;
      return {
        image_url: imageUrl,
        thumbnail_url: String(record.thumbnail_url || imageUrl),
        title: record.title ? String(record.title) : row.title,
        usage_status: record.usage_status ? String(record.usage_status) : "candidate",
        source: record.source ? String(record.source) : "TourAPI",
      };
    })
    .filter(Boolean) as EvidenceImageCandidate[];

  if (normalized.length > 0) return normalized;
  const imageUrl = row.metadata.image_url ? String(row.metadata.image_url) : "";
  return imageUrl
    ? [
        {
          image_url: imageUrl,
          thumbnail_url: imageUrl,
          title: row.title,
          usage_status: "candidate",
          source: "detail_common",
        },
      ]
    : [];
}

function parseMetadataJson(value: unknown): unknown {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function stringListFromMetadata(value: unknown): string[] {
  const parsed = parseMetadataJson(value);
  if (Array.isArray(parsed)) return parsed.map(String).filter(Boolean);
  if (typeof parsed === "string" && parsed.trim()) return [parsed.trim()];
  return [];
}

function numberFromMetadata(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function QASection({
  report,
  products,
  selectedIssueKeys,
  onToggleIssue,
  onToggleAll,
  onDeleteSelected,
  deleteLoading,
}: {
  report: QAReport;
  products: ProductIdea[];
  selectedIssueKeys: string[];
  onToggleIssue: (issue: QAIssue, index: number) => void;
  onToggleAll: (checked: boolean) => void;
  onDeleteSelected: () => void;
  deleteLoading: boolean;
}) {
  const productTitleById = new Map(products.map((product) => [product.id, product.title]));
  const hasSummaryFailure =
    report.overall_status !== "pass" || report.fail_count > 0 || report.needs_review_count > 0;
  const allSelected = report.issues.length > 0 && selectedIssueKeys.length === report.issues.length;
  const selectedCount = selectedIssueKeys.length;

  return (
    <Paper withBorder p="md">
      <Group justify="space-between">
        <div>
          <Text fw={700}>QA Review</Text>
          <Text size="sm" c="dimmed">{report.summary}</Text>
        </div>
        <Badge color={report.overall_status === "pass" ? "green" : "yellow"} variant="light">
          {report.overall_status}
        </Badge>
      </Group>
      <Group justify="space-between" mt="sm">
        <Group gap="xs">
          {report.issues.length > 0 ? (
            <Checkbox
              size="xs"
              label={`${selectedCount}/${report.issues.length} 선택됨`}
              checked={allSelected}
              indeterminate={selectedCount > 0 && !allSelected}
              onChange={(event) => onToggleAll(event.currentTarget.checked)}
            />
          ) : null}
        </Group>
        {report.issues.length > 0 ? (
          <Button
            size="xs"
            variant="light"
            color="red"
            disabled={selectedCount === 0}
            loading={deleteLoading}
            onClick={onDeleteSelected}
          >
            선택 리뷰 삭제
          </Button>
        ) : null}
      </Group>
      <Divider my="sm" />
      {report.issues.length === 0 ? (
        <Alert color={hasSummaryFailure ? "yellow" : "green"}>
          {hasSummaryFailure
            ? "QA 요약에는 이슈가 있다고 표시되었지만 상세 이슈가 없습니다. Raw JSON에서 qa_report를 확인하세요."
            : "검수에서 차단 수준의 이슈가 없습니다."}
        </Alert>
      ) : (
        <ScrollArea>
          <Table verticalSpacing="sm" className={classes.qaTable}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th className={classes.qaSelectColumn}></Table.Th>
                <Table.Th className={classes.qaProductColumn}>Product</Table.Th>
                <Table.Th className={classes.qaSeverityColumn}>Severity</Table.Th>
                <Table.Th className={classes.qaTypeColumn}>Type</Table.Th>
                <Table.Th className={classes.qaMessageColumn}>Message</Table.Th>
                <Table.Th className={classes.qaFixColumn}>Suggested fix</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {report.issues.map((issue, index) => (
                <Table.Tr key={`${issue.type}-${index}`}>
                  <Table.Td className={classes.qaSelectColumn}>
                    <Checkbox
                      size="xs"
                      aria-label="Select QA issue"
                      checked={selectedIssueKeys.includes(qaIssueKey(issue, index))}
                      onChange={() => onToggleIssue(issue, index)}
                    />
                  </Table.Td>
                  <Table.Td className={classes.qaProductColumn}>
                    <Text size="sm">
                      {issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체"}
                    </Text>
                  </Table.Td>
                  <Table.Td className={classes.qaSeverityColumn}>
                    <Badge
                      className={classes.qaSeverityBadge}
                      color={severityColor(issue.severity)}
                      variant="light"
                    >
                      {formatSeverity(issue.severity)}
                    </Badge>
                  </Table.Td>
                  <Table.Td className={classes.qaTypeColumn}>{formatIssueType(issue.type)}</Table.Td>
                  <Table.Td className={classes.qaMessageColumn}>
                    <Text size="sm">{formatQaMessage(issue)}</Text>
                  </Table.Td>
                  <Table.Td className={classes.qaFixColumn}>
                    <Text size="sm">{formatSuggestedFix(issue)}</Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </Paper>
  );
}

function ApprovalHistory({
  approvals,
  sourceApprovals = [],
}: {
  approvals: Approval[];
  sourceApprovals?: Approval[];
}) {
  return (
    <Paper withBorder p="md">
      <Text fw={700}>Approval History</Text>
      {sourceApprovals.length > 0 ? (
        <>
          <Text size="sm" c="dimmed" mt="xs">
            원본 run의 request changes와 검토 기록입니다.
          </Text>
          <ApprovalHistoryTable approvals={sourceApprovals} mt="sm" />
          <Divider my="sm" />
          <Text fw={600} size="sm">Current run decisions</Text>
        </>
      ) : null}
      {approvals.length === 0 ? (
        <Text size="sm" c="dimmed" mt="xs">아직 검토 결정이 없습니다.</Text>
      ) : (
        <ApprovalHistoryTable approvals={approvals} mt="sm" />
      )}
    </Paper>
  );
}

function ApprovalHistoryTable({ approvals, mt }: { approvals: Approval[]; mt?: string }) {
  return (
    <Table mt={mt} verticalSpacing="sm">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Decision</Table.Th>
          <Table.Th>Reviewer</Table.Th>
          <Table.Th>Comment</Table.Th>
          <Table.Th>Created</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {approvals.map((approval) => (
          <Table.Tr key={approval.id}>
            <Table.Td><Badge variant="light">{approval.decision}</Badge></Table.Td>
            <Table.Td>{approval.reviewer}</Table.Td>
            <Table.Td>{approval.comment ?? "-"}</Table.Td>
            <Table.Td>{formatKstDateTime(approval.created_at)}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
