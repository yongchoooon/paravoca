import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent } from "react";
import {
  ActionIcon,
  Accordion,
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
  Paper,
  ScrollArea,
  Select,
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
  IconAlertCircle,
  IconArrowUpRight,
  IconChevronDown,
  IconChevronUp,
  IconDownload,
  IconEdit,
  IconEye,
  IconGitBranch,
  IconPlayerStop,
  IconPhotoPlus,
  IconRefresh,
  IconTrash,
  IconZoomIn,
  IconZoomOut,
  IconX,
} from "@tabler/icons-react";
import { StatusBadge } from "../components/StatusBadge";
import {
  AgentStep,
  Approval,
  approveWorkflowRun,
  cancelWorkflowRun,
  createWorkflowRevision,
  deleteWorkflowRunQaIssues,
  EnrichmentRun,
  EvidenceDocument,
  getWorkflowRun,
  getWorkflowRunEnrichment,
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
  WorkflowEnrichmentSummary,
} from "../services/runsApi";
import {
  DEFAULT_POSTER_INCLUDED_SECTIONS,
  DEFAULT_POSTER_STYLE,
  POSTER_SECTION_LABELS,
  PosterAsset,
  PosterIncludedSection,
  PosterOptions,
  PosterStylePresetId,
  createPoster,
  deletePoster,
  getPosterOptions,
  isActivePosterStatus,
  isCountedPosterStatus,
  listRunPosters,
  posterDownloadUrl,
  posterImageSrc,
} from "../services/postersApi";
import { formatKstDateTime } from "../utils/datetime";
import { RunLogs } from "./RunLogs";
import classes from "./RunDetail.module.css";
import {
  ACTIVE_RUN_STATUSES,
  arrayOrEmpty,
  cloneJson,
  errorMessage,
  formatIssueType,
  formatQaMessage,
  formatSeverity,
  formatSuggestedFix,
  joinLines,
  normalizeWorkflowResult,
  qaIssueKey,
  qaIssueKeys,
  revisionModeLabel,
  revisionQaSettingsFromRun,
  RevisionQaSettings,
  severityColor,
  splitLines,
  workflowStages,
} from "./runDetailUtils";

type ApprovalAction = "approve" | "reject" | "request_changes";
type RunDetailTab = "review" | "evidence" | "developer";

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

