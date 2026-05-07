import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Drawer,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconEye, IconPlayerPlay } from "@tabler/icons-react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow } from "@xyflow/react";
import type { Edge, Node, ReactFlowInstance } from "@xyflow/react";
import { createWorkflowRun, listWorkflowRuns, listWorkflowTemplates, WorkflowRun } from "../services/runsApi";
import { StatusBadge } from "../components/StatusBadge";
import { RunDetail } from "./RunDetail";
import { formatKstDateTime } from "../utils/datetime";
import classes from "./Dashboard.module.css";

function WorkflowNodeLabel({
  title,
  stepType,
  description,
}: {
  title: string;
  stepType: string;
  description: string;
}) {
  return (
    <div className={classes.workflowNodeLabel}>
      <Text fw={700} size="xs">{title}</Text>
      <Text ff="monospace" size="10px" c="dimmed">{stepType}</Text>
      <Text size="10px" c="dimmed" lh={1.2}>{description}</Text>
    </div>
  );
}

function WorkflowDecisionNode() {
  return (
    <div className={classes.workflowDecisionLabel}>
      <Handle className={classes.workflowHiddenHandle} id="in-left" type="target" position={Position.Left} />
      <Handle className={classes.workflowHiddenHandle} id="resolved-right" type="source" position={Position.Right} />
      <Handle className={classes.workflowHiddenHandle} id="exit-top" type="source" position={Position.Top} />
      <div className={classes.workflowDecisionContent}>
        <Text fw={800} size="xs">지역 확정?</Text>
        <Text ff="monospace" size="9px" c="dimmed">geo_gate</Text>
        <Text size="9px" c="dimmed" lh={1.15}>진행 / 종료 판단</Text>
      </div>
    </div>
  );
}

const workflowNodeTypes = {
  decision: WorkflowDecisionNode,
};

const normalNodeStyle = {
  background: "var(--mantine-color-blue-0)",
  border: "1px solid var(--mantine-color-blue-5)",
  boxShadow: "0 1px 3px rgba(34, 139, 230, 0.18)",
};

const revisionNodeStyle = {
  background: "var(--mantine-color-grape-0)",
  border: "1px solid var(--mantine-color-grape-5)",
  boxShadow: "0 1px 3px rgba(174, 62, 201, 0.18)",
};

const resolvedNodeStyle = {
  background: "var(--mantine-color-teal-0)",
  border: "1px solid var(--mantine-color-teal-5)",
  boxShadow: "0 1px 3px rgba(18, 184, 134, 0.16)",
};

const geoExitNodeStyle = {
  background: "var(--mantine-color-red-0)",
  border: "1px solid var(--mantine-color-red-5)",
  boxShadow: "0 1px 3px rgba(250, 82, 82, 0.16)",
  width: 158,
};

const decisionNodeStyle = {
  background: "transparent",
  border: "0",
  boxShadow: "none",
  padding: 0,
  width: 158,
  height: 88,
};

const normalEdgeStyle = {
  stroke: "var(--mantine-color-blue-6)",
  strokeWidth: 2,
};

const revisionEdgeStyle = {
  stroke: "var(--mantine-color-grape-6)",
  strokeWidth: 2,
};

const resolvedEdgeStyle = {
  stroke: "var(--mantine-color-teal-6)",
  strokeWidth: 2,
};

const geoExitEdgeStyle = {
  stroke: "var(--mantine-color-red-6)",
  strokeWidth: 2,
  strokeDasharray: "6 4",
};

const workflowGraphBounds = {
  minX: -20,
  minY: -140,
  maxX: 1970,
  maxY: 455,
};

const workflowNodes: Node[] = [
  {
    id: "request",
    position: { x: 0, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="New run" stepType="workflow_created" description="자연어 요청 생성" />,
    },
  },
  {
    id: "planner",
    position: { x: 190, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Planner" stepType="planner" description="요청/기간 정규화" />,
    },
  },
  {
    id: "geo",
    position: { x: 360, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="GeoResolver" stepType="geo_resolution" description="ldong 지역 해석" />,
    },
  },
  {
    id: "geo-decision",
    position: { x: 525, y: 8 },
    type: "decision",
    style: decisionNodeStyle,
    data: {},
  },
  {
    id: "geo-resolved",
    position: { x: 735, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: resolvedNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Geo resolved" stepType="geo_scope_resolved" description="지역 확정 후 계속 진행" />,
    },
  },
  {
    id: "data",
    position: { x: 915, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Data" stepType="data_collection" description="TourAPI ldong 수집" />,
    },
  },
  {
    id: "research",
    position: { x: 1095, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Research" stepType="research" description="RAG 검색/요약" />,
    },
  },
  {
    id: "product",
    position: { x: 1275, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Product" stepType="product_generation" description="상품 초안" />,
    },
  },
  {
    id: "marketing",
    position: { x: 1455, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Marketing" stepType="marketing_generation" description="카피/FAQ/SNS" />,
    },
  },
  {
    id: "qa",
    position: { x: 1635, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="QA" stepType="qa_review" description="리스크 검수" />,
    },
  },
  {
    id: "approval",
    position: { x: 1815, y: 20 },
    type: "output",
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Approval" stepType="human_approval" description="승인 대기" />,
    },
  },
  {
    id: "geo-exit",
    position: { x: 525, y: -115 },
    sourcePosition: Position.Top,
    targetPosition: Position.Bottom,
    style: geoExitNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Geo exit" stepType="geo_scope_exit" description="후보 안내 / 지원 범위 밖" />,
    },
  },
  {
    id: "source-run",
    position: { x: 0, y: 330 },
    type: "input",
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Existing run" stepType="source_final_output" description="원본 결과" />,
    },
  },
  {
    id: "revision-context",
    position: { x: 240, y: 330 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Revision" stepType="revision_context" description="수정 맥락 생성" />,
    },
  },
  {
    id: "revision-patch",
    position: { x: 480, y: 330 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="AI Patch" stepType="revision_patch" description="선택 이슈만 수정" />,
    },
  },
  {
    id: "revision-qa",
    position: { x: 720, y: 330 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="QA" stepType="qa_review" description="재검수" />,
    },
  },
  {
    id: "revision-approval",
    position: { x: 960, y: 330 },
    type: "output",
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Approval" stepType="human_approval" description="새 revision 승인" />,
    },
  },
];