const POSTER_SECTION_ORDER = Object.keys(POSTER_SECTION_LABELS) as PosterIncludedSection[];
const POSTER_IMAGE_CANDIDATE_PAGE_SIZE = 6;

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
  const [enrichment, setEnrichment] = useState<WorkflowEnrichmentSummary | null>(null);
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
  const [stoppingRun, setStoppingRun] = useState(false);
  const [posters, setPosters] = useState<PosterAsset[]>([]);
  const [posterOptions, setPosterOptions] = useState<PosterOptions | null>(null);
  const [posterModalProduct, setPosterModalProduct] = useState<ProductIdea | null>(null);
  const [posterIncludedSections, setPosterIncludedSections] = useState<PosterIncludedSection[]>(
    DEFAULT_POSTER_INCLUDED_SECTIONS
  );
  const [posterStylePreset, setPosterStylePreset] = useState<PosterStylePresetId>(DEFAULT_POSTER_STYLE);
  const [posterGenerating, setPosterGenerating] = useState(false);
  const [posterError, setPosterError] = useState<string | null>(null);
  const [posterResult, setPosterResult] = useState<PosterAsset | null>(null);
  const [previewPoster, setPreviewPoster] = useState<PosterAsset | null>(null);
  const [deletingPosterIds, setDeletingPosterIds] = useState<string[]>([]);
  const [posterInputImages, setPosterInputImages] = useState<string[]>([]);
  const [posterInputImagePreview, setPosterInputImagePreview] = useState<EvidenceImageCandidate | null>(null);
  const [posterImageCandidateLimit, setPosterImageCandidateLimit] = useState(POSTER_IMAGE_CANDIDATE_PAGE_SIZE);
  const [previewPosterZoomed, setPreviewPosterZoomed] = useState(false);
  const [posterInputImagePreviewZoomed, setPosterInputImagePreviewZoomed] = useState(false);
  const [evidenceImagePreview, setEvidenceImagePreview] = useState<EvidenceImageCandidate | null>(null);
  const [evidenceImagePreviewZoomed, setEvidenceImagePreviewZoomed] = useState(false);
  const [posterExpandedSections, setPosterExpandedSections] = useState<PosterIncludedSection[]>([]);

  async function loadRunDetail(options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setLoading(true);
      }
      setError(null);
      const nextRun = await getWorkflowRun(runId);
      const [
        resultResponse,
        stepsResponse,
        toolCallsResponse,
        enrichmentResponse,
        llmCallsResponse,
        approvalsResponse,
        postersResponse,
        posterOptionsResponse,
      ] =
        await Promise.allSettled([
          getWorkflowRunResult(runId),
          listRunSteps(runId),
          listRunToolCalls(runId),
          getWorkflowRunEnrichment(runId),
          listRunLlmCalls(runId),
          listRunApprovals(runId),
          listRunPosters(runId),
          getPosterOptions(),
        ]);
      setRun(nextRun);
      const nextSteps = stepsResponse.status === "fulfilled" ? stepsResponse.value : [];
      const nextToolCalls = toolCallsResponse.status === "fulfilled" ? toolCallsResponse.value : [];
      const nextEnrichment = enrichmentResponse.status === "fulfilled" ? enrichmentResponse.value : null;
      const nextLlmCalls = llmCallsResponse.status === "fulfilled" ? llmCallsResponse.value : [];
      const nextApprovals = approvalsResponse.status === "fulfilled" ? approvalsResponse.value : [];
      const nextPosters = postersResponse.status === "fulfilled" ? postersResponse.value : [];
      const nextPosterOptions =
        posterOptionsResponse.status === "fulfilled" ? posterOptionsResponse.value : null;
      setSteps(nextSteps);
      setToolCalls(nextToolCalls);
      setEnrichment(nextEnrichment);
      setLlmCalls(nextLlmCalls);
      setApprovals(nextApprovals);
      setPosters(nextPosters);
      setPosterOptions(nextPosterOptions);
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

  const hasActivePosters = useMemo(
    () => posters.some((poster) => isActivePosterStatus(poster.status)),
    [posters]
  );

  useEffect(() => {
    if (!hasActivePosters || isActiveRun) return;
    const timer = window.setInterval(() => {
      void loadRunDetail({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasActivePosters, isActiveRun, runId]);

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
    const selectedSourceIds = Array.from(
      new Set(result.products.flatMap((product) => stringListFromUnknown(product.source_ids)))
    );
    if (!showSelectedProductEvidenceOnly || selectedSourceIds.length === 0) {
      return result.retrieved_documents;
    }
    const sourceIds = new Set(selectedSourceIds);
    return result.retrieved_documents.filter((doc) => sourceIds.has(doc.doc_id));
  }, [result, showSelectedProductEvidenceOnly]);

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

  const postersByProduct = useMemo(() => {
    const map = new Map<string, PosterAsset[]>();
    posters
      .slice()
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .forEach((poster) => {
        map.set(poster.product_id, [...(map.get(poster.product_id) ?? []), poster]);
      });
    return map;
  }, [posters]);

  const modalPoster =
    posterResult ?? (posterModalProduct ? postersByProduct.get(posterModalProduct.id)?.[0] ?? null : null);
  const modalProductPosters = posterModalProduct ? postersByProduct.get(posterModalProduct.id) ?? [] : [];
  const maxPostersPerProduct = posterOptions?.max_posters_per_product ?? 3;
  const modalCountedPosterCount = modalProductPosters.filter((poster) =>
    isCountedPosterStatus(poster.status)
  ).length;
  const modalProductAtLimit = modalCountedPosterCount >= maxPostersPerProduct;
  const modalImageCandidates = useMemo(() => {
    if (!posterModalProduct || !result) return [];
    return productVisualCandidates(posterModalProduct, result.retrieved_documents);
  }, [posterModalProduct, result]);
  const modalMarketing = useMemo(() => {
    if (!posterModalProduct || !result) return null;
    return result.marketing_assets.find((asset) => asset.product_id === posterModalProduct.id) ?? null;
  }, [posterModalProduct, result]);

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

  const qaAvoidRules = useMemo(
    () => avoidRulesForQaReview(run, result),
    [run, result]
  );

  const revisionModalTitle =
    revisionMode === "qa_only"
      ? "QA 재검수 실행"
      : revisionMode === "llm_partial_rewrite"
        ? "AI 수정 실행"
        : "직접 수정";
  const revisionModalDescription =
    revisionMode === "manual_edit"
      ? "QA 이슈 전체를 참고하면서 상품과 마케팅 문구를 직접 수정하고 새 Revision으로 저장합니다."
      : revisionMode === "qa_only"
        ? "상품 내용은 바꾸지 않고 선택한 QA 이슈가 해결됐는지만 다시 확인합니다."
        : "선택한 QA 이슈와 요청 배경을 바탕으로 필요한 필드만 AI가 수정합니다.";
  const revisionPrimaryLabel =
    revisionMode === "manual_edit"
      ? "저장 후 QA 재검수"
      : revisionMode === "qa_only"
        ? "QA 재검수 실행"
        : "AI 수정 실행";
  const revisionSubmitDisabled = revisionMode !== "manual_edit" && selectedQaIssues.length === 0;
  const revisionDisabledReason =
    revisionMode !== "manual_edit" && selectedQaIssues.length === 0
      ? "실행하려면 Evidence + QA 탭에서 확인할 QA 이슈를 먼저 선택해야 합니다."
      : null;

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

  function openRevisionModal(mode: Exclude<RevisionMode, "manual_save">) {
    if (!result) return;
    setRevisionMode(mode);
    setRevisionComment(mode === "qa_only" ? "QA 재검수" : "");
    setRevisionQaSettings(revisionQaSettingsFromRun(run));
    setEditableProducts(cloneJson(result.products));
    setEditableMarketingAssets(cloneJson(result.marketing_assets));
    setEditProductId(result.products[0]?.id ?? null);
    setRevisionModalOpen(true);
  }

  function openAiRevisionFromQaIssues() {
    if (!result || selectedQaIssues.length === 0) return;
    openRevisionModal("llm_partial_rewrite");
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

  async function stopActiveRun() {
    if (!run || !isActiveRun) return;
    try {
      setStoppingRun(true);
      const response = await cancelWorkflowRun(run.id);
      setRun(response.run);
      notifications.show({
        title: "실행 중지 요청",
        message: response.message,
        color: "yellow",
      });
      await loadRunDetail({ silent: true });
      await onStatusChanged();
    } catch (err) {
      notifications.show({
        title: "실행 중지 실패",
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setStoppingRun(false);
    }
  }

  function openPosterModal(product: ProductIdea) {
    setPosterModalProduct(product);
    setPosterIncludedSections(
      posterOptions?.default_included_sections.length
        ? posterOptions.default_included_sections
        : DEFAULT_POSTER_INCLUDED_SECTIONS
    );
    setPosterStylePreset(posterOptions?.style_presets[0]?.id ?? DEFAULT_POSTER_STYLE);
    setPosterError(null);
    setPosterResult(postersByProduct.get(product.id)?.[0] ?? null);
    setPosterInputImages([]);
    setPosterImageCandidateLimit(POSTER_IMAGE_CANDIDATE_PAGE_SIZE);
    setPosterExpandedSections([]);
  }

  function togglePosterSection(section: PosterIncludedSection, checked: boolean) {
    setPosterIncludedSections((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(section);
      } else {
        next.delete(section);
      }
      return POSTER_SECTION_ORDER.filter((item) => next.has(item));
    });
  }

  function togglePosterInputImage(url: string) {
    setPosterInputImages((current) => {
      if (current.includes(url)) {
        return current.filter((item) => item !== url);
      }
      if (current.length >= 3) {
        return current;
      }
      return [...current, url];
    });
  }

  function togglePosterExpandedSection(section: PosterIncludedSection) {
    setPosterExpandedSections((current) =>
      current.includes(section)
        ? current.filter((item) => item !== section)
        : [...current, section]
    );
  }

  async function submitPosterGeneration() {
    if (!run || !posterModalProduct) return;
    try {
      setPosterGenerating(true);
      setPosterError(null);
      const poster = await createPoster(run.id, posterModalProduct.id, {
        style_preset: posterStylePreset,
        included_sections: posterIncludedSections,
        input_images: posterInputImages.length > 0 ? posterInputImages : undefined,
      });
      setPosterResult(poster);
      setPosters((current) => [poster, ...current.filter((item) => item.id !== poster.id)]);
      notifications.show({
        title: "포스터 생성 시작",
        message: "포스터 이미지를 생성 중입니다. Run Detail과 Poster Studio에서 진행 상태를 확인할 수 있습니다.",
        color: "blue",
      });
      setPosterModalProduct(null);
      setPosterResult(null);
      setPosterInputImages([]);
      setPosterImageCandidateLimit(POSTER_IMAGE_CANDIDATE_PAGE_SIZE);
      setPosterExpandedSections([]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "포스터 생성에 실패했습니다.";
      setPosterError(message);
      notifications.show({ title: "포스터 생성 실패", message, color: "red" });
      try {
        setPosters(await listRunPosters(run.id));
      } catch {
        // Keep the original generation error visible.
      }
    } finally {
      setPosterGenerating(false);
    }
  }

  async function deleteRunDetailPoster(poster: PosterAsset) {
    try {
      setDeletingPosterIds((current) => [...current, poster.id]);
      await deletePoster(poster.id);
      setPosters((current) => current.filter((item) => item.id !== poster.id));
      setPreviewPoster((current) => (current?.id === poster.id ? null : current));
      notifications.show({
        title: "포스터 삭제",
        message: "저장된 포스터 기록을 삭제했습니다.",
        color: "gray",
      });
    } catch (err) {
      notifications.show({
        title: "포스터 삭제 실패",
        message: err instanceof Error ? err.message : "포스터를 삭제하지 못했습니다.",
        color: "red",
      });
    } finally {
      setDeletingPosterIds((current) => current.filter((id) => id !== poster.id));
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
    const mode = modeOverride ?? revisionMode;
    const shouldSendSelectedQaIssues =
      mode === "llm_partial_rewrite" || mode === "manual_edit" || mode === "qa_only";
    const qaIssuesForRevision = mode === "manual_edit" ? result.qa_report.issues : selectedQaIssues;
    const payload = {
      revision_mode: mode,
      comment: revisionComment.trim() || null,
      requested_changes: [],
      qa_issues: shouldSendSelectedQaIssues ? qaIssuesForRevision : [],
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
      enrichment,
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
            {isActiveRun ? (
              <Button
                color="red"
                variant="light"
                leftSection={<IconPlayerStop size={16} />}
                loading={stoppingRun}
                onClick={stopActiveRun}
              >
                실행 중지
              </Button>
            ) : null}
          </Group>
          <RequestPromptPanel run={run} originalRun={rootRun ?? run} />
          <Alert
            color={run.status === "failed" ? "red" : "blue"}
            title={run.status === "failed" ? "Workflow failed" : "Result is not ready"}
          >
            {run.error ? errorMessage(run.error) : "아직 생성된 result가 없습니다."}
          </Alert>
          <GeoClarificationFromSteps steps={steps} />
          <UserWorkflowProgress steps={steps} run={run} result={null} />
          <Accordion variant="contained">
            <Accordion.Item value="developer">
              <Accordion.Control>Developer debug</Accordion.Control>
              <Accordion.Panel>
                <RunLogs
                  run={run}
                  steps={steps}
                  toolCalls={toolCalls}
                  llmCalls={llmCalls}
                  agentExecution={[]}
                />
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
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
            {isActiveRun ? (
              <Button
                color="red"
                variant="light"
                leftSection={<IconPlayerStop size={16} />}
                loading={stoppingRun}
                onClick={stopActiveRun}
              >
                실행 중지
              </Button>
            ) : null}
            <Tooltip
              label={
                selectedQaIssues.length === 0
                  ? "AI 수정하려면 먼저 QA 이슈를 선택하세요."
                  : "선택한 QA 이슈를 AI가 수정합니다."
              }
            >
              <span>
                <Button
                  variant="light"
                  leftSection={<IconGitBranch size={16} />}
                  disabled={!canCreateRevision || selectedQaIssues.length === 0}
                  onClick={openAiRevisionFromQaIssues}
                >
                  AI 수정
                </Button>
              </span>
            </Tooltip>
            <Button
              variant="light"
              disabled={!canCreateRevision}
              onClick={() => openRevisionModal("manual_edit")}
            >
              직접 수정
            </Button>
            <Tooltip
              label={
                selectedQaIssues.length === 0
                  ? "QA 재검수하려면 먼저 확인할 QA 이슈를 선택하세요."
                  : "선택한 QA 이슈만 다시 확인합니다."
              }
            >
              <span>
                <Button
                  variant="subtle"
                  disabled={!canCreateRevision || selectedQaIssues.length === 0}
                  loading={revisionSubmitting && !revisionModalOpen}
                  onClick={() => openRevisionModal("qa_only")}
                >
                  QA 재검수
                </Button>
              </span>
            </Tooltip>
            <Button
              variant="light"
              leftSection={<IconDownload size={16} />}
              onClick={exportJson}
            >
              Export JSON
            </Button>
          </Group>
        </Group>

        <RequestPromptPanel run={run} originalRun={rootRun ?? run} />

        {isActiveRun ? (
          <Alert color="blue">
            <Group gap="sm" align="flex-start">
              <Loader size="sm" type="oval" mt={2} />
              <div>
                <Text fw={700}>{run.status === "cancelling" ? "Workflow stop requested" : "Workflow is running"}</Text>
                {run.status === "cancelling" ? (
                  <Text size="sm" c="dimmed">
                    현재 실행 중인 단계가 끝나면 중지됩니다.
                  </Text>
                ) : null}
                <UserWorkflowProgress steps={steps} run={run} result={result} />
              </div>
            </Group>
          </Alert>
        ) : null}

        {run.status === "failed" && !isGeoClarificationResult(result) && !isInsufficientSourceDataResult(result) ? (
          <Alert color="red" title="Workflow failed">
            {run.error ? errorMessage(run.error) : "Developer 탭에서 실패한 step과 error log를 확인하세요."}
          </Alert>
        ) : null}

        {result.status === "unsupported" ? (
          <SupportScopeNotice result={result} />
        ) : null}

        {isGeoClarificationResult(result) ? (
          <GeoClarificationNotice result={result} />
        ) : null}

        {isInsufficientSourceDataResult(result) ? (
          <InsufficientSourceDataNotice result={result} />
        ) : null}

        {result.status === "cancelled" ? (
          <Alert color="gray" title="실행이 중지되었습니다">
            {typeof result.user_message?.message === "string"
              ? result.user_message.message
              : "사용자 요청으로 workflow 실행을 중지했습니다."}
          </Alert>
        ) : null}

        <SimpleGrid cols={{ base: 1, sm: 4 }}>
          <Metric label="Products" value={String(result.products.length)} />
          <Metric label="Evidence" value={String(result.retrieved_documents.length)} />
          <Metric label="QA status" value={result.qa_report.overall_status} />
          <Metric label="LLM mode" value={String(result.cost_summary.mode ?? "-")} />
        </SimpleGrid>

        <GeoScopePanel scope={geoScopeFromResult(result)} />
        <EnrichmentOverview result={result} enrichment={enrichment} />

        <Tabs
          value={activeTab}
          onChange={(value) => setActiveTab((value as RunDetailTab | null) ?? "review")}
        >
          <Tabs.List>
            <Tabs.Tab value="review">Result Review</Tabs.Tab>
            <Tabs.Tab value="evidence">Evidence + QA</Tabs.Tab>
            <Tabs.Tab value="developer">Developer</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="review" pt="md">
            <ReviewQaSummary report={result.qa_report} avoidRules={qaAvoidRules} />
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
                    <ProductDetail
                      product={selectedProduct}
                      marketing={selectedMarketing}
                      evidenceDocuments={result.retrieved_documents}
                      posters={postersByProduct.get(selectedProduct.id) ?? []}
                      posterOptions={posterOptions}
                      onCreatePoster={() => openPosterModal(selectedProduct)}
                      onDeletePoster={deleteRunDetailPoster}
                      deletingPosterIds={deletingPosterIds}
                      onPreviewPoster={setPreviewPoster}
                      onPreviewEvidenceImage={(candidate) => setEvidenceImagePreview(candidate)}
                    />
                  ) : (
                    <Text c="dimmed">생성된 상품이 없습니다.</Text>
                  )}
                </Paper>
              </div>
            ) : result.status === "unsupported" ? (
              <SupportScopeNotice result={result} />
            ) : isGeoClarificationResult(result) ? (
              <GeoClarificationReviewNotice result={result} />
            ) : isInsufficientSourceDataResult(result) ? (
              <InsufficientSourceDataNotice result={result} compact />
            ) : result.status === "cancelled" ? (
              <Alert color="gray" title="실행이 중지되었습니다">
                이 run은 사용자 요청으로 중지되었습니다. 이미 완료된 단계는 Developer 탭에서 확인할 수 있습니다.
              </Alert>
            ) : (
              <Alert color="gray">
                <Group gap="sm" align="flex-start">
                  {isActiveRun ? <Loader size="sm" type="oval" mt={2} /> : null}
                  <div>
                    <Text fw={700}>No generated product result</Text>
                    <Text size="sm">
                      {isActiveRun
                        ? "Workflow output을 아직 생성하고 있습니다."
                        : "이 run은 실패했을 수 있습니다. 상태와 에러는 Developer 탭에서 확인하세요."}
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
                  <Text fw={700} size="sm">근거와 보강 데이터</Text>
                  <Text size="sm" c="dimmed">
                    상품 생성과 QA 검수에 사용된 근거입니다. {selectedEvidenceRows.length} / {result.retrieved_documents.length}건 표시 중입니다.
                    {showSelectedProductEvidenceOnly
                      ? " 전체 상품에 연결된 근거만 표시 중입니다."
                      : ""}
                  </Text>
                </div>
                <Checkbox
                  checked={showSelectedProductEvidenceOnly}
                  disabled={result.products.every((product) => stringListFromUnknown(product.source_ids).length === 0)}
                  label="Selected evidence only"
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
                avoidRules={qaAvoidRules}
                qaDiffSummary={qaDiffSummaryFromRevision(result.revision)}
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

          <Tabs.Panel value="developer" pt="md">
            <DeveloperDebugPanel
              run={run}
              result={result}
              steps={steps}
              toolCalls={toolCalls}
              llmCalls={llmCalls}
              approvals={approvals}
              enrichment={enrichment}
            />
          </Tabs.Panel>
        </Tabs>
      </Stack>

      <Drawer
        opened={Boolean(selectedEvidence)}
        onClose={() => setSelectedEvidence(null)}
        position="right"
        size="lg"
        title={selectedEvidence?.title ?? "Evidence"}
        closeOnEscape={evidenceImagePreview === null}
      >
        {selectedEvidence ? (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge variant="light">{evidenceTypeLabel(selectedEvidence)}</Badge>
              <Badge variant="light" color="blue">{evidenceSourceLabel(selectedEvidence)}</Badge>
              <Badge variant="light" color="gray">{evidenceRegionLabel(selectedEvidence)}</Badge>
              <EvidenceDetailBadge row={selectedEvidence} />
            </Group>
            <Text size="sm" c="dimmed">{evidenceSourceDescription(selectedEvidence)}</Text>
            <EvidenceImageCandidates
              row={selectedEvidence}
              onPreviewImage={(candidate) => setEvidenceImagePreview(candidate)}
            />
            <EvidenceMetadataSummary row={selectedEvidence} />
            <Text size="sm">{selectedEvidence.content}</Text>
            <Accordion variant="contained">
              <Accordion.Item value="metadata">
                <Accordion.Control>Developer metadata</Accordion.Control>
                <Accordion.Panel>
                  <Code block>
                    {JSON.stringify(selectedEvidence.metadata, null, 2)}
                  </Code>
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          </Stack>
        ) : null}
      </Drawer>

      <Modal
        opened={posterModalProduct !== null}
        onClose={() => {
          setPosterModalProduct(null);
          setPosterError(null);
          setPosterInputImages([]);
          setPosterImageCandidateLimit(POSTER_IMAGE_CANDIDATE_PAGE_SIZE);
          setPosterExpandedSections([]);
        }}
        title="포스터 만들기"
        size="62rem"
        closeOnEscape={posterInputImagePreview === null && previewPoster === null}
      >
        <Stack gap="md">
          {posterModalProduct ? (
            <Alert color="gray">
              <Text fw={700}>{posterModalProduct.title}</Text>
              <Text size="sm" c="dimmed">
                생성 이미지는 검토용 이미지입니다. 현재는 정해진 스타일로만 생성할 수 있으며, 자유 커스터마이즈는 후속 단계에서 제공 예정입니다.
              </Text>
            </Alert>
          ) : null}

          <div className={classes.posterCreationGrid}>
            <Stack gap="sm">
              <Stack gap={6}>
                <Text fw={700} size="sm">포함할 내용</Text>
                {POSTER_SECTION_ORDER.map((section) => (
                  <PosterSectionOption
                    key={section}
                    section={section}
                    checked={posterIncludedSections.includes(section)}
                    expanded={posterExpandedSections.includes(section)}
                    preview={posterSectionPreview(section, posterModalProduct, modalMarketing)}
                    disabled={posterGenerating}
                    onToggleChecked={(checked) => togglePosterSection(section, checked)}
                    onToggleExpanded={() => togglePosterExpandedSection(section)}
                  />
                ))}
              </Stack>

              <Stack gap={6}>
                <Text fw={700} size="sm">참조 이미지 선택 (최대 3개)</Text>
                <Text size="xs" c="dimmed">
                  상품 근거 데이터와 연결된 이미지 후보를 관련성이 높은 순서로 보여줍니다. 이미지를 누르면 크게 확인할 수 있습니다.
                </Text>
                {modalImageCandidates.length > 0 ? (
                  <Stack gap="xs">
                    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="xs">
                      {modalImageCandidates.slice(0, posterImageCandidateLimit).map((candidate) => {
                        const url = candidate.image_url;
                        const selected = posterInputImages.includes(url);
                        const disabled = !selected && posterInputImages.length >= 3;
                        return (
                          <Paper
                            key={url}
                            withBorder
                            p="xs"
                            className={classes.posterReferenceImageCard}
                            style={{
                              opacity: disabled ? 0.5 : 1,
                              outline: selected ? "2px solid var(--mantine-color-blue-6)" : "none",
                              outlineOffset: "-2px",
                            }}
                          >
                            <Stack gap={6}>
                              <button
                                type="button"
                                className={classes.posterReferenceImageButton}
                                onClick={() => setPosterInputImagePreview(candidate)}
                                aria-label={`${candidate.title || "참조 이미지 후보"} 크게 보기`}
                              >
                                <Image
                                  src={candidate.thumbnail_url || url}
                                  alt={candidate.title || "참조 이미지 후보"}
                                  h={118}
                                  w="100%"
                                  fit="cover"
                                  radius="xs"
                                />
                              </button>
                              <Text size="xs" fw={700} lineClamp={2}>
                                {candidate.title || "이미지 후보"}
                              </Text>
                              <Button
                                size="xs"
                                variant={selected ? "filled" : "light"}
                                disabled={disabled || posterGenerating}
                                onClick={() => togglePosterInputImage(url)}
                              >
                                {selected ? "선택 해제" : "선택"}
                              </Button>
                            </Stack>
                          </Paper>
                        );
                      })}
                    </SimpleGrid>
                    {modalImageCandidates.length > posterImageCandidateLimit ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        onClick={() =>
                          setPosterImageCandidateLimit((current) => current + POSTER_IMAGE_CANDIDATE_PAGE_SIZE)
                        }
                      >
                        더 보기 ({Math.min(modalImageCandidates.length, posterImageCandidateLimit + POSTER_IMAGE_CANDIDATE_PAGE_SIZE)} / {modalImageCandidates.length})
                      </Button>
                    ) : modalImageCandidates.length > POSTER_IMAGE_CANDIDATE_PAGE_SIZE ? (
                      <Button
                        size="xs"
                        variant="subtle"
                        onClick={() => setPosterImageCandidateLimit(POSTER_IMAGE_CANDIDATE_PAGE_SIZE)}
                      >
                        접기
                      </Button>
                    ) : null}
                  </Stack>
                ) : (
                  <Text size="xs" c="dimmed" fs="italic">
                    이 상품에 연결된 이미지 후보를 찾지 못했습니다.
                  </Text>
                )}
                {posterInputImages.length > 0 ? (
                  <Stack gap={4}>
                    <Text size="xs" fw={600}>선택된 이미지 ({posterInputImages.length}/3)</Text>
                    {posterInputImages.map((url) => {
                      const candidate = modalImageCandidates.find((item) => item.image_url === url);
                      return (
                        <Group key={url} gap="xs" wrap="nowrap">
                          <Text size="xs" c="dimmed" lineClamp={1} style={{ flex: 1 }}>
                            {candidate?.title || "선택된 이미지"}
                          </Text>
                          <ActionIcon
                            size="xs"
                            variant="subtle"
                            color="red"
                            aria-label="선택 이미지 제거"
                            disabled={posterGenerating}
                            onClick={() =>
                              setPosterInputImages((current) => current.filter((item) => item !== url))
                            }
                          >
                            <IconTrash size={12} />
                          </ActionIcon>
                        </Group>
                      );
                    })}
                  </Stack>
                ) : null}
              </Stack>

              <Select
                label="스타일"
                data={(posterOptions?.style_presets ?? []).map((preset) => ({
                  value: preset.id,
                  label: preset.label,
                }))}
                value={posterStylePreset}
                onChange={(value) =>
                  setPosterStylePreset((value as PosterStylePresetId) ?? DEFAULT_POSTER_STYLE)
                }
                disabled={!posterOptions || posterGenerating}
              />
              {posterOptions?.style_presets.find((preset) => preset.id === posterStylePreset)?.description ? (
                <Text size="xs" c="dimmed">
                  {posterOptions.style_presets.find((preset) => preset.id === posterStylePreset)?.description}
                </Text>
              ) : null}

              <Alert color="blue" variant="light">
                <Stack gap={2}>
                  <Text size="sm">- 상품 1개당 최대 {maxPostersPerProduct}개까지 저장됩니다.</Text>
                  <Text size="sm">- 이 상품은 현재 {modalCountedPosterCount}개를 사용 중입니다.</Text>
                  <Text size="sm">- 크기는 {posterOptions?.image_size ?? "1024x1536"} portrait로 고정되어 있습니다.</Text>
                </Stack>
              </Alert>

              {posterError ? (
                <Alert color="red" icon={<IconAlertCircle size={16} />}>
                  {posterError}
                </Alert>
              ) : null}

              <Button
                leftSection={posterGenerating ? <Loader size={16} /> : <IconPhotoPlus size={16} />}
                onClick={() => void submitPosterGeneration()}
                disabled={
                  !posterModalProduct ||
                  posterIncludedSections.length === 0 ||
                  posterGenerating ||
                  modalProductAtLimit
                }
              >
                {posterGenerating ? "포스터 생성 요청 중" : "포스터 생성"}
              </Button>
              {modalProductAtLimit ? (
                <Text size="sm" c="dimmed">
                  이 상품은 포스터 {maxPostersPerProduct}개를 모두 사용 중입니다. 기존 포스터를 삭제하면 하나 더 만들 수 있습니다.
                </Text>
              ) : null}
              {posterGenerating ? (
                <Text size="sm" c="dimmed">
                  생성 작업을 등록하고 있습니다. 등록 후에는 이 창을 닫거나 화면을 이동해도 계속 진행됩니다.
                </Text>
              ) : null}
            </Stack>

            <Paper withBorder p="xs" className={classes.posterPreviewPanel}>
              {posterGenerating ? (
                <Stack h={360} align="center" justify="center">
                  <Loader />
                  <Text size="sm" c="dimmed">포스터 생성 작업을 등록하는 중입니다.</Text>
                </Stack>
              ) : modalPoster?.status === "succeeded" ? (
                <Stack gap="sm">
                  <button
                    type="button"
                    className={classes.modalPosterPreviewButton}
                    onClick={() => setPreviewPoster(modalPoster)}
                    aria-label={`${modalPoster.product_title} 포스터 크게 보기`}
                  >
                    <Image
                      src={posterImageSrc(modalPoster)}
                      alt={modalPoster.product_title}
                      radius="sm"
                      fit="contain"
                      className={classes.modalPosterPreviewImage}
                    />
                  </button>
                  <Group justify="space-between">
                    <Button
                      component="a"
                      href={posterDownloadUrl(modalPoster.id)}
                      leftSection={<IconDownload size={16} />}
                    >
                      다운로드
                    </Button>
                  </Group>
                </Stack>
              ) : modalPoster?.status === "failed" ? (
                <Alert color="red" title="마지막 포스터 생성 실패">
                  <Stack gap="xs">
                    <Text size="sm">{modalPoster.error?.message ?? "포스터 생성에 실패했습니다."}</Text>
                  </Stack>
                </Alert>
              ) : modalPoster && isActivePosterStatus(modalPoster.status) ? (
                <Stack h={360} align="center" justify="center">
                  <Loader />
                  <Text size="sm" c="dimmed">
                    최근 포스터 이미지를 생성 중입니다.
                  </Text>
                  <Badge variant="light" color="gray">{posterStyleLabel(modalPoster.style_preset, posterOptions)}</Badge>
                </Stack>
              ) : (
                <Stack h={360} justify="center" align="center">
                  <Text fw={700}>아직 생성된 포스터가 없습니다.</Text>
                  <Text size="sm" c="dimmed" ta="center">
                    포함할 내용과 스타일을 선택한 뒤 포스터를 생성하세요.
                  </Text>
                </Stack>
              )}
            </Paper>
          </div>
        </Stack>
      </Modal>

      <Modal
        opened={previewPoster !== null}
        onClose={() => {
          setPreviewPoster(null);
          setPreviewPosterZoomed(false);
        }}
        withCloseButton={false}
        padding={0}
        size="auto"
        centered
        styles={{
          content: { background: "transparent", boxShadow: "none", maxHeight: "none", overflow: "visible" },
          body: { padding: 0, overflow: "visible" },
        }}
      >
        {previewPoster ? (
          <ZoomImage
            src={posterImageSrc(previewPoster)}
            alt={previewPoster.product_title}
            zoomed={previewPosterZoomed}
            onToggleZoom={() => setPreviewPosterZoomed((value) => !value)}
          />
        ) : null}
      </Modal>

      <Modal
        opened={posterInputImagePreview !== null}
        onClose={() => {
          setPosterInputImagePreview(null);
          setPosterInputImagePreviewZoomed(false);
        }}
        withCloseButton={false}
        padding={0}
        size="auto"
        centered
        styles={{
          content: { background: "transparent", boxShadow: "none", maxHeight: "none", overflow: "visible" },
          body: { padding: 0, overflow: "visible" },
        }}
      >
        {posterInputImagePreview ? (
          <ZoomImage
            src={posterInputImagePreview.image_url}
            alt={posterInputImagePreview.title || "참조 이미지 후보"}
            zoomed={posterInputImagePreviewZoomed}
            onToggleZoom={() => setPosterInputImagePreviewZoomed((value) => !value)}
          />
        ) : null}
      </Modal>

      <Modal
        opened={evidenceImagePreview !== null}
        onClose={() => {
          setEvidenceImagePreview(null);
          setEvidenceImagePreviewZoomed(false);
        }}
        withCloseButton={false}
        padding={0}
        size="auto"
        centered
        styles={{
          content: { background: "transparent", boxShadow: "none", maxHeight: "none", overflow: "visible" },
          body: { padding: 0, overflow: "visible" },
        }}
      >
        {evidenceImagePreview ? (
          <ZoomImage
            src={evidenceImagePreview.image_url}
            alt={evidenceImagePreview.title || "근거 이미지 후보"}
            zoomed={evidenceImagePreviewZoomed}
            onToggleZoom={() => setEvidenceImagePreviewZoomed((value) => !value)}
          />
        ) : null}
      </Modal>

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
        title={revisionModalTitle}
        size="min(1180px, calc(100vw - 32px))"
        classNames={{
          body: classes.revisionModalBody,
          content: classes.revisionModalContent,
        }}
      >
        <div className={classes.revisionModalShell}>
          <section className={classes.revisionModalHeader} aria-label="Revision summary">
            <Group justify="space-between" align="flex-start" gap="md">
              <div className={classes.revisionHeaderCopy}>
                <Text fw={700}>{revisionModalTitle}</Text>
                <Text size="sm" c="dimmed">
                  {revisionModalDescription}
                </Text>
              </div>
            </Group>
          </section>

          {revisionMode === "manual_edit" ? (
            <div className={`${classes.revisionModalMain} ${classes.revisionManualMain}`}>
              <section
                className={`${classes.revisionModalColumn} ${classes.revisionManualContextColumn}`}
                aria-label="작업 컨텍스트"
              >
                <Paper withBorder p="sm" className={`${classes.productList} ${classes.revisionProductList}`}>
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
                <RevisionQaIssuesReference
                  issues={result.qa_report.issues}
                  productTitleById={productTitleById}
                />
                <Paper withBorder p="md" className={classes.revisionManualNote}>
                  <Stack gap="sm">
                    <Textarea
                      label="Revision note"
                      placeholder="직접 수정한 이유나 확인해야 할 내용을 적습니다. 예: 제목의 불필요한 숫자를 제거함"
                      minRows={5}
                      value={revisionComment}
                      onChange={(event) => setRevisionComment(event.currentTarget.value)}
                    />
                    <Text size="sm" c="dimmed">
                      편집 내용은 원본 run을 덮어쓰지 않고 새 revision으로 저장됩니다.
                    </Text>
                  </Stack>
                </Paper>
              </section>

              <section className={`${classes.revisionModalColumn} ${classes.revisionEditorColumn}`} aria-label="직접 수정 편집 영역">
                <Paper withBorder p="md" className={`${classes.panel} ${classes.revisionEditorPanel}`}>
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
              </section>
            </div>
          ) : (
            <div className={`${classes.revisionModalMain} ${classes.revisionReviewMain}`}>
              <section className={classes.revisionModalColumn} aria-label="입력 정보">
                <RevisionExecutionPanel
                  revisionMode={revisionMode}
                  revisionComment={revisionComment}
                  onCommentChange={setRevisionComment}
                  revisionQaSettings={revisionQaSettings}
                  revisionDisabledReason={revisionDisabledReason}
                />
              </section>

              <section className={classes.revisionModalColumn} aria-label="QA 이슈 선택">
                <RevisionQaIssuesSelector
                  issues={result.qa_report.issues}
                  selectedIssueKeys={selectedQaIssueKeys}
                  productTitleById={productTitleById}
                  onToggleIssue={toggleQaIssue}
                  onToggleAll={toggleAllQaIssues}
                />
              </section>
            </div>
          )}

          <footer className={classes.revisionModalFooter}>
            <Text size="sm" c={revisionDisabledReason ? "yellow.9" : "dimmed"} className={classes.revisionFooterNote}>
              {revisionDisabledReason ?? "원본 결과는 그대로 두고 새 Revision으로 기록합니다."}
            </Text>
            <Group className={classes.revisionFooterActions}>
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
              <Button
                loading={revisionSubmitting}
                disabled={revisionSubmitDisabled}
                onClick={() => void submitRevision()}
              >
                {revisionPrimaryLabel}
              </Button>
            </Group>
          </footer>
        </div>
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
  const userMessage = recordOrNull(result.user_message);
  const title = String(userMessage?.title ?? "지역을 하나로 좁혀 주세요");
  const message = String(
    userMessage?.message ?? "요청 문장만으로는 어느 지역인지 확정하기 어려워 데이터 수집을 시작하지 않았습니다."
  );
  const detail = String(
    userMessage?.detail ?? "예: `서울 중구 야간 관광 상품`처럼 시도와 시군구를 함께 넣어 다시 요청해 주세요."
  );
  return (
    <Alert color="yellow" title={title}>
      <Stack gap={4}>
        <Text size="sm">{message}</Text>
        <Text size="sm" c="dimmed">{detail}</Text>
      </Stack>
    </Alert>
  );
}

function GeoClarificationReviewNotice({ result }: { result: WorkflowResult }) {
  const userMessage = recordOrNull(result.user_message);
  const title = String(userMessage?.title ?? "아직 상품을 만들지 않았습니다");
  const message = String(userMessage?.message ?? "요청한 지역을 하나로 정하지 못해 관광 데이터 검색 전에 멈췄습니다.");
  const detail = String(userMessage?.detail ?? "위의 지역 후보를 보고 원하는 지역명을 더 구체적으로 넣어 새 run을 만들어 주세요.");
  return (
    <Alert color="gray" title={title}>
      <Stack gap={4}>
        <Text size="sm">{message}</Text>
        <Text size="sm" c="dimmed">{detail}</Text>
      </Stack>
    </Alert>
  );
}

function InsufficientSourceDataNotice({
  result,
  compact = false,
}: {
  result: WorkflowResult;
  compact?: boolean;
}) {
  const userMessage = recordOrNull(result.user_message);
  const suggestions = stringListFromUnknown(result.suggested_next_requests).length > 0
    ? stringListFromUnknown(result.suggested_next_requests)
    : stringListFromUnknown(userMessage?.suggestions);
  return (
    <Alert color="blue" title={String(userMessage?.title ?? "관광 근거 데이터가 부족합니다")}>
      <Stack gap={compact ? 6 : "xs"}>
        <Text size="sm">
          {String(
            userMessage?.message
              ?? "요청한 지역과 조건에서 상품 기획에 사용할 수 있는 관광 근거를 충분히 찾지 못했습니다."
          )}
        </Text>
        <Text size="sm" c="dimmed">
          {String(
            userMessage?.detail
              ?? "지역을 조금 넓히거나, 테마 또는 기간을 바꿔 새 run을 만들어 주세요."
          )}
        </Text>
        {suggestions.length > 0 ? (
          <Stack gap={4}>
            <Text size="sm" fw={700}>다시 요청해볼 수 있는 방향</Text>
            {suggestions.map((suggestion) => (
              <Text key={suggestion} size="sm" c="blue.7">
                {suggestion}
              </Text>
            ))}
          </Stack>
        ) : null}
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

function EnrichmentOverview({
  result,
  enrichment,
}: {
  result: WorkflowResult;
  enrichment: WorkflowEnrichmentSummary | null;
}) {
  const latest = enrichment?.latest ?? null;
  const coverage = result.data_coverage;
  const hasCoverage = Object.keys(coverage).length > 0;
  const callRows = enrichmentCallRows(latest, result.enrichment_plan);
  const unresolved = result.unresolved_gaps;
  const gapReasoning = String(recordOrNull(result.data_gap_report)?.reasoning_summary ?? "");
  const routingReasoning = String(recordOrNull(result.enrichment_plan)?.routing_reasoning ?? "");
  const highlights = arrayOfRecords(result.ui_highlights);
  const coverageCards = [
    ["상세정보", coverage.detail_info_coverage, "장소 설명과 기본 상세가 충분한지"],
    ["이미지", coverage.image_coverage, "상품 카드에 쓸 이미지 후보가 있는지"],
    ["운영시간", coverage.operating_hours_coverage, "방문 가능 시간 정보를 확인했는지"],
    ["요금", coverage.price_or_fee_coverage, "요금/입장료를 단정할 수 있는지"],
    ["예약정보", coverage.booking_info_coverage, "예약/문의 조건을 확인했는지"],
  ] as const;
  if (!latest && !hasCoverage && unresolved.length === 0 && highlights.length === 0) return null;

  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      <Paper withBorder p="md">
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text fw={700} size="sm">데이터 커버리지</Text>
              <Text size="sm" c="dimmed">
                수집된 근거에서 상품화에 필요한 상세정보 공백을 요약합니다.
              </Text>
            </div>
            <Badge variant="light" color={sourceConfidenceColor(result.source_confidence)}>
              신뢰도 {Math.round((result.source_confidence || 0) * 100)}%
            </Badge>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
            {coverageCards.map(([label, value, description]) => (
              <CoverageMetric
                key={label}
                label={label}
                value={value}
                description={description}
              />
            ))}
            <Paper withBorder p="sm">
              <Group justify="space-between" align="flex-start" gap="xs">
                <div>
                  <Text c="dimmed" size="xs">운영자 확인</Text>
                  <Text fw={700}>{unresolved.length}</Text>
                </div>
                <Badge size="xs" variant="light" color={unresolved.length > 0 ? "yellow" : "green"}>
                  {unresolved.length > 0 ? "확인 필요" : "추가 확인 없음"}
                </Badge>
              </Group>
              <Text size="xs" c="dimmed" mt={4}>상품에 단정해서 쓰면 안 되는 정보 공백입니다.</Text>
            </Paper>
          </SimpleGrid>
          {unresolved.length > 0 ? (
            <UnresolvedGapSummary gaps={unresolved} />
          ) : (
            <Text size="sm" c="dimmed">현재 Product/QA로 전달할 차단 수준의 미해결 공백은 없습니다.</Text>
          )}
          {gapReasoning ? (
            <>
              <Divider />
              <div>
                <Text fw={600} size="sm">판단 근거</Text>
                <Text size="sm" c="dimmed">{gapReasoning}</Text>
              </div>
            </>
          ) : null}
        </Stack>
      </Paper>

      <Paper withBorder p="md">
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text fw={700} size="sm">추천 보강 호출</Text>
              <Text size="sm" c="dimmed">
                부족한 정보에 대해 실제 실행했거나 보류한 보강 호출입니다.
              </Text>
            </div>
            {latest ? (
              <Badge variant="light" color={latest.status === "completed" ? "green" : "yellow"}>
                {enrichmentStatusLabel(latest.status)}
              </Badge>
            ) : null}
          </Group>
          {callRows.length === 0 ? (
            <Alert color="gray">추가 보강 호출이 필요하지 않았습니다.</Alert>
          ) : (
            <ScrollArea>
              <Table verticalSpacing="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>처리 상태</Table.Th>
                    <Table.Th>데이터 종류</Table.Th>
                    <Table.Th>처리 내용</Table.Th>
                    <Table.Th>이유와 활용</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {callRows.slice(0, 8).map((row) => (
                    <Table.Tr key={row.id}>
                      <Table.Td>
                        <Badge variant="light" color={callStatusColor(row.status)}>
                          {callStatusLabel(row)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{sourceFamilyLabel(row.source_family)}</Table.Td>
                      <Table.Td>{toolLabel(row.tool_name)}</Table.Td>
                      <Table.Td>
                        <Text size="sm" lineClamp={2}>{humanReadableCallReason(row)}</Text>
                        <Text size="xs" c="dimmed" lineClamp={1}>{callBusinessValue(row)}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          )}
          {routingReasoning ? (
            <>
              <Divider />
              <div>
                <Text fw={600} size="sm">호출 선택 기준</Text>
                <Text size="sm" c="dimmed">{routingReasoning}</Text>
              </div>
            </>
          ) : null}
        </Stack>
      </Paper>
      {highlights.length > 0 ? (
        <Paper withBorder p="md">
          <Stack gap="sm">
            <div>
              <Text fw={700} size="sm">상품화 판단 메모</Text>
              <Text size="sm" c="dimmed">
                보강된 근거가 Product/Marketing/QA에서 어떻게 쓰여야 하는지 요약합니다.
              </Text>
            </div>
            {highlights.slice(0, 4).map((highlight, index) => (
              <Alert
                key={`${String(highlight.title ?? "highlight")}-${index}`}
                color={highlightSeverityColor(highlight.severity)}
              >
                <Text fw={600} size="sm">{String(highlight.title ?? "확인 항목")}</Text>
                <Text size="sm">{String(highlight.body ?? "")}</Text>
              </Alert>
            ))}
          </Stack>
        </Paper>
      ) : null}
    </SimpleGrid>
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
  const latestRevision = childRuns.length > 0 ? childRuns[childRuns.length - 1] : null;
  const currentRunId = latestRevision?.id ?? (parentRun ? parentRun.id : run.id);
  const historyRuns = [
    ...[...childRuns].reverse(),
    ...(parentRun ? [parentRun] : []),
  ].filter((item) => item.id !== run.id);

  return (
    <Stack gap={4} mt={6}>
      <Group gap="xs">
        <Badge variant={run.revision_number > 0 ? "light" : "outline"} color="opsBlue">
          {run.revision_number > 0 ? `Rev ${run.revision_number}` : "Original"}
        </Badge>
        {run.revision_mode ? (
          <Badge variant="light" color="gray">
            {revisionModeLabel[run.revision_mode] ?? run.revision_mode}
          </Badge>
        ) : null}
      </Group>
      {historyRuns.length > 0 ? (
        <Group gap="xs">
          <Text size="xs" c="dimmed">History</Text>
          {historyRuns.map((historyRun) => (
            <Button
              key={historyRun.id}
              size="compact-xs"
              variant="subtle"
              onClick={() => onSelectRun?.(historyRun.id)}
            >
              {historyRun.revision_number > 0 ? `Rev ${historyRun.revision_number}` : "Original"}
            </Button>
          ))}
        </Group>
      ) : null}
    </Stack>
  );
}

function RequestPromptPanel({
  run,
  originalRun,
}: {
  run: WorkflowRun;
  originalRun: WorkflowRun;
}) {
  const prompt = (originalRun.input.message || run.input.message || "").trim();
  if (!prompt) return null;
  const isRevision = run.id !== originalRun.id;

  return (
    <div className={classes.requestPrompt}>
      <Group gap="xs" justify="space-between" align="center">
        <Text fw={700} size="sm">최초 요청 문장</Text>
        {isRevision ? (
          <Badge size="sm" variant="light" color="gray">
            원본 Run 기준
          </Badge>
        ) : null}
      </Group>
      <Text size="sm" className={classes.requestPromptText}>
        {prompt}
      </Text>
    </div>
  );
}

function UserWorkflowProgress({
  steps,
  run,
  result,
}: {
  steps: AgentStep[];
  run: WorkflowRun;
  result: WorkflowResult | null;
}) {
  const stages = userWorkflowStages(steps, run, result);
  return (
    <Stack gap={6} mt={6}>
      {stages.map((stage) => (
        <Group key={stage.key} gap="xs" align="center" wrap="nowrap">
          <StageIndicator status={stage.status} />
          <Text size="sm" fw={stage.status === "running" ? 650 : 500}>
            {stage.label}
          </Text>
          <Badge size="xs" color={userStageColor(stage.status)} variant="light">
            {userStageStatusLabel(stage.status)}
          </Badge>
          <Text size="sm" c="dimmed" lineClamp={1}>
            {stage.description}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

function userWorkflowStages(
  steps: AgentStep[],
  run: WorkflowRun,
  result: WorkflowResult | null,
) {
  const stageGroups = [
    {
      key: "request",
      label: "요청 확인",
      description: "요청 범위와 상품 개수를 확인합니다.",
      stepTypes: ["preflight_validation", "planner", "revision_context"],
    },
    {
      key: "geo",
      label: "지역 해석",
      description: "자연어 요청에서 국내 지역 범위를 정합니다.",
      stepTypes: ["geo_resolution"],
    },
    {
      key: "data",
      label: "관광 데이터 확인",
      description: "확정된 지역의 기본 관광 데이터를 확인합니다.",
      stepTypes: ["baseline_data_collection"],
    },
    {
      key: "enrichment",
      label: "보강 정보 확인",
      description: "상세 정보, 이미지, 운영 확인 항목을 정리합니다.",
      stepTypes: [
        "data_gap_profile",
        "api_capability_routing",
        "tourapi_detail_planning",
        "visual_data_planning",
        "route_signal_planning",
        "theme_data_planning",
        "data_enrichment",
        "evidence_fusion",
        "research",
      ],
    },
    {
      key: "draft",
      label: "상품 초안 생성",
      description: "상품안과 마케팅 문구를 생성합니다.",
      stepTypes: ["product_generation", "marketing_generation", "revision_patch"],
    },
    {
      key: "qa",
      label: "검수 및 승인",
      description: "QA 검수 후 사람 검토 단계로 넘깁니다.",
      stepTypes: ["qa_review", "human_approval"],
    },
  ];

  return stageGroups.map((stage) => {
    const matched = steps.filter((step) => stage.stepTypes.includes(step.step_type));
    let status = aggregateUserStageStatus(matched, run, result, stage.key);
    if (run.status === "failed" && stage.key === "qa" && result?.products.length === 0) {
      status = "pending";
    }
    return { ...stage, status };
  });
}

function aggregateUserStageStatus(
  steps: AgentStep[],
  run: WorkflowRun,
  result: WorkflowResult | null,
  key: string,
) {
  if (steps.some((step) => step.status === "running")) return "running";
  if (steps.some((step) => step.status === "failed")) return "failed";
  if (steps.some((step) => step.status === "succeeded")) return "succeeded";
  if (key === "request") return "succeeded";
  if (key === "qa" && result && result.products.length > 0 && run.status !== "running") {
    return "succeeded";
  }
  return "pending";
}

function userStageStatusLabel(status: string) {
  return {
    pending: "대기",
    running: "진행 중",
    succeeded: "완료",
    failed: "확인 필요",
  }[status] ?? status;
}

function userStageColor(status: string) {
  return {
    pending: "gray",
    running: "blue",
    succeeded: "green",
    failed: "red",
  }[status] ?? "gray";
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

function DeveloperDebugPanel({
  run,
  result,
  steps,
  toolCalls,
  llmCalls,
  approvals,
  enrichment,
}: {
  run: WorkflowRun;
  result: WorkflowResult;
  steps: AgentStep[];
  toolCalls: ToolCall[];
  llmCalls: LLMCall[];
  approvals: Approval[];
  enrichment: WorkflowEnrichmentSummary | null;
}) {
  return (
    <Stack gap="md">
      <Alert color="gray">
        <Text fw={700}>Developer debug</Text>
        <Text size="sm">
          이 영역은 내부 agent step, tool call, LLM call, Raw JSON을 확인하기 위한 개발자용 정보입니다.
          사용자 검토 흐름은 Result Review와 Evidence + QA 탭을 기준으로 확인하세요.
        </Text>
      </Alert>
      <RetrievalDiagnosticsPanel diagnostics={result.retrieval_diagnostics} />
      <Accordion variant="contained" multiple defaultValue={["logs"]}>
        <Accordion.Item value="progress">
          <Accordion.Control>Detailed agent progress</Accordion.Control>
          <Accordion.Panel>
            <WorkflowProgress steps={steps} />
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="logs">
          <Accordion.Control>Run logs, tool calls, LLM calls</Accordion.Control>
          <Accordion.Panel>
            <RunLogs
              run={run}
              steps={steps}
              toolCalls={toolCalls}
              llmCalls={llmCalls}
              agentExecution={result.agent_execution}
            />
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="json">
          <Accordion.Control>Raw JSON</Accordion.Control>
          <Accordion.Panel>
            <Code block className={classes.jsonBlock}>
              {JSON.stringify(
                runDebugPayload({ run, result, steps, enrichment, toolCalls, llmCalls, approvals }),
                null,
                2
              )}
            </Code>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

function RetrievalDiagnosticsPanel({ diagnostics }: { diagnostics?: Record<string, unknown> }) {
  const record = recordOrNull(diagnostics);
  if (!record || Object.keys(record).length === 0) return null;
  const vectorSearch = recordOrNull(record.vector_search);
  const retrievedReasons = Array.isArray(record.retrieved_document_reasons) ? record.retrieved_document_reasons : [];
  const rows = [
    ["TourAPI raw collected", record.tourapi_raw_collected_count],
    ["Geo-filtered items", record.geo_filtered_item_count],
    ["Source documents upserted", record.source_document_upsert_count],
    ["Indexed documents", record.indexed_document_count],
    ["Vector search results", record.vector_search_result_count],
    ["Post geo-filter results", record.post_geo_filter_result_count],
    ["RAG query", vectorSearch?.query],
    ["RAG filter result count", vectorSearch?.result_count],
    ["Fallback applied", vectorSearch?.fallback_applied],
    ["Scope expansion applied", vectorSearch?.scope_expansion_applied],
    ["Reason", record.reason],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  return (
    <Paper withBorder p="sm">
      <Stack gap="xs">
        <Text fw={700} size="sm">Retrieval diagnostics</Text>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
          {rows.map(([label, value]) => (
            <div key={String(label)}>
              <Text size="xs" c="dimmed">{String(label)}</Text>
              <Text size="sm" fw={600}>{String(value)}</Text>
            </div>
          ))}
        </SimpleGrid>
        {vectorSearch ? (
          <Accordion variant="separated">
            <Accordion.Item value="rag-filters">
              <Accordion.Control>RAG query/filter details</Accordion.Control>
              <Accordion.Panel>
                <Code block>
                  {JSON.stringify(
                    {
                      filters: vectorSearch.filters,
                      matching_signal_summary: vectorSearch.matching_signal_summary,
                    },
                    null,
                    2
                  )}
                </Code>
              </Accordion.Panel>
            </Accordion.Item>
            {retrievedReasons.length > 0 ? (
              <Accordion.Item value="rag-reasons">
                <Accordion.Control>Returned document matching signals</Accordion.Control>
                <Accordion.Panel>
                  <Code block>{JSON.stringify(retrievedReasons, null, 2)}</Code>
                </Accordion.Panel>
              </Accordion.Item>
            ) : null}
          </Accordion>
        ) : null}
      </Stack>
    </Paper>
  );
}

function runDebugPayload({
  run,
  result,
  steps,
  enrichment,
  toolCalls,
  llmCalls,
  approvals,
}: {
  run: WorkflowRun;
  result: WorkflowResult;
  steps: AgentStep[];
  enrichment: WorkflowEnrichmentSummary | null;
  toolCalls: ToolCall[];
  llmCalls: LLMCall[];
  approvals: Approval[];
}) {
  return {
    run,
    result,
    revision: {
      ...(result.revision ?? {}),
      parent_run_id: run.parent_run_id,
      revision_number: run.revision_number,
      revision_mode: run.revision_mode,
    },
    steps,
    enrichment,
    toolCalls,
    llmCalls,
    approvals,
  };
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
  const isUnsupportedMultiRegion = scope.mode === "unsupported_multi_region"
    || scope.resolution_strategy === "unsupported_multi_region";
  const unsupportedLocations = Array.isArray(scope.unsupported_locations)
    ? scope.unsupported_locations.map(String).filter(Boolean)
    : [];
  const statusLabel = isUnsupported
    ? "지원 범위 안내"
    : isUnsupportedMultiRegion
      ? "단일 지역 필요"
    : needsClarification
      ? "확인 필요"
      : scope.allow_nationwide === true
        ? "전국"
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
          <Alert color="yellow" title={isUnsupportedMultiRegion ? "단일 지역만 지원합니다" : "지역을 하나로 좁혀 주세요"}>
            <Stack gap="xs">
              <Text size="sm">
                {isUnsupportedMultiRegion
                  ? "지역 이동형 코스나 복수 지역 동시 기획은 아직 지원하지 않습니다. 아래 후보 중 하나만 포함해 다시 요청해 주세요."
                  : "요청 문장만으로는 어느 지역인지 확정하기 어렵습니다. 아래 후보 중 원하는 지역명을 포함해 다시 요청해 주세요."}
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

function isInsufficientSourceDataResult(result: WorkflowResult) {
  return result.status === "insufficient_source_data" || result.reason === "insufficient_source_data";
}

function geoScopeLabel(scope: Record<string, unknown>) {
  if (scope.status === "unsupported" || scope.mode === "unsupported_region") return "지원 범위 밖";
  if (scope.mode === "unsupported_multi_region" || scope.resolution_strategy === "unsupported_multi_region") {
    return "단일 지역만 지원합니다";
  }
  if (scope.allow_nationwide === true) return "전국";
  if (scope.needs_clarification === true) return "지역을 더 구체적으로 입력해 주세요";
  const locations = arrayOfRecords(scope.locations);
  const names = locations.map((location) => String(location.name ?? "").trim()).filter(Boolean);
  return names.length > 0 ? names.join(", ") : "-";
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
    primary: "",
    comparison: "비교: ",
    nearby_anchor: "주변: ",
  }[role] ?? "";
}

type EnrichmentCallRow = {
  id: string;
  status: string;
  source_family: string;
  tool_name: string;
  reason: string;
  skip_reason?: string;
};

function enrichmentCallRows(
  latest: EnrichmentRun | null,
  resultPlan: Record<string, unknown>,
): EnrichmentCallRow[] {
  if (latest?.tool_calls?.length) {
    return latest.tool_calls.map((call) => {
      const summary = recordOrNull(call.response_summary);
      const error = recordOrNull(call.error);
      return {
        id: call.id,
        status: call.status,
        source_family: call.source_family,
        tool_name: call.tool_name,
        reason:
          String(summary?.reason ?? "") ||
          String(summary?.detail ?? "") ||
          String(error?.message ?? "") ||
          String(summary?.display_name ?? "") ||
          "선택된 보강 계획에 따라 처리했습니다.",
        skip_reason: String(summary?.skip_reason ?? ""),
      };
    });
  }

  const plan = latest?.plan ?? resultPlan;
  const planned = arrayOfRecords(plan.planned_calls).map((call, index) => ({
    id: String(call.id ?? `planned-${index}`),
    status: "planned",
    source_family: String(call.source_family ?? ""),
    tool_name: String(call.tool_name ?? ""),
    reason: String(call.reason ?? "보강 후보로 계획되었습니다."),
    skip_reason: String(call.skip_reason ?? ""),
  }));
  const skipped = arrayOfRecords(plan.skipped_calls).map((call, index) => ({
    id: String(call.id ?? `skipped-${index}`),
    status: "skipped",
    source_family: String(call.source_family ?? ""),
    tool_name: String(call.tool_name ?? ""),
    reason: String(call.reason ?? "") || skipReasonLabel(call.skip_reason),
    skip_reason: String(call.skip_reason ?? ""),
  }));
  return [...planned, ...skipped];
}

function gapTypeCounts(gaps: Array<Record<string, unknown>>): Array<[string, number]> {
  const counts = new Map<string, number>();
  gaps.forEach((gap) => {
    const type = String(gap.gap_type ?? "unknown");
    counts.set(type, (counts.get(type) ?? 0) + 1);
  });
  return Array.from(counts.entries());
}

function formatCoveragePercent(value: unknown) {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${Math.round(numeric * 100)}%`;
}

function coverageNumeric(value: unknown) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function coverageStatus(value: unknown) {
  const numeric = coverageNumeric(value);
  if (numeric === null) return { label: "정보 없음", color: "gray" };
  if (numeric >= 0.75) return { label: "충분", color: "green" };
  if (numeric >= 0.35) return { label: "일부 부족", color: "yellow" };
  return { label: "부족", color: "red" };
}

function CoverageMetric({
  label,
  value,
  description,
}: {
  label: string;
  value: unknown;
  description: string;
}) {
  const status = coverageStatus(value);
  return (
    <Paper withBorder p="sm">
      <Group justify="space-between" align="flex-start" gap="xs">
        <div>
          <Text c="dimmed" size="xs">{label}</Text>
          <Text fw={700}>{formatCoveragePercent(value)}</Text>
        </div>
        <Badge size="xs" variant="light" color={status.color}>
          {status.label}
        </Badge>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>{description}</Text>
    </Paper>
  );
}

function UnresolvedGapSummary({ gaps }: { gaps: Array<Record<string, unknown>> }) {
  const visible = gaps.slice(0, 4);
  return (
    <Stack gap="xs">
      <Group gap="xs">
        {gapTypeCounts(gaps).map(([type, count]) => (
          <Badge key={type} variant="light" color="yellow">
            {gapTypeLabel(type)} {count}
          </Badge>
        ))}
      </Group>
      {visible.map((gap, index) => (
        <Alert key={`${String(gap.gap_type ?? "gap")}-${index}`} color="yellow">
          <Text fw={600} size="sm">{gapTypeLabel(String(gap.gap_type ?? "unknown"))}</Text>
          <Text size="sm">
            {String(gap.reason ?? gap.description ?? "운영자가 확인해야 하는 정보 공백입니다.")}
          </Text>
        </Alert>
      ))}
    </Stack>
  );
}

function sourceConfidenceColor(value: number) {
  if (value >= 0.75) return "green";
  if (value >= 0.5) return "yellow";
  return "red";
}

function enrichmentStatusLabel(value: string) {
  return {
    completed: "완료",
    completed_with_errors: "일부 실패",
    running: "진행 중",
    planned: "계획됨",
    failed: "실패",
  }[value] ?? value;
}

function callStatusLabel(row: EnrichmentCallRow) {
  const value = row.status;
  const skipReason = row.skip_reason || row.reason;
  if (value === "skipped" && String(skipReason).includes("feature_flag_disabled")) {
    return "비활성";
  }
  if (value === "skipped" && String(skipReason).includes("future_provider_not_implemented")) {
    return "향후 연결 예정";
  }
  if (value === "skipped" && row.source_family !== "kto_tourapi_kor") {
    return "향후 연결 예정";
  }
  if (value === "skipped") return "보류됨";
  return {
    planned: "보류됨",
    running: "진행 중",
    succeeded: "호출됨",
    completed: "호출됨",
    failed: "실패함",
  }[value] ?? value;
}

function callStatusColor(value: string) {
  return {
    planned: "blue",
    running: "blue",
    succeeded: "green",
    completed: "green",
    skipped: "gray",
    failed: "red",
  }[value] ?? "gray";
}

function humanReadableCallReason(row: EnrichmentCallRow) {
  if (row.status === "skipped") {
    return skipReasonLabel(row.skip_reason || row.reason) || row.reason;
  }
  if (row.status === "failed") {
    return row.reason || "호출 중 오류가 발생했습니다. Developer 탭에서 상세 로그를 확인하세요.";
  }
  return row.reason || "부족한 정보를 보강하기 위해 호출했습니다.";
}

function callBusinessValue(row: EnrichmentCallRow) {
  if (row.source_family === "kto_tourapi_kor") {
    return "상세 설명, 이미지 후보, 운영 확인 항목을 상품화 판단에 연결합니다.";
  }
  if (row.source_family === "kto_photo_contest" || row.source_family === "kto_tourism_photo") {
    return "상품 카드와 홍보 소재에 쓸 시각 자료 후보입니다.";
  }
  if (
    row.source_family === "kto_durunubi" ||
    row.source_family === "kto_related_places" ||
    row.source_family === "kto_tourism_bigdata" ||
    row.source_family === "kto_crowding_forecast" ||
    row.source_family === "kto_regional_tourism_demand"
  ) {
    return "동선, 연관 장소, 수요/혼잡 판단에 쓰일 데이터입니다.";
  }
  if (row.source_family === "kto_medical") {
    return "의료관광은 feature flag가 켜진 경우에만 검토합니다.";
  }
  return "테마형 상품 구성에 쓸 수 있는 보강 데이터입니다.";
}

function highlightSeverityColor(value: unknown) {
  return {
    success: "green",
    warning: "yellow",
    info: "blue",
    error: "red",
  }[String(value ?? "info")] ?? "blue";
}

function sourceFamilyLabel(value: string) {
  return {
    kto_tourapi_kor: "TourAPI 국문",
    kto_photo_contest: "관광공모전 사진",
    kto_tourism_photo: "관광사진",
    kto_durunubi: "두루누비",
    kto_related_places: "연관 관광지",
    kto_tourism_bigdata: "관광 빅데이터",
    kto_crowding_forecast: "혼잡도 예측",
    kto_regional_tourism_demand: "지역 관광수요",
    kto_wellness: "웰니스",
    kto_pet: "반려동물",
    kto_audio: "오디오 관광",
    kto_eco: "생태관광",
    kto_medical: "의료관광",
  }[value] ?? (value || "-");
}

function toolLabel(value: string) {
  return {
    kto_tour_detail_enrichment: "상세/이미지 보강",
    kto_tourism_photo_search: "관광사진 후보",
    kto_photo_contest_award_list: "공모전 사진 후보",
    kto_related_places_area: "주변 관광지",
    kto_related_places_keyword: "연관 관광지",
    kto_durunubi_course_list: "코스/동선",
    kto_tourism_bigdata_metco_visitors: "광역 방문자 신호",
    kto_tourism_bigdata_locgo_visitors: "시군구 방문자 신호",
    kto_attraction_crowding_forecast: "혼잡도 예측",
    kto_regional_tourism_demand_area: "지역 수요 신호",
    kto_regional_tourism_service_demand: "관광서비스 수요",
    kto_regional_culture_resource_demand: "문화자원 수요",
    kto_pet_area_search: "반려동물 테마",
    kto_pet_keyword_search: "반려동물 테마",
    kto_pet_detail_pet: "반려동물 조건",
    kto_wellness_keyword_search: "웰니스 테마",
    kto_audio_keyword_search: "오디오 해설",
    kto_audio_story_search: "오디오 스토리",
    kto_audio_theme_search: "오디오 테마",
    kto_eco_tourism_search: "생태관광",
    kto_eco_area_search: "생태관광",
    kto_medical_keyword_search: "의료관광",
  }[value] ?? (value || "-");
}

function gapTypeLabel(value: string) {
  return {
    missing_detail_info: "상세정보",
    missing_image_asset: "이미지",
    missing_operating_hours: "운영시간",
    missing_price_or_fee: "요금",
    missing_booking_info: "예약정보",
    missing_related_places: "연관 장소",
    missing_route_context: "동선",
    missing_theme_specific_data: "테마 데이터",
    missing_pet_policy: "반려동물 조건",
    missing_wellness_attributes: "웰니스 속성",
    missing_medical_context: "의료관광 맥락",
    missing_story_asset: "해설/스토리",
    missing_sustainability_context: "생태/지속가능성",
    missing_demand_signal: "수요 신호",
    missing_crowding_signal: "혼잡 신호",
    missing_regional_demand_signal: "지역 수요",
    missing_visual_reference: "시각 참고",
    missing_multilingual_story: "다국어 해설",
  }[value] ?? value;
}

function skipReasonLabel(value: unknown) {
  return {
    future_provider_not_implemented: "향후 연결 예정인 source라 이번 run에서는 실제 호출하지 않았습니다.",
    feature_flag_disabled: "기능 플래그가 꺼져 있어 호출하지 않았습니다.",
    max_call_budget_exceeded: "이번 run의 보강 호출 예산을 넘어 보류했습니다.",
  }[String(value ?? "")] ?? "이번 run에서는 호출하지 않았습니다.";
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
    theme: "테마 근거",
    route: "동선 후보",
    signal: "보조 신호",
  }[rawType] ?? (rawType ? rawType : "-");
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function avoidRulesForQaReview(run: WorkflowRun | null, result: WorkflowResult | null): string[] {
  const revision = result ? recordOrNull(result.revision) : null;
  const qaSettings = recordOrNull(revision?.qa_settings);
  const revisionAvoid = stringListFromUnknown(qaSettings?.avoid);
  if (revisionAvoid.length > 0) return revisionAvoid;

  const inputAvoid = stringListFromUnknown((run?.input as unknown as Record<string, unknown> | undefined)?.avoid);
  if (inputAvoid.length > 0) return inputAvoid;

  const normalizedAvoid = stringListFromUnknown(result?.normalized_request?.avoid);
  if (normalizedAvoid.length > 0) return normalizedAvoid;

  return [];
}

function stringListFromUnknown(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) {
    return [value.trim()];
  }
  return [];
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
  evidenceDocuments,
  posters,
  posterOptions,
  onCreatePoster,
  onDeletePoster,
  deletingPosterIds,
  onPreviewPoster,
  onPreviewEvidenceImage,
}: {
  product: ProductIdea;
  marketing: MarketingAsset | null;
  evidenceDocuments: EvidenceDocument[];
  posters: PosterAsset[];
  posterOptions: PosterOptions | null;
  onCreatePoster: () => void;
  onDeletePoster: (poster: PosterAsset) => void;
  deletingPosterIds: string[];
  onPreviewPoster: (poster: PosterAsset) => void;
  onPreviewEvidenceImage: (candidate: EvidenceImageCandidate) => void;
}) {
  const needsReview = stringListFromUnknown(product.needs_review);
  const claimLimits = stringListFromUnknown(product.claim_limits);
  const coverageNotes = stringListFromUnknown(product.coverage_notes);
  const evidenceSummary =
    typeof product.evidence_summary === "string" && product.evidence_summary.trim()
      ? product.evidence_summary.trim()
      : "";
  const marketingClaimLimits = stringListFromUnknown(marketing?.claim_limits);
  const evidenceDisclaimer =
    typeof marketing?.evidence_disclaimer === "string" ? marketing.evidence_disclaimer : "";
  const sourceIds = stringListFromUnknown(product.source_ids);
  const visualCandidates = productVisualCandidates(product, evidenceDocuments);
  const maxPostersPerProduct = posterOptions?.max_posters_per_product ?? 3;
  const countedPosterCount = posters.filter((item) => isCountedPosterStatus(item.status)).length;
  const atPosterLimit = countedPosterCount >= maxPostersPerProduct;
  const activePosterCount = posters.filter((item) => isActivePosterStatus(item.status)).length;
  const displayedVisualCandidates = visualCandidates.slice(0, 4);

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <div style={{ flex: 1, minWidth: 0 }}>
          <Title order={4}>{product.title}</Title>
          <Text size="sm" c="dimmed">{product.one_liner}</Text>
        </div>
        <Button
          size="sm"
          variant="light"
          leftSection={<IconPhotoPlus size={16} />}
          onClick={onCreatePoster}
          disabled={atPosterLimit}
          style={{ flexShrink: 0 }}
        >
          포스터 만들기
        </Button>
      </Group>
      <Group gap="xs">
        {product.core_value.map((value) => (
          <Badge key={value} variant="light">{value}</Badge>
        ))}
      </Group>
      <Alert color={activePosterCount > 0 ? "blue" : "gray"} variant="light">
        <Text size="sm">
          이 상품의 포스터 이미지는 최대 {maxPostersPerProduct}개까지 저장됩니다. 현재 {countedPosterCount}개를 사용 중입니다.
          {activePosterCount > 0 ? " 생성 중인 포스터가 있습니다." : ""}
        </Text>
      </Alert>
      {posters.length > 0 ? (
        <Paper withBorder p="sm">
          <Stack gap="sm">
            <Group justify="space-between">
              <Text fw={700} size="sm">저장된 포스터</Text>
              <Badge variant="light" color="opsBlue">{countedPosterCount} / {maxPostersPerProduct}</Badge>
            </Group>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              {posters.map((item) => (
                <PosterDraftCard
                  key={item.id}
                  poster={item}
                  styleLabel={posterStyleLabel(item.style_preset, posterOptions)}
                  deleting={deletingPosterIds.includes(item.id)}
                  onDelete={() => onDeletePoster(item)}
                  onPreview={() => onPreviewPoster(item)}
                />
              ))}
            </SimpleGrid>
          </Stack>
        </Paper>
      ) : null}
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Metric label="Target" value={product.target_customer} />
        <Metric label="Duration" value={product.estimated_duration} />
        <Metric label="Difficulty" value={product.operation_difficulty} />
      </SimpleGrid>

      <Paper withBorder p="sm">
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start">
            <div>
              <Text fw={700} size="sm">근거 기반 상태</Text>
              <Text size="sm" c="dimmed">
                Result Review에서는 상품별 핵심 근거 상태만 요약합니다. 상세 근거와 리스크는 Evidence + QA에서 확인하세요.
              </Text>
            </div>
            <Group gap="xs">
              <Badge variant="light" color="opsBlue">근거 {sourceIds.length}개</Badge>
              <Badge variant="light" color={needsReview.length > 0 ? "yellow" : "green"}>
                확인 필요 {needsReview.length}개
              </Badge>
              <Badge variant="light" color={claimLimits.length > 0 ? "gray" : "green"}>
                claim 제한 {claimLimits.length}개
              </Badge>
            </Group>
          </Group>

          {evidenceSummary ? <Text size="sm">{evidenceSummary}</Text> : null}

          {visualCandidates.length > 0 ? (
            <Stack gap="xs">
              <Text size="xs" c="dimmed">
                이미지 후보 {visualCandidates.length}개 중 상품 근거와 직접 연결된 후보를 먼저 표시합니다.
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                {displayedVisualCandidates.map((candidate) => (
                  <Paper key={candidate.image_url} withBorder p="xs">
                    <Group align="flex-start" wrap="nowrap">
                      <button
                        type="button"
                        className={classes.evidenceImageButton}
                        onClick={() => onPreviewEvidenceImage(candidate)}
                        aria-label={`${candidate.title || product.title} 이미지 크게 보기`}
                      >
                        <Image
                          src={candidate.thumbnail_url || candidate.image_url}
                          alt={candidate.title || product.title}
                          w={96}
                          h={72}
                          fit="cover"
                          radius="sm"
                        />
                      </button>
                      <Stack gap={4}>
                        <Text size="xs" fw={700} lineClamp={1}>
                          {candidate.title || "이미지 후보"}
                        </Text>
                        <Text size="xs" c="dimmed" lineClamp={2}>
                          게시 확정 이미지가 아니라 상품 검토용 후보입니다.
                        </Text>
                        <Group gap={6}>
                          <Badge size="xs" variant="light" color="yellow">
                            사용권 확인 필요
                          </Badge>
                          <Tooltip label="원본 이미지 열기">
                            <ActionIcon
                              component="a"
                              href={candidate.image_url}
                              target="_blank"
                              rel="noreferrer"
                              size="xs"
                              variant="subtle"
                              aria-label={`${candidate.title || product.title} 원본 이미지 열기`}
                            >
                              <IconArrowUpRight size={14} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Stack>
                    </Group>
                  </Paper>
                ))}
              </SimpleGrid>
              {visualCandidates.length > displayedVisualCandidates.length ? (
                <Text size="xs" c="dimmed">
                  나머지 {visualCandidates.length - displayedVisualCandidates.length}개 후보는 Evidence + QA에서 확인하세요.
                </Text>
              ) : null}
            </Stack>
          ) : null}

          <SimpleGrid cols={{ base: 1, md: 3 }}>
            <EvidenceStateList title="확인 필요" items={needsReview} emptyText="별도 확인 항목 없음" />
            <EvidenceStateList
              title="Claim 제한"
              items={[...claimLimits, ...marketingClaimLimits]}
              emptyText="추가 제한 없음"
            />
            <EvidenceStateList title="Coverage note" items={coverageNotes} emptyText="추가 커버리지 메모 없음" />
          </SimpleGrid>

          {evidenceDisclaimer ? (
            <Alert color="gray" variant="light">
              <Text size="sm">{evidenceDisclaimer}</Text>
            </Alert>
          ) : null}
        </Stack>
      </Paper>

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

function PosterDraftCard({
  poster,
  styleLabel,
  deleting,
  onDelete,
  onPreview,
}: {
  poster: PosterAsset;
  styleLabel: string;
  deleting: boolean;
  onDelete: () => void;
  onPreview: () => void;
}) {
  const imageSrc = posterImageSrc(poster);
  const includedSections = poster.included_sections
    .map((section) => POSTER_SECTION_LABELS[section] ?? section)
    .join(", ");

  return (
    <Paper withBorder p="xs" className={classes.posterDraftCard}>
      <Stack gap="xs">
        <div className={classes.posterDraftFrame}>
          {poster.status === "succeeded" && imageSrc ? (
            <button
              type="button"
              className={classes.posterImageButton}
              onClick={onPreview}
              aria-label={`${poster.product_title} 포스터 크게 보기`}
            >
              <Image src={imageSrc} alt={poster.product_title} w="100%" h="100%" fit="cover" />
            </button>
          ) : poster.status === "failed" ? (
            <Stack h="100%" align="center" justify="center" p="sm">
              <Badge color="red" variant="light">failed</Badge>
              <Text size="xs" ta="center" c="dimmed" lineClamp={4}>
                {poster.error?.message ?? "포스터 생성 실패"}
              </Text>
            </Stack>
          ) : (
            <Stack h="100%" align="center" justify="center">
              <Loader size="sm" />
              <Text size="xs" c="dimmed">생성 중</Text>
            </Stack>
          )}
        </div>
        <Group gap={6}>
          {poster.status === "failed" ? <Badge size="xs" variant="light" color="red">failed</Badge> : null}
          <Badge size="xs" variant="light" color="gray">{styleLabel}</Badge>
        </Group>
        <Text size="xs" c="dimmed" lineClamp={2}>
          옵션: {includedSections || "선택 없음"}
          {poster.input_images.length > 0 ? ` · 참조 이미지 ${poster.input_images.length}개` : ""}
        </Text>
        <Text size="xs" c="dimmed">{formatKstDateTime(poster.created_at)}</Text>
        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            component="a"
            href={posterDownloadUrl(poster.id)}
            leftSection={<IconDownload size={14} />}
            disabled={poster.status !== "succeeded"}
          >
            다운로드
          </Button>
          <Tooltip label={isActivePosterStatus(poster.status) ? "생성 중인 포스터는 완료 후 삭제할 수 있습니다." : "삭제"}>
            <ActionIcon
              size="sm"
              variant="light"
              color="red"
              aria-label="포스터 삭제"
              loading={deleting}
              disabled={isActivePosterStatus(poster.status)}
              onClick={onDelete}
            >
              <IconTrash size={14} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Stack>
    </Paper>
  );
}

function PosterSectionOption({
  section,
  checked,
  expanded,
  preview,
  disabled,
  onToggleChecked,
  onToggleExpanded,
}: {
  section: PosterIncludedSection;
  checked: boolean;
  expanded: boolean;
  preview: string;
  disabled: boolean;
  onToggleChecked: (checked: boolean) => void;
  onToggleExpanded: () => void;
}) {
  return (
    <Paper withBorder p="xs" className={classes.posterSectionOption}>
      <Group align="flex-start" wrap="nowrap" gap="xs">
        <Checkbox
          checked={checked}
          onChange={(event) => onToggleChecked(event.currentTarget.checked)}
          disabled={disabled}
          aria-label={POSTER_SECTION_LABELS[section]}
        />
        <Stack gap={3} className={classes.posterSectionOptionBody}>
          <Group justify="space-between" wrap="nowrap" gap="xs">
            <Text size="sm" fw={600}>{POSTER_SECTION_LABELS[section]}</Text>
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              onClick={onToggleExpanded}
              aria-label={expanded ? "내용 접기" : "내용 펼치기"}
            >
              {expanded ? <IconChevronUp size={15} /> : <IconChevronDown size={15} />}
            </ActionIcon>
          </Group>
          <Text
            size="xs"
            c="dimmed"
            className={
              expanded
                ? classes.posterSectionPreviewExpanded
                : `${classes.posterSectionPreviewText} ${classes.posterSectionPreviewCollapsed}`
            }
          >
            {preview}
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}

function ZoomImage({
  src,
  alt,
  zoomed,
  onToggleZoom,
}: {
  src: string;
  alt: string;
  zoomed: boolean;
  onToggleZoom: () => void;
}) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragStartRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const draggedRef = useRef(false);

  useEffect(() => {
    setOffset({ x: 0, y: 0 });
    dragStartRef.current = null;
    draggedRef.current = false;
  }, [src, zoomed]);

  function handleClick() {
    if (draggedRef.current) {
      draggedRef.current = false;
      return;
    }
    if (zoomed) {
      setOffset({ x: 0, y: 0 });
    }
    onToggleZoom();
  }

  function handlePointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!zoomed) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
    };
    draggedRef.current = false;
  }

  function handlePointerMove(event: PointerEvent<HTMLButtonElement>) {
    if (!zoomed || !dragStartRef.current) return;
    event.preventDefault();
    const dx = event.clientX - dragStartRef.current.x;
    const dy = event.clientY - dragStartRef.current.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      draggedRef.current = true;
    }
    setOffset({
      x: dragStartRef.current.offsetX + dx,
      y: dragStartRef.current.offsetY + dy,
    });
  }

  function handlePointerEnd(event: PointerEvent<HTMLButtonElement>) {
    if (!dragStartRef.current) return;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released by the browser.
    }
    dragStartRef.current = null;
  }

  const transform = zoomed ? `translate3d(${offset.x}px, ${offset.y}px, 0) scale(1.5)` : undefined;

  return (
    <div className={classes.zoomPreviewFrame} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`${classes.zoomPreviewButton} ${zoomed ? classes.zoomed : ""}`}
        style={{ transform }}
        onClick={handleClick}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
        aria-label={zoomed ? "이미지 축소" : "이미지 확대"}
      >
        <img src={src} alt={alt} className={classes.zoomPreviewImage} />
        <span className={classes.zoomIcon}>
          {zoomed ? <IconZoomOut size={22} /> : <IconZoomIn size={22} />}
        </span>
      </button>
    </div>
  );
}

const POSTER_STYLE_LABEL_FALLBACK: Record<string, string> = {
  editorial_travel: "프리미엄 여행 매거진",
  night_city: "야간 도시 시네마틱",
  minimal_event: "미니멀 홍보 포스터",
};

function posterStyleLabel(styleId: string, options: PosterOptions | null) {
  return (
    options?.style_presets.find((preset) => preset.id === styleId)?.label ??
    POSTER_STYLE_LABEL_FALLBACK[styleId] ??
    styleId
  );
}

function posterSectionPreview(
  section: PosterIncludedSection,
  product: ProductIdea | null,
  marketing: MarketingAsset | null
) {
  if (!product) return "상품을 선택하면 이 항목에 들어갈 실제 내용이 표시됩니다.";
  if (section === "product_summary") {
    return [product.title, product.one_liner, product.core_value.join(", ")]
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join(" / ") || "상품 요약 없음";
  }
  if (section === "itinerary") {
    const items = arrayOfRecords(product.itinerary)
      .map((item) => String(item.name || item.title || item.place || item.activity || item.description || "").trim())
      .filter(Boolean);
    return items.join(" → ") || "일정/경험 요소 없음";
  }
  if (section === "marketing_copy") {
    return [marketing?.sales_copy.headline, marketing?.sales_copy.subheadline]
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join(" / ") || "마케팅 문구 없음";
  }
  if (section === "sns_copy") {
    return marketing?.sns_posts[0] || "SNS 문구 없음";
  }
  if (section === "evidence_summary") {
    return product.evidence_summary?.trim() || "근거 요약 없음";
  }
  if (section === "claim_limits") {
    const limits = [
      ...stringListFromUnknown(product.claim_limits),
      ...stringListFromUnknown(product.not_to_claim),
      ...stringListFromUnknown(product.needs_review),
    ];
    return limits.join(" / ") || "제한/주의사항 없음";
  }
  return "선택한 데이터가 포스터 프롬프트에 반영됩니다.";
}

function EvidenceStateList({
  title,
  items,
  emptyText,
}: {
  title: string;
  items: string[];
  emptyText: string;
}) {
  const deduped = Array.from(new Set(items.map((item) => item.trim()).filter(Boolean))).slice(0, 5);
  return (
    <div>
      <Text fw={700} size="xs" c="dimmed">{title}</Text>
      {deduped.length > 0 ? (
        <Stack gap={4} mt={4}>
          {deduped.map((item) => (
            <Text key={item} size="sm">- {item}</Text>
          ))}
        </Stack>
      ) : (
        <Text size="sm" c="dimmed" mt={4}>{emptyText}</Text>
      )}
    </div>
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
            autosize
            minRows={4}
            maxRows={8}
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
            autosize
            minRows={4}
            maxRows={8}
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
                  autosize
                  minRows={7}
                  maxRows={14}
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
            autosize
            minRows={4}
            maxRows={8}
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
                  autosize
                  minRows={6}
                  maxRows={11}
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
            autosize
            minRows={11}
            maxRows={21}
            value={joinLines(marketing.sns_posts)}
            onChange={(event) =>
              onMarketingChange({ sns_posts: splitLines(event.currentTarget.value) })
            }
          />
          <Textarea
            label="Search keywords"
            autosize
            minRows={11}
            maxRows={21}
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
            autosize
            minRows={11}
            maxRows={21}
            value={joinLines(product.assumptions)}
            onChange={(event) => onProductChange({ assumptions: splitLines(event.currentTarget.value) })}
          />
          <Textarea
            label="Do not claim"
            autosize
            minRows={11}
            maxRows={21}
            value={joinLines(product.not_to_claim)}
            onChange={(event) => onProductChange({ not_to_claim: splitLines(event.currentTarget.value) })}
          />
        </SimpleGrid>
      </Tabs.Panel>
    </Tabs>
  );
}

function RevisionExecutionPanel({
  revisionMode,
  revisionComment,
  onCommentChange,
  revisionQaSettings,
  revisionDisabledReason,
}: {
  revisionMode: RevisionMode;
  revisionComment: string;
  onCommentChange: (value: string) => void;
  revisionQaSettings: RevisionQaSettings;
  revisionDisabledReason: string | null;
}) {
  return (
    <Paper withBorder p="md" className={classes.revisionExecutionCard}>
      <Stack gap="md">
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
          onChange={(event) => onCommentChange(event.currentTarget.value)}
        />

        <RevisionQaSettingsPanel settings={revisionQaSettings} />

        <Paper withBorder p="sm" className={classes.revisionRunSummary}>
          <Stack gap="xs">
            <Text fw={700} size="sm">실행 요약</Text>
            <Text size="sm" c="dimmed">
              원본 run은 그대로 두고 새 revision run으로 기록합니다.
            </Text>
            {revisionDisabledReason ? (
              <Text size="sm" c="yellow.9">
                {revisionDisabledReason}
              </Text>
            ) : (
              <ul className={classes.revisionSummaryList}>
                <li>선택한 QA 이슈가 해결됐는지 다시 확인합니다.</li>
                <li>근거 없는 단정, 과장 표현, 출처 연결 오류를 확인합니다.</li>
                <li>Avoid 조건과 사용자 요청 제한이 지켜졌는지 봅니다.</li>
              </ul>
            )}
          </Stack>
        </Paper>
      </Stack>
    </Paper>
  );
}

function RevisionQaSettingsPanel({
  settings,
}: {
  settings: RevisionQaSettings;
}) {
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <div>
          <Text fw={700}>Run settings</Text>
        </div>
        <SimpleGrid cols={{ base: 1, md: 3 }}>
          <RevisionSettingValue label="Period" value={settings.period || "-"} />
          <RevisionSettingValue label="Target" value={settings.target_customer || "-"} />
          <RevisionSettingValue label="Product count" value={String(settings.product_count || "-")} />
        </SimpleGrid>
        <div className={classes.revisionSettingTagGrid}>
          <RevisionSettingTags label="Preferences" values={settings.preferences} />
          <RevisionSettingTags label="Avoid" values={settings.avoid} />
        </div>
      </Stack>
    </Paper>
  );
}

function RevisionSettingValue({ label, value }: { label: string; value: string }) {
  return (
    <div className={classes.revisionSettingValue}>
      <Text size="xs" c="dimmed" fw={700}>{label}</Text>
      <Text size="sm">{value}</Text>
    </div>
  );
}

function RevisionSettingTags({ label, values }: { label: string; values: string[] }) {
  const items = values.map((value) => value.trim()).filter(Boolean);
  return (
    <div className={classes.revisionSettingTags}>
      <Text size="xs" c="dimmed" fw={700}>{label}</Text>
      {items.length > 0 ? (
        <Group gap={6} mt={6}>
          {items.map((value) => (
            <Badge key={value} variant="light" color="gray" radius="sm">
              {value}
            </Badge>
          ))}
        </Group>
      ) : (
        <Text size="sm" c="dimmed" mt={4}>없음</Text>
      )}
    </div>
  );
}

function RevisionQaIssuesSelector({
  issues,
  selectedIssueKeys,
  productTitleById,
  onToggleIssue,
  onToggleAll,
}: {
  issues: QAIssue[];
  selectedIssueKeys: string[];
  productTitleById: Map<string, string>;
  onToggleIssue: (issue: QAIssue, index: number) => void;
  onToggleAll: (checked: boolean) => void;
}) {
  const selected = new Set(selectedIssueKeys);
  const selectedCount = issues.filter((issue, index) => selected.has(qaIssueKey(issue, index))).length;
  const allSelected = issues.length > 0 && selectedCount === issues.length;
  const partiallySelected = selectedCount > 0 && selectedCount < issues.length;

  return (
    <Paper withBorder p="sm" className={classes.selectedQaIssuesPanel}>
      <Stack gap="xs" className={classes.selectedQaIssuesContent}>
        <Group justify="space-between" align="flex-start" gap="xs">
          <div>
            <Text fw={700} size="sm">QA 이슈 선택</Text>
            <Text size="xs" c="dimmed">
              이 창에서도 재검수하거나 AI가 반영할 이슈를 추가하거나 해제할 수 있습니다.
            </Text>
          </div>
          <Checkbox
            checked={allSelected}
            indeterminate={partiallySelected}
            disabled={issues.length === 0}
            label={`${selectedCount}/${issues.length}`}
            onChange={(event) => onToggleAll(event.currentTarget.checked)}
          />
        </Group>

        {issues.length === 0 ? (
          <div className={classes.selectedQaIssuesEmpty}>
            <Text fw={700} size="sm">선택된 QA 이슈가 없습니다.</Text>
            <Text size="sm" c="dimmed">
              Evidence + QA 탭에서 재검수하거나 수정할 이슈를 체크한 뒤 다시 실행하세요.
            </Text>
          </div>
        ) : (
          <div className={classes.selectedQaIssueList} role="list">
            {issues.map((issue, index) => {
              const key = qaIssueKey(issue, index);
              const checked = selected.has(key);
              const titleId = `revision-qa-issue-${index}`;
              return (
                <article
                  key={key}
                  className={classes.selectedQaIssueCard}
                  aria-labelledby={titleId}
                  role="listitem"
                >
                  <Group align="flex-start" gap="xs" wrap="nowrap">
                    <Checkbox
                      checked={checked}
                      onChange={() => onToggleIssue(issue, index)}
                      aria-label={`${issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체"} QA 이슈 선택`}
                    />
                    <div className={classes.selectedQaIssueTitle}>
                      <Group gap={6} align="center" wrap="nowrap">
                        <Text id={titleId} size="sm" fw={700} lineClamp={1}>
                          {issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체"}
                        </Text>
                        <Badge size="xs" variant="light" color={severityColor(issue.severity)}>
                          {formatSeverity(issue.severity)}
                        </Badge>
                      </Group>
                    </div>
                  </Group>
                  <div className={classes.selectedQaIssueFields}>
                    <div>
                      <Text size="xs" fw={700} c="dimmed">메시지</Text>
                      <Text size="sm">{formatQaMessage(issue)}</Text>
                    </div>
                    <div>
                      <Text size="xs" fw={700} c="dimmed">수정 방향</Text>
                      <Text size="sm" c="dimmed">{formatSuggestedFix(issue)}</Text>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Stack>
    </Paper>
  );
}

function RevisionQaIssuesReference({
  issues,
  productTitleById,
}: {
  issues: QAIssue[];
  productTitleById: Map<string, string>;
}) {
  return (
    <Paper withBorder p="sm" className={`${classes.selectedQaIssuesPanel} ${classes.revisionQaReferencePanel}`}>
      <Stack gap="xs" className={classes.selectedQaIssuesContent}>
        <div>
          <Text fw={700} size="sm">QA 이슈 전체</Text>
          <Text size="xs" c="dimmed">
            아래 이슈들을 참고해서 오른쪽에서 필요한 내용을 한 번에 수정하세요.
          </Text>
        </div>
        {issues.length === 0 ? (
          <div className={classes.selectedQaIssuesEmpty}>
            <Text size="sm" c="dimmed">표시할 QA 이슈가 없습니다.</Text>
          </div>
        ) : (
          <div className={classes.selectedQaIssueList} role="list">
            {issues.map((issue, index) => (
              <article
                key={qaIssueKey(issue, index)}
                className={classes.selectedQaIssueCard}
                role="listitem"
              >
                <Group gap={6} align="center" wrap="nowrap">
                  <Text size="sm" fw={700} lineClamp={1}>
                    {issue.product_id ? productTitleById.get(issue.product_id) ?? issue.product_id : "전체"}
                  </Text>
                  <Badge size="xs" variant="light" color={severityColor(issue.severity)}>
                    {formatSeverity(issue.severity)}
                  </Badge>
                  <Badge size="xs" variant="light" color="gray">
                    {formatIssueType(issue.type)}
                  </Badge>
                </Group>
                <div className={classes.selectedQaIssueFields}>
                  <div>
                    <Text size="xs" fw={700} c="dimmed">메시지</Text>
                    <Text size="sm">{formatQaMessage(issue)}</Text>
                  </div>
                  <div>
                    <Text size="xs" fw={700} c="dimmed">수정 방향</Text>
                    <Text size="sm" c="dimmed">{formatSuggestedFix(issue)}</Text>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
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
              <Table.Th>근거</Table.Th>
              <Table.Th>출처</Table.Th>
              <Table.Th>지역</Table.Th>
              <Table.Th>유형</Table.Th>
              <Table.Th>보강</Table.Th>
              <Table.Th>이미지</Table.Th>
              <Table.Th>확인</Table.Th>
              <Table.Th>요약</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => (
              <Table.Tr key={row.doc_id}>
                <Table.Td>
                  <Text fw={600} size="sm">{row.title}</Text>
                  <Text size="xs" c="dimmed" lineClamp={1}>{evidenceSourceDescription(row)}</Text>
                </Table.Td>
                <Table.Td>{evidenceSourceLabel(row)}</Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={1}>{evidenceRegionLabel(row)}</Text>
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
                <Table.Td>
                  <EvidenceReviewBadge row={row} />
                </Table.Td>
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
  relevance_label?: string;
  relevance_rank?: number;
};

function EvidenceDetailBadge({ row }: { row: EvidenceDocument }) {
  const hasDetail = row.metadata.detail_common_available === true || row.metadata.detail_common_available === "true";
  const detailInfoCount = numberFromMetadata(row.metadata.detail_info_count);
  if (!hasDetail && detailInfoCount === 0) {
    return <Badge variant="light" color="gray">기본 정보</Badge>;
  }
  return (
    <Badge variant="light" color="green">
      상세 보강{detailInfoCount > 0 ? ` ${detailInfoCount}` : ""}
    </Badge>
  );
}

function EvidenceReviewBadge({ row }: { row: EvidenceDocument }) {
  const flags = stringListFromMetadata(row.metadata.data_quality_flags);
  const needsReview = flags.length > 0 || String(row.metadata.needs_review ?? "") === "true";
  if (!needsReview) {
    return <Badge variant="light" color="green">확인 완료</Badge>;
  }
  return <Badge variant="light" color="yellow">확인 필요</Badge>;
}

function evidenceSourceLabel(row: EvidenceDocument) {
  const family = String(row.metadata.source_family ?? "");
  if (family) return sourceFamilyLabel(family);
  const source = String(row.metadata.source ?? "").toLowerCase();
  if (source === "tourapi") return "TourAPI";
  return source || "저장 근거";
}

function evidenceSourceDescription(row: EvidenceDocument) {
  const trust = row.metadata.trust_level;
  const retrievedAt = row.metadata.retrieved_at ? formatKstDateTime(String(row.metadata.retrieved_at)) : "";
  const trustNumber = Number(trust);
  const trustLabel = Number.isFinite(trustNumber)
    ? `신뢰도 ${Math.round(trustNumber * 100)}%`
    : "신뢰도 확인 필요";
  return [trustLabel, retrievedAt ? `수집 ${retrievedAt}` : ""].filter(Boolean).join(" · ");
}

function evidenceRegionLabel(row: EvidenceDocument) {
  const explicit = String(
    row.metadata.region_name ??
      row.metadata.location_name ??
      row.metadata.area_name ??
      row.metadata.ldong_name ??
      ""
  ).trim();
  if (explicit) return explicit;
  const address = String(row.metadata.address ?? "").trim();
  if (address) {
    return address.split(/\s+/).slice(0, 2).join(" ");
  }
  return "-";
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
          <Badge variant="light">{evidenceSourceLabel(row)}</Badge>
          <Badge variant="light">{evidenceRegionLabel(row)}</Badge>
          <Badge variant="light">상세 항목 {detailInfoCount}</Badge>
          <Badge variant="light">이미지 후보 {imageCount}</Badge>
        </Group>
        {flags.length > 0 ? (
          <Text size="xs" c="dimmed">운영자 확인: {flags.map(gapTypeLabel).join(", ")}</Text>
        ) : null}
        {notes.length > 0 ? (
          <Text size="xs" c="dimmed">{notes.join(" ")}</Text>
        ) : null}
      </Stack>
    </Paper>
  );
}

function EvidenceImageCandidates({
  row,
  onPreviewImage,
}: {
  row: EvidenceDocument;
  onPreviewImage: (candidate: EvidenceImageCandidate) => void;
}) {
  const candidates = evidenceImageCandidates(row);
  if (candidates.length === 0) return null;

  return (
    <Stack gap="xs">
      <Text fw={700} size="sm">이미지 후보</Text>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {candidates.slice(0, 4).map((candidate) => (
          <Paper key={candidate.image_url} withBorder p="xs">
            <Stack gap={6}>
              <button
                type="button"
                className={classes.evidenceImageButton}
                onClick={() => onPreviewImage(candidate)}
                aria-label={`${candidate.title || row.title} 이미지 크게 보기`}
              >
                <Image
                  src={candidate.thumbnail_url || candidate.image_url}
                  alt={candidate.title || row.title}
                  h={120}
                  fit="cover"
                  radius="sm"
                />
              </button>
              <Text size="xs" fw={600} lineClamp={1}>
                {candidate.title || row.title}
              </Text>
              <Group gap={6}>
                <Badge size="xs" variant="light" color="yellow">
                  {candidate.usage_status || "candidate"}
                </Badge>
                {evidenceImageSourceLabel(candidate.source) ? (
                  <Badge size="xs" variant="light">
                    {evidenceImageSourceLabel(candidate.source)}
                  </Badge>
                ) : null}
                <Tooltip label="원본 이미지 열기">
                  <ActionIcon
                    component="a"
                    href={candidate.image_url}
                    target="_blank"
                    rel="noreferrer"
                    size="xs"
                    variant="subtle"
                    aria-label={`${candidate.title || row.title} 원본 이미지 열기`}
                  >
                    <IconArrowUpRight size={14} />
                  </ActionIcon>
                </Tooltip>
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

function evidenceImageSourceLabel(source: string | undefined) {
  const normalized = String(source || "").trim();
  if (!normalized) return null;
  const technicalSources = new Set([
    "detailImage",
    "detailImage2",
    "detail_common",
    "detailCommon",
    "detailCommon2",
    "detail_image",
    "detail_image2",
  ]);
  if (technicalSources.has(normalized)) return null;
  return sourceFamilyLabel(normalized);
}

function productVisualCandidates(
  product: ProductIdea,
  evidenceDocuments: EvidenceDocument[],
): EvidenceImageCandidate[] {
  const productSourceIds = stringListFromUnknown(product.source_ids);
  const sourceIds = new Set(productSourceIds);
  const sourceOrder = new Map(productSourceIds.map((sourceId, index) => [sourceId, index]));
  if (sourceIds.size === 0) return [];
  const linkedContentIds = new Set(
    evidenceDocuments
      .filter((document) => sourceIds.has(document.doc_id))
      .map((document) => String(document.metadata.content_id ?? "").trim())
      .filter(Boolean)
  );
  const candidates: EvidenceImageCandidate[] = [];
  evidenceDocuments.forEach((document, index) => {
    const contentId = String(document.metadata.content_id ?? "").trim();
    const isDirect = sourceIds.has(document.doc_id);
    const isLinked = Boolean(contentId && linkedContentIds.has(contentId));
    if (!isDirect && !isLinked) return;
    const relevanceLabel = isDirect ? "상품 직접 근거" : "같은 장소 후보";
    const relevanceRank = isDirect ? sourceOrder.get(document.doc_id) ?? index : 100 + index;
    evidenceImageCandidates(document).forEach((candidate) => {
      candidates.push({
        ...candidate,
        source: candidate.source ? sourceFamilyLabel(candidate.source) : "이미지 후보",
        relevance_label: relevanceLabel,
        relevance_rank: relevanceRank,
      });
    });
  });
  const seen = new Set<string>();
  return candidates
    .filter((candidate) => {
      if (seen.has(candidate.image_url)) return false;
      seen.add(candidate.image_url);
      return true;
    })
    .sort(
      (a, b) =>
        (a.relevance_rank ?? 99) - (b.relevance_rank ?? 99) ||
        String(a.title ?? "").localeCompare(String(b.title ?? ""))
    );
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

function ReviewQaSummary({
  report,
  avoidRules,
}: {
  report: QAReport;
  avoidRules: string[];
}) {
  return (
    <Paper withBorder p="md" mb="md">
      <Group justify="space-between" align="flex-start">
        <div>
          <Text fw={700}>QA 요약</Text>
          <Text size="sm" c="dimmed">{report.summary}</Text>
          {avoidRules.length > 0 ? (
            <Group gap="xs" mt={6}>
              <Text size="xs" c="dimmed" fw={600}>Avoid</Text>
              {avoidRules.map((rule) => (
                <Badge key={rule} size="sm" variant="light" color="gray">
                  {rule}
                </Badge>
              ))}
            </Group>
          ) : null}
        </div>
        <Group gap="xs">
          <Badge color={report.overall_status === "pass" ? "green" : "yellow"} variant="light">
            {report.overall_status}
          </Badge>
          {report.issues.length > 0 ? (
            <Badge color="yellow" variant="light">
              확인 {report.issues.length}
            </Badge>
          ) : null}
        </Group>
      </Group>
    </Paper>
  );
}

type QaDiffSummary = {
  qa_recheck_mode?: string | null;
  counts: Record<string, number>;
};

const qaDiffLabels: Record<string, string> = {
  resolved: "해결됨",
  still_open: "계속 확인 필요",
};

function qaDiffSummaryFromRevision(revision: Record<string, unknown> | undefined): QaDiffSummary | null {
  const rawSummary = revision?.qa_diff_summary;
  if (!rawSummary || typeof rawSummary !== "object" || Array.isArray(rawSummary)) return null;
  const summary = rawSummary as Record<string, unknown>;
  const rawCounts = summary.counts;
  if (!rawCounts || typeof rawCounts !== "object" || Array.isArray(rawCounts)) return null;
  const counts: Record<string, number> = {};
  Object.entries(rawCounts as Record<string, unknown>).forEach(([key, value]) => {
    if (typeof value === "number" && value > 0) counts[key] = value;
  });
  if (Object.keys(counts).length === 0) return null;
  return {
    qa_recheck_mode: typeof summary.qa_recheck_mode === "string" ? summary.qa_recheck_mode : null,
    counts,
  };
}

function QaDiffSummaryPanel({ summary }: { summary: QaDiffSummary }) {
  const modeLabel =
    summary.qa_recheck_mode === "ai_partial_rewrite_recheck"
      ? "AI 수정 후 재검수"
      : summary.qa_recheck_mode === "qa_only_recheck"
      ? "QA 재검수"
      : "재검수";
  return (
    <Paper withBorder p="sm" mt="sm">
      <Group justify="space-between" align="center">
        <Text size="sm" fw={600}>{modeLabel} 결과 변화</Text>
        <Group gap="xs">
          {Object.entries(qaDiffLabels).map(([key, label]) =>
            summary.counts[key] ? (
              <Badge key={key} variant="light" color={key === "new_issue" ? "yellow" : "gray"}>
                {label} {summary.counts[key]}
              </Badge>
            ) : null
          )}
        </Group>
      </Group>
    </Paper>
  );
}

function QASection({
  report,
  products,
  avoidRules,
  qaDiffSummary,
  selectedIssueKeys,
  onToggleIssue,
  onToggleAll,
  onDeleteSelected,
  deleteLoading,
}: {
  report: QAReport;
  products: ProductIdea[];
  avoidRules: string[];
  qaDiffSummary: QaDiffSummary | null;
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
          <Group gap="xs" mt={6}>
            <Text size="xs" c="dimmed" fw={600}>Avoid</Text>
            {avoidRules.length > 0 ? (
              avoidRules.map((rule) => (
                <Badge key={rule} size="sm" variant="light" color="gray">
                  {rule}
                </Badge>
              ))
            ) : (
              <Text size="xs" c="dimmed">설정된 Avoid 기준 없음</Text>
            )}
          </Group>
        </div>
        <Badge color={report.overall_status === "pass" ? "green" : "yellow"} variant="light">
          {report.overall_status}
        </Badge>
      </Group>
      {qaDiffSummary ? <QaDiffSummaryPanel summary={qaDiffSummary} /> : null}
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
            ? "QA 요약에는 이슈가 있다고 표시되었지만 상세 이슈가 없습니다. Developer 탭에서 qa_report를 확인하세요."
            : "검수에서 차단 수준의 이슈가 없습니다."}
        </Alert>
      ) : (
        <ScrollArea>
          <Table verticalSpacing="sm" className={classes.qaTable}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th className={classes.qaSelectColumn}></Table.Th>
                <Table.Th className={classes.qaProductColumn}>상품</Table.Th>
                <Table.Th className={classes.qaSeverityColumn}>중요도</Table.Th>
                <Table.Th className={classes.qaTypeColumn}>분류</Table.Th>
                <Table.Th className={classes.qaMessageColumn}>문제 내용</Table.Th>
                <Table.Th className={classes.qaFixColumn}>수정 제안</Table.Th>
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