const workflowEdges: Edge[] = [
  ...[
    ["request", "planner"],
    ["planner", "geo"],
    ["geo", "geo-decision"],
    ["geo-resolved", "data"],
    ["data", "research"],
    ["research", "product"],
    ["product", "marketing"],
    ["marketing", "qa"],
    ["qa", "approval"],
  ].map(([source, target]) => ({
    id: `${source}-${target}`,
    source,
    target,
    targetHandle: target === "geo-decision" ? "in-left" : undefined,
    style: normalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  })),
  {
    id: "geo-resolved-edge",
    source: "geo-decision",
    sourceHandle: "resolved-right",
    target: "geo-resolved",
    label: "확정",
    style: resolvedEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-teal-6)" },
  },
  {
    id: "geo-exit-edge",
    source: "geo-decision",
    sourceHandle: "exit-top",
    target: "geo-exit",
    label: "확정 불가 / 해외",
    type: "smoothstep",
    style: geoExitEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-red-6)" },
  },
  {
    id: "geo-exit-retry-edge",
    source: "geo-exit",
    target: "request",
    label: "지역명 보강 후 새 run",
    type: "smoothstep",
    style: { ...geoExitEdgeStyle, strokeDasharray: "2 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-red-6)" },
  },
  {
    id: "source-revision",
    source: "source-run",
    target: "revision-context",
    style: revisionEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
  {
    id: "revision-patch-edge",
    source: "revision-context",
    target: "revision-patch",
    label: "AI 수정",
    style: revisionEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
  {
    id: "revision-qa-edge",
    source: "revision-patch",
    target: "revision-qa",
    style: revisionEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
  {
    id: "manual-qa-edge",
    source: "revision-context",
    target: "revision-qa",
    label: "직접 수정 / QA 재검수",
    style: { ...revisionEdgeStyle, strokeDasharray: "6 4" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
  {
    id: "revision-approval-edge",
    source: "revision-qa",
    target: "revision-approval",
    style: revisionEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
  {
    id: "manual-save-edge",
    source: "revision-context",
    target: "revision-approval",
    label: "저장",
    style: { ...revisionEdgeStyle, strokeDasharray: "2 4" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-grape-6)" },
  },
];

const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);
const PERIOD_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function getRunTitle(run: WorkflowRun) {
  const products = Array.isArray(run.final_output?.products)
    ? (run.final_output.products as Array<{ title?: unknown }>)
    : [];
  const productTitle = products.find((product) => typeof product.title === "string")?.title;
  if (typeof productTitle === "string" && productTitle.trim()) {
    return productTitle;
  }
  return run.input.message || `${run.input.region ?? "Region"} product planning`;
}

function getRunProductCount(run: WorkflowRun) {
  const products = Array.isArray(run.final_output?.products) ? run.final_output.products.length : 0;
  return products > 0 ? products : run.input.product_count;
}

function getRunGeoLabel(run: WorkflowRun) {
  const finalGeoScope = recordOrNull(run.final_output?.geo_scope);
  const normalizedGeoScope = recordOrNull(run.normalized_input?.geo_scope);
  const scope = finalGeoScope ?? normalizedGeoScope;
  if (!scope) {
    return run.input.region || "-";
  }
  if (scope.status === "unsupported" || scope.mode === "unsupported_region") {
    return "지원 불가";
  }
  if (scope.allow_nationwide === true) {
    return "전국";
  }
  if (scope.needs_clarification === true) {
    return "후보 확인";
  }
  const locations = Array.isArray(scope.locations)
    ? (scope.locations as Array<Record<string, unknown>>)
    : [];
  const names = locations
    .map((location) => String(location.name ?? "").trim())
    .filter(Boolean);
  const separator = scope.mode === "route" ? " → " : ", ";
  return names.length > 0 ? names.join(separator) : run.input.region || "-";
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function RunTableRow({
  run,
  selectedRunId,
  indent = false,
  revisionCount = 0,
  isExpanded = false,
  onToggleRevisions,
  onSelectRun,
}: {
  run: WorkflowRun;
  selectedRunId: string | null;
  indent?: boolean;
  revisionCount?: number;
  isExpanded?: boolean;
  onToggleRevisions?: () => void;
  onSelectRun: (runId: string) => void;
}) {
  return (
    <Table.Tr className={indent ? classes.revisionRow : undefined}>
      <Table.Td className={classes.taskCell}>
        <Group gap="xs" wrap="nowrap" className={indent ? classes.revisionTask : undefined}>
          {indent ? <Text className={classes.branchMarker}>↳</Text> : null}
          <Text fw={600} size="sm" lineClamp={1}>
            {getRunTitle(run)}
          </Text>
          {run.revision_number > 0 ? (
            <Badge size="xs" variant="light" color="opsBlue">
              Rev {run.revision_number}
            </Badge>
          ) : null}
        </Group>
        <Text ff="monospace" size="xs" c="dimmed">
          {run.id}
        </Text>
      </Table.Td>
      <Table.Td>
        <StatusBadge status={run.status} />
      </Table.Td>
      <Table.Td>{getRunGeoLabel(run)}</Table.Td>
      <Table.Td>{getRunProductCount(run)}</Table.Td>
      <Table.Td>
        {!indent && revisionCount > 0 ? (
          <Button size="compact-xs" variant="subtle" onClick={onToggleRevisions}>
            {isExpanded ? "Hide" : "Show"} {revisionCount}
          </Button>
        ) : indent ? (
          <Badge size="xs" variant="light" color="gray">
            Revision
          </Badge>
        ) : (
          "-"
        )}
      </Table.Td>
      <Table.Td>{formatKstDateTime(run.created_at)}</Table.Td>
      <Table.Td>
        <Button
          size="xs"
          variant={selectedRunId === run.id ? "light" : "subtle"}
          leftSection={<IconEye size={14} />}
          onClick={() => onSelectRun(run.id)}
        >
          Review
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

export function Dashboard() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [templateCount, setTemplateCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [expandedRootIds, setExpandedRootIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState("runs");
  const [workflowFlow, setWorkflowFlow] = useState<ReactFlowInstance | null>(null);
  const workflowPreviewRef = useRef<HTMLDivElement | null>(null);
  const workflowCenterTimers = useRef<number[]>([]);
  const [opened, { open, close }] = useDisclosure(false);

  const form = useForm({
    initialValues: {
      message: "이번 달 대전에서 외국인 대상 액티비티 상품을 5개 기획해줘",
      period: "2026-05",
      target_customer: "외국인",
      product_count: 5,
      preferences: ["야간 관광", "축제"],
      avoid: ["가격 단정 표현"],
      output_language: "ko" as const,
    },
    validate: {
      period: (value) =>
        PERIOD_PATTERN.test(value)
          ? null
          : "Period must use YYYY-MM, for example 2026-05.",
    },
  });

  async function loadData(options: { silent?: boolean } = {}) {
    try {
      if (!options.silent) {
        setLoading(true);
        setError(null);
      }
      const [nextRuns, templates] = await Promise.all([
        listWorkflowRuns(),
        listWorkflowTemplates(),
      ]);
      setRuns(nextRuns);
      setTemplateCount(templates.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const awaitingApprovalCount = useMemo(
    () => runs.filter((run) => run.status === "awaiting_approval").length,
    [runs]
  );

  const hasActiveRuns = useMemo(
    () => runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status)),
    [runs]
  );

  const selectedRun = useMemo(
    () => runs.find((run) => run.id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  useEffect(() => {
    if (!hasActiveRuns) return;
    const timer = window.setInterval(() => {
      void loadData({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasActiveRuns]);

  function centerWorkflowMap(instance: ReactFlowInstance, duration = 0) {
    const container = workflowPreviewRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    if (rect.width < 50 || rect.height < 50) return;

    const graphWidth = workflowGraphBounds.maxX - workflowGraphBounds.minX;
    const graphHeight = workflowGraphBounds.maxY - workflowGraphBounds.minY;
    const padding = 56;
    const zoom = Math.min(
      (rect.width - padding * 2) / graphWidth,
      (rect.height - padding * 2) / graphHeight,
      0.95,
    );
    const safeZoom = Math.max(0.25, zoom);
    const x = (rect.width - graphWidth * safeZoom) / 2 - workflowGraphBounds.minX * safeZoom;
    const y = (rect.height - graphHeight * safeZoom) / 2 - workflowGraphBounds.minY * safeZoom;
    instance.setViewport({ x, y, zoom: safeZoom }, { duration });
  }

  function scheduleWorkflowCenter(instance: ReactFlowInstance) {
    workflowCenterTimers.current.forEach((timer) => window.clearTimeout(timer));
    workflowCenterTimers.current = [0, 50, 160, 360, 700].map((delay) =>
      window.setTimeout(() => centerWorkflowMap(instance, delay === 0 ? 0 : 180), delay)
    );
  }

  useEffect(() => {
    if (activeTab !== "workflow" || !workflowFlow) return;
    scheduleWorkflowCenter(workflowFlow);
    return () => {
      workflowCenterTimers.current.forEach((timer) => window.clearTimeout(timer));
      workflowCenterTimers.current = [];
    };
  }, [activeTab, workflowFlow]);

  async function handleCreateRun(values: typeof form.values) {
    try {
      setCreating(true);
      setError(null);
      const run = await createWorkflowRun(values);
      notifications.show({
        title: "Workflow run 시작",
        message: "실행 상태는 자동으로 갱신됩니다. 완료되면 승인 대기 상태로 전환됩니다.",
        color: "blue",
      });
      close();
      setSelectedRunId(run.id);
      await loadData({ silent: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      notifications.show({
        title: "Run 생성 실패",
        message,
        color: "red",
      });
      await loadData({ silent: true });
    } finally {
      setCreating(false);
    }
  }

  async function handleRevisionCreated(run: WorkflowRun) {
    if (run.parent_run_id) {
      setExpandedRootIds((current) =>
        current.includes(run.parent_run_id as string)
          ? current
          : [...current, run.parent_run_id as string]
      );
    }
    setSelectedRunId(run.id);
    await loadData({ silent: true });
  }

  function toggleRoot(rootId: string) {
    setExpandedRootIds((current) =>
      current.includes(rootId)
        ? current.filter((item) => item !== rootId)
        : [...current, rootId]
    );
  }

  const rows = runs
    .filter((run) => !run.parent_run_id)
    .map((run) => {
    const revisions = runs
      .filter((item) => item.parent_run_id === run.id)
      .sort((a, b) => (b.revision_number ?? 0) - (a.revision_number ?? 0));
    const isExpanded = expandedRootIds.includes(run.id);
    return (
      <Fragment key={run.id}>
        <RunTableRow
          run={run}
          selectedRunId={selectedRunId}
          revisionCount={revisions.length}
          isExpanded={isExpanded}
          onToggleRevisions={() => toggleRoot(run.id)}
          onSelectRun={setSelectedRunId}
        />
        {isExpanded
          ? revisions.map((revision) => (
              <RunTableRow
                key={revision.id}
                run={revision}
                selectedRunId={selectedRunId}
                indent
                onSelectRun={setSelectedRunId}
              />
            ))
          : null}
      </Fragment>
    );
  });

  return (
    <Stack gap="md">
      <Group className={classes.toolbar} justify="space-between">
        <div>
          <Title order={2}>Dashboard</Title>
          <Text c="dimmed" size="sm">
            공공 관광 데이터를 상품 초안, 근거 문서, QA 검수, 승인 흐름으로 연결합니다.
          </Text>
        </div>
        <Button leftSection={<IconPlayerPlay size={16} />} onClick={open}>
          New run
        </Button>
      </Group>

      <Paper withBorder p="md" className={classes.overviewPanel}>
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700}>PARAVOCA AX Agent Studio</Text>
            <Text c="dimmed" size="sm">
              요청 문장에서 지역 의도를 해석한 뒤 관광 데이터 수집부터 여행 상품 초안, 마케팅 카피, FAQ, 운영 리스크 검수, 검토 승인까지 이어지는 운영 워크플로우입니다.
            </Text>
          </div>
          <Group gap="xs">
            {["Geo", "Data", "RAG", "Draft", "QA", "Approval"].map((step) => (
              <Badge key={step} variant="light" color="opsBlue">
                {step}
              </Badge>
            ))}
          </Group>
        </Group>
      </Paper>

      {error ? (
        <Alert color="red" icon={<IconAlertCircle size={16} />}>
          {error}
        </Alert>
      ) : null}

      {selectedRun && ACTIVE_RUN_STATUSES.has(selectedRun.status) ? (
        <Alert color="blue">
          <Text fw={700}>Workflow is running</Text>
          <Text size="sm">
            {getRunTitle(selectedRun)} is being processed. Status will refresh automatically.
          </Text>
        </Alert>
      ) : null}

      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Paper withBorder p="md">
          <Text c="dimmed" size="sm">Workflow runs</Text>
          <Title order={3}>{loading ? "-" : runs.length}</Title>
        </Paper>
        <Paper withBorder p="md">
          <Text c="dimmed" size="sm">Awaiting approval</Text>
          <Title order={3}>{loading ? "-" : awaitingApprovalCount}</Title>
        </Paper>
        <Paper withBorder p="md">
          <Text c="dimmed" size="sm">Templates</Text>
          <Title order={3}>{loading ? "-" : templateCount}</Title>
        </Paper>
      </SimpleGrid>

      <Tabs value={activeTab} onChange={(value) => setActiveTab(value ?? "runs")}>
        <Tabs.List>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          <Tabs.Tab value="workflow">Workflow preview</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="runs" pt="md">
          <Paper withBorder className={classes.tablePanel}>
            <Table striped highlightOnHover verticalSpacing="sm" className={classes.runsTable}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th className={classes.taskColumn}>Task</Table.Th>
                  <Table.Th className={classes.statusColumn}>Status</Table.Th>
                  <Table.Th className={classes.regionColumn}>Geo</Table.Th>
                  <Table.Th className={classes.productsColumn}>Products</Table.Th>
                  <Table.Th className={classes.revisionsColumn}>Revisions</Table.Th>
                  <Table.Th className={classes.createdColumn}>Created</Table.Th>
                  <Table.Th className={classes.actionColumn}>Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.length > 0 ? rows : (
                  <Table.Tr>
                    <Table.Td colSpan={7}>
                      <Text c="dimmed" ta="center" py="lg">
                        No workflow runs yet.
                      </Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="workflow" pt="md">
          <Stack gap="sm">
            <Paper withBorder p="md">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Text fw={700}>Implemented workflow map</Text>
                  <Text size="sm" c="dimmed">
                    이 preview는 현재 코드에 구현된 agent 실행 순서입니다. Workflow Builder 편집 화면이 아니라,
                    run을 만들었을 때 DB의 `agent_steps.step_type`으로 기록되는 흐름을 요약합니다.
                  </Text>
                </div>
                <Group gap="xs">
                  <Badge variant="light" color="opsBlue">Normal run</Badge>
                  <Badge variant="light" color="teal">Decision gate</Badge>
                  <Badge variant="light" color="teal">Geo resolved</Badge>
                  <Badge variant="light" color="red">Geo exit</Badge>
                  <Badge variant="light" color="grape">Revision run</Badge>
                  <Badge variant="outline" color="gray">dashed = exit path</Badge>
                </Group>
              </Group>
            </Paper>

            <Paper withBorder className={classes.workflowPreview} ref={workflowPreviewRef}>
              {activeTab === "workflow" ? (
                <ReactFlow
                  nodes={workflowNodes}
                  edges={workflowEdges}
                  nodeTypes={workflowNodeTypes}
                  defaultViewport={{ x: 60, y: 48, zoom: 0.7 }}
                  onInit={(instance) => {
                    setWorkflowFlow(instance);
                    scheduleWorkflowCenter(instance);
                  }}
                  minZoom={0.25}
                  maxZoom={1.3}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                >
                  <Background />
                  <Controls showInteractive={false} />
                </ReactFlow>
              ) : null}
            </Paper>

            <SimpleGrid cols={{ base: 1, md: 3 }}>
              <Paper withBorder p="md">
                <Text fw={700} size="sm">Normal run</Text>
                <Text size="sm" c="dimmed">
                  새 요청은 Planner 다음 GeoResolver가 자연어 지역을 분석하고, `지역 확정?` gate에서 계속 진행할지 종료할지 판단한 뒤 TourAPI 수집으로 넘어갑니다.
                </Text>
              </Paper>
              <Paper withBorder p="md">
                <Text fw={700} size="sm">Geo exits</Text>
                <Text size="sm" c="dimmed">
                  `중구`처럼 후보가 여러 개인 요청은 실패 상태로 멈추고 후보를 보여줍니다. 해외 목적지는 PARAVOCA 국내 지원 안내로 종료하며, 사용자는 지역명을 보강해 새 run을 만들 수 있습니다.
                </Text>
              </Paper>
              <Paper withBorder p="md">
                <Text fw={700} size="sm">Revision run</Text>
                <Text size="sm" c="dimmed">
                  기존 run은 덮어쓰지 않습니다. 직접 수정은 QA만 다시 실행하고, AI 수정은 선택한 QA 이슈를 patch한 뒤 QA와 승인을 다시 거칩니다.
                </Text>
              </Paper>
            </SimpleGrid>
          </Stack>
        </Tabs.Panel>
      </Tabs>

      <Drawer
        opened={selectedRunId !== null}
        onClose={() => setSelectedRunId(null)}
        title="Run review"
        position="right"
        size="90%"
        padding="md"
      >
        {selectedRunId ? (
          <RunDetail
            runId={selectedRunId}
            onStatusChanged={loadData}
            onRevisionCreated={handleRevisionCreated}
            relatedRuns={runs}
            onSelectRun={setSelectedRunId}
          />
        ) : null}
      </Drawer>

      <Modal opened={opened} onClose={close} title="Create workflow run" size="lg">
        <form onSubmit={form.onSubmit(handleCreateRun)}>
          <Stack gap="sm">
            <Textarea
              label="Request"
              description="지역은 이 요청 문장에서 우선 해석합니다."
              minRows={3}
              {...form.getInputProps("message")}
            />
            <Group grow>
              <TextInput
                label="Period"
                type="month"
                placeholder="YYYY-MM"
                {...form.getInputProps("period")}
              />
            </Group>
            <Group grow>
              <TextInput label="Target" {...form.getInputProps("target_customer")} />
              <NumberInput
                label="Product count"
                min={1}
                max={10}
                {...form.getInputProps("product_count")}
              />
            </Group>
            <MultiSelect
              label="Preferences"
              data={["야간 관광", "축제", "전통시장", "해변", "요트", "푸드투어"]}
              searchable
              {...form.getInputProps("preferences")}
            />
            <MultiSelect
              label="Avoid"
              data={["가격 단정 표현", "과장 표현", "출처 없는 주장", "무리한 이동"]}
              searchable
              {...form.getInputProps("avoid")}
            />
            <Group justify="flex-end" mt="md">
              <Button variant="subtle" onClick={close} disabled={creating}>
                Cancel
              </Button>
              <Button type="submit" loading={creating}>Create run</Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
