import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Drawer,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAlertCircle, IconEye, IconPlayerPlay, IconTrash } from "@tabler/icons-react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow } from "@xyflow/react";
import type { Edge, Node, ReactFlowInstance } from "@xyflow/react";
import {
  createWorkflowRun,
  deleteWorkflowRuns,
  listWorkflowRuns,
  listWorkflowTemplates,
  WorkflowRun,
} from "../services/runsApi";
import { ApiError } from "../services/apiClient";
import { StatusBadge } from "../components/StatusBadge";
import { RunDetail } from "./RunDetail";
import { formatKstDateTime } from "../utils/datetime";
import type { AppSection } from "../components/AppShellLayout/AppShellLayout";
import classes from "./Dashboard.module.css";

function WorkflowNodeLabel({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className={classes.workflowNodeLabel}>
      <Text fw={700} size="xs">{title}</Text>
      <Text size="10px" c="dimmed" lh={1.2}>{description}</Text>
    </div>
  );
}

function WorkflowDecisionNode({ data }: { data?: { title?: string; stepType?: string; description?: string } }) {
  return (
    <div className={classes.workflowDecisionLabel}>
      <Handle className={classes.workflowHiddenHandle} id="in-left" type="target" position={Position.Left} />
      <Handle className={classes.workflowHiddenHandle} id="in-top" type="target" position={Position.Top} />
      <Handle className={classes.workflowHiddenHandle} id="resolved-right" type="source" position={Position.Right} />
      <Handle className={classes.workflowHiddenHandle} id="no-right" type="source" position={Position.Right} />
      <Handle className={classes.workflowHiddenHandle} id="yes-bottom" type="source" position={Position.Bottom} />
      <Handle className={classes.workflowHiddenHandle} id="exit-top" type="source" position={Position.Top} />
      <div className={classes.workflowDecisionContent}>
        <Text fw={800} size="xs">{data?.title ?? "지역 확정?"}</Text>
        <Text size="9px" c="dimmed" lh={1.15}>{data?.description ?? "진행 / 종료 판단"}</Text>
      </div>
    </div>
  );
}

function WorkflowActionNode({ data }: { data?: { title?: string; stepType?: string; description?: string } }) {
  return (
    <div className={classes.workflowActionNode}>
      <Handle className={classes.workflowHiddenHandle} id="in-top" type="target" position={Position.Top} />
      <Handle className={classes.workflowHiddenHandle} id="in-left" type="target" position={Position.Left} />
      <Handle className={classes.workflowHiddenHandle} id="out-right" type="source" position={Position.Right} />
      <Text fw={800} size="xs">{data?.title ?? "실행"}</Text>
      <Text size="9px" c="dimmed" lh={1.15}>{data?.description ?? "선택 API 호출"}</Text>
    </div>
  );
}

function WorkflowExitActionNode({ data }: { data?: { title?: string; description?: string } }) {
  return (
    <div className={classes.workflowExitActionNode}>
      <Handle className={classes.workflowHiddenHandle} id="in-bottom" type="target" position={Position.Bottom} />
      <Handle className={classes.workflowHiddenHandle} id="out-top" type="source" position={Position.Top} />
      <Text fw={800} size="xs">{data?.title ?? "종료 안내"}</Text>
      <Text size="9px" c="dimmed" lh={1.15}>{data?.description ?? "후보 안내 후 새 요청"}</Text>
    </div>
  );
}

const workflowNodeTypes = {
  decision: WorkflowDecisionNode,
  action: WorkflowActionNode,
  exitAction: WorkflowExitActionNode,
};

const normalNodeStyle = {
  background: "var(--mantine-color-blue-0)",
  border: "1px solid var(--mantine-color-blue-5)",
  boxShadow: "0 1px 3px rgba(34, 139, 230, 0.18)",
  width: 154,
  height: 64,
  display: "flex",
  alignItems: "center",
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
  width: 154,
  height: 64,
  display: "flex",
  alignItems: "center",
};

const decisionNodeStyle = {
  background: "transparent",
  border: "0",
  boxShadow: "none",
  padding: 0,
  width: 158,
  height: 64,
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

const optionalEdgeStyle = {
  stroke: "var(--mantine-color-blue-6)",
  strokeWidth: 2,
};

const workflowGraphBounds = {
  minX: -430,
  minY: -305,
  maxX: 3240,
  maxY: 600,
};

const workflowNodes: Node[] = [
  {
    id: "request",
    position: { x: -390, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="New run" description="자연어 요청 생성" />,
    },
  },
  {
    id: "preflight",
    position: { x: -200, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Preflight" description="지원 범위와 개수 확인" />,
    },
  },
  {
    id: "preflight-decision",
    position: { x: -35, y: 20 },
    type: "decision",
    style: decisionNodeStyle,
    data: {
      title: "요청 가능?",
      description: "실행 전 범위 검증",
    },
  },
  {
    id: "preflight-exit",
    position: { x: -35, y: -115 },
    type: "exitAction",
    data: {
      title: "요청 수정",
      description: "범위 또는 최대 개수 안내",
    },
  },
  {
    id: "planner",
    position: { x: 190, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Planner" description="요청 조건 정리" />,
    },
  },
  {
    id: "geo",
    position: { x: 360, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="GeoResolver" description="요청 지역 해석" />,
    },
  },
  {
    id: "geo-decision",
    position: { x: 525, y: 20 },
    type: "decision",
    style: decisionNodeStyle,
    data: {
      title: "지역 확정?",
      description: "진행 또는 안내 종료",
    },
  },
  {
    id: "geo-resolved",
    position: { x: 735, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: resolvedNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Geo resolved" description="확정 지역으로 계속 진행" />,
    },
  },
  {
    id: "baseline-data",
    position: { x: 915, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Baseline" description="기본 관광 데이터 수집" />,
    },
  },
  {
    id: "gap-profile",
    position: { x: 1095, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Data Gap" description="부족한 정보 파악" />,
    },
  },
  {
    id: "enrichment-decision",
    position: { x: 1275, y: 20 },
    type: "decision",
    style: decisionNodeStyle,
    data: {
      title: "보강 필요?",
      description: "추가 데이터가 필요한지 판단",
    },
  },
  {
    id: "api-router",
    position: { x: 1405, y: -143 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="API Router" description="필요한 API 묶음 분류" />,
    },
  },
  {
    id: "tourapi-detail-planner",
    position: { x: 1625, y: -270 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Detail Planner" description="상세 정보 보강 계획" />,
    },
  },
  {
    id: "visual-data-planner",
    position: { x: 1625, y: -185 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Visual Planner" description="사진 자료 후보 판단" />,
    },
  },
  {
    id: "route-signal-planner",
    position: { x: 1625, y: -100 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Route Planner" description="동선과 수요 신호 판단" />,
    },
  },
  {
    id: "theme-data-planner",
    position: { x: 1625, y: -15 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Theme Planner" description="테마 데이터 후보 판단" />,
    },
  },
  {
    id: "fusion",
    position: { x: 1835, y: -143 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Evidence Fusion" description="보강 근거 병합" />,
    },
  },
  {
    id: "research",
    position: { x: 2045, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Research" description="근거 검색과 요약" />,
    },
  },
  {
    id: "product",
    position: { x: 2225, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Product" description="상품 초안 작성" />,
    },
  },
  {
    id: "marketing",
    position: { x: 2405, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Marketing" description="상세페이지와 FAQ 작성" />,
    },
  },
  {
    id: "qa",
    position: { x: 2585, y: 20 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="QA" description="표현과 근거 리스크 검수" />,
    },
  },
  {
    id: "approval",
    position: { x: 2765, y: 20 },
    type: "output",
    targetPosition: Position.Left,
    style: normalNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Approval" description="사람 검토 대기" />,
    },
  },
  {
    id: "geo-exit",
    position: { x: 525, y: -115 },
    type: "exitAction",
    data: {
      title: "요청 종료",
      description: "지역 후보 안내 또는 국내 지원 범위 안내",
    },
  },
  {
    id: "source-run",
    position: { x: 0, y: 465 },
    type: "input",
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Existing run" description="원본 결과" />,
    },
  },
  {
    id: "revision-context",
    position: { x: 240, y: 465 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Revision" description="수정 요청 정리" />,
    },
  },
  {
    id: "revision-patch",
    position: { x: 480, y: 465 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="AI Patch" description="선택 이슈만 수정" />,
    },
  },
  {
    id: "revision-qa",
    position: { x: 720, y: 465 },
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="QA" description="수정 결과 재검수" />,
    },
  },
  {
    id: "revision-approval",
    position: { x: 960, y: 465 },
    type: "output",
    style: revisionNodeStyle,
    data: {
      label: <WorkflowNodeLabel title="Approval" description="새 revision 승인" />,
    },
  },
];

const workflowEdges: Edge[] = [
  ...[
    ["request", "preflight"],
    ["preflight", "preflight-decision"],
    ["planner", "geo"],
    ["geo", "geo-decision"],
    ["geo-resolved", "baseline-data"],
    ["baseline-data", "gap-profile"],
    ["research", "product"],
    ["product", "marketing"],
    ["marketing", "qa"],
    ["qa", "approval"],
  ].map(([source, target]) => ({
    id: `${source}-${target}`,
    source,
    target,
    targetHandle: target === "geo-decision" || target === "preflight-decision" ? "in-left" : undefined,
    type: "straight",
    style: normalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  })),
  {
    id: "preflight-pass-edge",
    source: "preflight-decision",
    sourceHandle: "resolved-right",
    target: "planner",
    label: "통과",
    type: "straight",
    style: resolvedEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-teal-6)" },
  },
  {
    id: "preflight-exit-edge",
    source: "preflight-decision",
    sourceHandle: "exit-top",
    target: "preflight-exit",
    targetHandle: "in-bottom",
    label: "범위 밖",
    type: "smoothstep",
    style: geoExitEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-red-6)" },
  },
  {
    id: "preflight-retry-edge",
    source: "preflight-exit",
    sourceHandle: "out-top",
    target: "request",
    label: "요청 수정",
    type: "smoothstep",
    style: { ...geoExitEdgeStyle, strokeDasharray: "2 5" },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-red-6)" },
  },
  {
    id: "gap-profile-enrichment-decision",
    source: "gap-profile",
    target: "enrichment-decision",
    targetHandle: "in-left",
    type: "straight",
    style: normalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  },
  {
    id: "enrichment-needed-router",
    source: "enrichment-decision",
    sourceHandle: "exit-top",
    target: "api-router",
    label: "보강 필요",
    type: "smoothstep",
    style: optionalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  },
  {
    id: "enrichment-not-needed-research",
    source: "enrichment-decision",
    sourceHandle: "yes-bottom",
    target: "research",
    label: "보강 없음",
    type: "smoothstep",
    style: normalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  },
  ...[
    ["api-router", "tourapi-detail-planner"],
    ["api-router", "visual-data-planner"],
    ["api-router", "route-signal-planner"],
    ["api-router", "theme-data-planner"],
  ].map(([source, target]) => ({
    id: `${source}-${target}`,
    source,
    target,
    type: "smoothstep",
    style: optionalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  })),
  ...[
    ["tourapi-detail-planner", "fusion"],
    ["visual-data-planner", "fusion"],
    ["route-signal-planner", "fusion"],
    ["theme-data-planner", "fusion"],
  ].map(([source, target]) => ({
    id: `${source}-${target}`,
    source,
    target,
    type: "smoothstep",
    style: optionalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  })),
  {
    id: "fusion-research",
    source: "fusion",
    target: "research",
    type: "smoothstep",
    style: normalEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-blue-6)" },
  },
  {
    id: "geo-resolved-edge",
    source: "geo-decision",
    sourceHandle: "resolved-right",
    target: "geo-resolved",
    label: "확정",
    type: "straight",
    style: resolvedEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-teal-6)" },
  },
  {
    id: "geo-exit-edge",
    source: "geo-decision",
    sourceHandle: "exit-top",
    target: "geo-exit",
    targetHandle: "in-bottom",
    label: "확정 불가 / 해외",
    type: "smoothstep",
    style: geoExitEdgeStyle,
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--mantine-color-red-6)" },
  },
  {
    id: "geo-exit-retry-edge",
    source: "geo-exit",
    sourceHandle: "out-top",
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
  selectedForDelete,
  indent = false,
  revisionCount = 0,
  isExpanded = false,
  onToggleRevisions,
  onSelectRun,
  onToggleRunSelection,
  canSelectForDelete,
}: {
  run: WorkflowRun;
  selectedRunId: string | null;
  selectedForDelete: boolean;
  indent?: boolean;
  revisionCount?: number;
  isExpanded?: boolean;
  onToggleRevisions?: () => void;
  onSelectRun: (runId: string) => void;
  onToggleRunSelection: (runId: string, checked: boolean) => void;
  canSelectForDelete: boolean;
}) {
  return (
    <Table.Tr className={indent ? classes.revisionRow : undefined}>
      <Table.Td className={classes.selectCell}>
        <Checkbox
          size="xs"
          checked={selectedForDelete}
          disabled={!canSelectForDelete}
          aria-label={`${getRunTitle(run)} 선택`}
          onChange={(event) => onToggleRunSelection(run.id, event.currentTarget.checked)}
        />
      </Table.Td>
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

export function Dashboard({ activeSection }: { activeSection: AppSection }) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [templateCount, setTemplateCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createRunWarning, setCreateRunWarning] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedDeleteRunIds, setSelectedDeleteRunIds] = useState<string[]>([]);
  const [deletingRuns, setDeletingRuns] = useState(false);
  const [expandedRootIds, setExpandedRootIds] = useState<string[]>([]);
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
      message: (value) => (value.trim().length > 0 ? null : "요청 내용을 입력해 주세요."),
      product_count: (value) => (Number(value) <= 5 ? null : "상품은 최대 5개까지 생성할 수 있습니다."),
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

  const revisionsByParentId = useMemo(() => {
    const grouped = new Map<string, WorkflowRun[]>();
    runs.forEach((run) => {
      if (!run.parent_run_id) return;
      const revisions = grouped.get(run.parent_run_id) ?? [];
      revisions.push(run);
      grouped.set(run.parent_run_id, revisions);
    });
    grouped.forEach((revisions) => {
      revisions.sort((a, b) => (b.revision_number ?? 0) - (a.revision_number ?? 0));
    });
    return grouped;
  }, [runs]);

  const runById = useMemo(() => new Map(runs.map((run) => [run.id, run])), [runs]);

  function canSelectRunForDelete(run: WorkflowRun) {
    if (ACTIVE_RUN_STATUSES.has(run.status)) return false;
    if (run.parent_run_id) return true;
    return !(revisionsByParentId.get(run.id) ?? []).some((revision) =>
      ACTIVE_RUN_STATUSES.has(revision.status)
    );
  }

  function deletionGroupIdsForRun(run: WorkflowRun) {
    if (!canSelectRunForDelete(run)) return [];
    if (run.parent_run_id) return [run.id];
    return [
      run.id,
      ...(revisionsByParentId.get(run.id) ?? [])
        .filter((revision) => canSelectRunForDelete(revision))
        .map((revision) => revision.id),
    ];
  }

  const visibleRunIds = useMemo(() => {
    const ids: string[] = [];
    runs
      .filter((run) => !run.parent_run_id)
      .forEach((run) => {
        ids.push(run.id);
        if (!expandedRootIds.includes(run.id)) return;
        (revisionsByParentId.get(run.id) ?? []).forEach((revision) => ids.push(revision.id));
      });
    return ids;
  }, [expandedRootIds, revisionsByParentId, runs]);

  const selectableRunIds = useMemo(
    () =>
      Array.from(
        new Set(
          visibleRunIds.flatMap((runId) => {
            const run = runById.get(runId);
            return run ? deletionGroupIdsForRun(run) : [];
          })
        )
      ),
    [runById, visibleRunIds]
  );

  const selectedDeleteCount = selectedDeleteRunIds.length;
  const allVisibleSelected =
    selectableRunIds.length > 0 && selectableRunIds.every((runId) => selectedDeleteRunIds.includes(runId));
  const someVisibleSelected =
    selectableRunIds.some((runId) => selectedDeleteRunIds.includes(runId)) && !allVisibleSelected;

  useEffect(() => {
    if (!hasActiveRuns) return;
    const timer = window.setInterval(() => {
      void loadData({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasActiveRuns]);

  useEffect(() => {
    const existingRunIds = new Set(runs.map((run) => run.id));
    setSelectedDeleteRunIds((current) => current.filter((runId) => existingRunIds.has(runId)));
  }, [runs]);

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
    if (activeSection !== "workflow" || !workflowFlow) return;
    scheduleWorkflowCenter(workflowFlow);
    return () => {
      workflowCenterTimers.current.forEach((timer) => window.clearTimeout(timer));
      workflowCenterTimers.current = [];
    };
  }, [activeSection, workflowFlow]);

  async function handleCreateRun(values: typeof form.values) {
    try {
      setCreating(true);
      setError(null);
      setCreateRunWarning(null);
      const run = await createWorkflowRun(values);
      notifications.show({
        title: "Workflow run 시작",
        message: "실행 상태는 자동으로 갱신됩니다. 완료되면 승인 대기 상태로 전환됩니다.",
        color: "blue",
      });
      closeCreateRunModal();
      setSelectedRunId(run.id);
      await loadData({ silent: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (err instanceof ApiError && err.code === "PREFLIGHT_VALIDATION_FAILED") {
        setCreateRunWarning(message);
      } else {
        setError(message);
      }
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

  function openCreateRunModal() {
    setCreateRunWarning(null);
    setError(null);
    open();
  }

  function closeCreateRunModal() {
    setCreateRunWarning(null);
    close();
  }

  function toggleRoot(rootId: string) {
    setExpandedRootIds((current) =>
      current.includes(rootId)
        ? current.filter((item) => item !== rootId)
        : [...current, rootId]
    );
  }

  function toggleRunSelection(runId: string, checked: boolean) {
    const run = runById.get(runId);
    const targetIds = run ? deletionGroupIdsForRun(run) : [runId];
    setSelectedDeleteRunIds((current) => {
      if (!checked) {
        const targets = new Set([
          ...targetIds,
          ...(run?.parent_run_id ? [run.parent_run_id] : []),
        ]);
        return current.filter((item) => !targets.has(item));
      }
      return Array.from(new Set([...current, ...targetIds]));
    });
  }

  function toggleSelectAllVisible(checked: boolean) {
    setSelectedDeleteRunIds((current) => {
      const selectable = new Set(selectableRunIds);
      if (!checked) {
        return current.filter((runId) => !selectable.has(runId));
      }
      return Array.from(new Set([...current, ...selectableRunIds]));
    });
  }

  async function deleteSelectedRuns() {
    if (selectedDeleteRunIds.length === 0) return;
    const confirmed = window.confirm(
      `선택한 task ${selectedDeleteRunIds.length}개를 삭제할까요? 원본 run을 삭제하면 연결된 revision도 함께 삭제됩니다.`
    );
    if (!confirmed) return;
    try {
      setDeletingRuns(true);
      const result = await deleteWorkflowRuns({ run_ids: selectedDeleteRunIds });
      const deletedIds = new Set(result.deleted_run_ids);
      setRuns((current) => current.filter((run) => !deletedIds.has(run.id)));
      setSelectedDeleteRunIds([]);
      if (selectedRunId && deletedIds.has(selectedRunId)) {
        setSelectedRunId(null);
      }
      notifications.show({
        color: "green",
        title: "Task deleted",
        message: `${result.deleted_count}개 task를 삭제했습니다.`,
      });
      void loadData({ silent: true });
    } catch (err) {
      notifications.show({
        color: "red",
        title: "삭제 실패",
        message: err instanceof Error ? err.message : "선택한 task를 삭제하지 못했습니다.",
      });
    } finally {
      setDeletingRuns(false);
    }
  }

  const rows = runs
    .filter((run) => !run.parent_run_id)
    .map((run) => {
    const revisions = revisionsByParentId.get(run.id) ?? [];
    const isExpanded = expandedRootIds.includes(run.id);
    return (
      <Fragment key={run.id}>
        <RunTableRow
          run={run}
          selectedRunId={selectedRunId}
          selectedForDelete={selectedDeleteRunIds.includes(run.id)}
          canSelectForDelete={canSelectRunForDelete(run)}
          revisionCount={revisions.length}
          isExpanded={isExpanded}
          onToggleRevisions={() => toggleRoot(run.id)}
          onSelectRun={setSelectedRunId}
          onToggleRunSelection={toggleRunSelection}
        />
        {isExpanded
          ? revisions.map((revision) => (
              <RunTableRow
                key={revision.id}
                run={revision}
                selectedRunId={selectedRunId}
                selectedForDelete={selectedDeleteRunIds.includes(revision.id)}
                canSelectForDelete={canSelectRunForDelete(revision)}
                indent
                onSelectRun={setSelectedRunId}
                onToggleRunSelection={toggleRunSelection}
              />
            ))
          : null}
      </Fragment>
    );
  });

  const sectionCopy: Record<AppSection, { title: string; description: string }> = {
    dashboard: {
      title: "Dashboard",
      description: "공공 관광 데이터를 상품 초안, 근거 문서, QA 검수, 승인 흐름으로 연결합니다.",
    },
    workflow: {
      title: "Workflow Preview",
      description: "현재 코드에 구현된 agent 실행 흐름과 조건부 데이터 보강 경로를 확인합니다.",
    },
    "data-sources": {
      title: "Data Sources",
      description: "KTO/TourAPI와 향후 연결할 데이터 소스 상태를 관리할 화면입니다.",
    },
    evaluation: {
      title: "Evaluation",
      description: "상품 초안과 근거 품질 평가를 모아 볼 화면입니다.",
    },
    costs: {
      title: "Costs",
      description: "LLM 호출 비용과 토큰 사용량을 운영 관점에서 볼 화면입니다.",
    },
    "poster-studio": {
      title: "Poster Studio",
      description: "승인된 상품을 포스터와 홍보 소재로 확장할 화면입니다.",
    },
    settings: {
      title: "Settings",
      description: "Agent, API, workflow 실행 옵션을 관리할 화면입니다.",
    },
  };

  const currentSection = sectionCopy[activeSection];

  const sectionHeader = (
    <Group className={classes.toolbar} justify="space-between">
      <div>
        <Title order={2}>{currentSection.title}</Title>
        <Text c="dimmed" size="sm">
          {currentSection.description}
        </Text>
      </div>
      {activeSection === "dashboard" ? (
        <Button leftSection={<IconPlayerPlay size={16} />} onClick={openCreateRunModal}>
          New run
        </Button>
      ) : null}
    </Group>
  );

  const statusAlerts = (
    <>
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
    </>
  );

  const dashboardSummary = (
    <Stack gap="md">
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

      {statusAlerts}

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
    </Stack>
  );

  const runsTable = (
    <Stack gap="md">
      <Group justify="space-between" mb="xs">
        <Checkbox
          label="전체 선택"
          checked={allVisibleSelected}
          indeterminate={someVisibleSelected}
          disabled={selectableRunIds.length === 0}
          onChange={(event) => toggleSelectAllVisible(event.currentTarget.checked)}
        />
        <Button
          color="red"
          variant="light"
          leftSection={<IconTrash size={16} />}
          disabled={selectedDeleteCount === 0}
          loading={deletingRuns}
          onClick={deleteSelectedRuns}
        >
          선택 삭제{selectedDeleteCount > 0 ? ` (${selectedDeleteCount})` : ""}
        </Button>
      </Group>
      <Paper withBorder className={classes.tablePanel}>
        <Table striped highlightOnHover verticalSpacing="sm" className={classes.runsTable}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th className={classes.selectColumn}>
                <Checkbox
                  size="xs"
                  checked={allVisibleSelected}
                  indeterminate={someVisibleSelected}
                  disabled={selectableRunIds.length === 0}
                  aria-label="보이는 task 전체 선택"
                  onChange={(event) => toggleSelectAllVisible(event.currentTarget.checked)}
                />
              </Table.Th>
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
                <Table.Td colSpan={8}>
                  <Text c="dimmed" ta="center" py="lg">
                    No workflow runs yet.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>
    </Stack>
  );

  const workflowPreview = (
    <Stack gap="sm">
      <Paper withBorder p="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text fw={700}>Implemented workflow map</Text>
            <Text size="sm" c="dimmed">
              이 preview는 현재 구현된 실행 흐름을 요약합니다. 일부 데이터 보강 경로는 필요한 경우에만 실행됩니다.
            </Text>
          </div>
          <Group gap="xs">
            <Badge variant="light" color="opsBlue">Agent</Badge>
            <Badge variant="light" color="teal">Decision</Badge>
            <Badge variant="light" color="red">Exit action</Badge>
            <Badge variant="light" color="grape">Revision</Badge>
          </Group>
        </Group>
      </Paper>

      <Paper withBorder className={classes.workflowPreview} ref={workflowPreviewRef}>
        {activeSection === "workflow" ? (
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
            새 요청은 사전 검증, 지역 확정, 기본 관광 데이터 수집, 부족한 정보 판단을 거친 뒤 필요한 경우에만 보강 API 계획과 근거 병합 경로를 탑니다.
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
  );

  const placeholderCopy: Partial<Record<AppSection, { phase: string; items: string[] }>> = {
    "data-sources": {
      phase: "Phase 12",
      items: [
        "Visual, Route/Signal, Theme 계열 KTO API 실제 연결",
        "source family별 활성화 상태와 보강 이력",
        "catalog sync, cache, reindex 상태 표시",
      ],
    },
    evaluation: {
      phase: "Phase 11 이후",
      items: [
        "evidence 기반 상품 생성 품질 평가",
        "claim risk와 unresolved gap 추적",
        "revision 전후 비교",
      ],
    },
    costs: {
      phase: "Phase 13 또는 운영 단계",
      items: [
        "LLM provider별 토큰 사용량",
        "run별 비용 추적",
        "prompt debug log와 비용 분석 연결",
      ],
    },
    "poster-studio": {
      phase: "Phase 13 이후 또는 별도 후속 단계",
      items: [
        "승인된 상품의 포스터 초안",
        "이미지 asset과 홍보 문구 조합",
        "채널별 홍보 소재 변형",
      ],
    },
    settings: {
      phase: "Phase 13 운영 설정",
      items: [
        "feature flag와 API 활성화 설정",
        "Agent별 token budget",
        "사용자용/개발자용 workflow 표시 수준 설정",
      ],
    },
  };

  const placeholder = placeholderCopy[activeSection];

  const plannedView = placeholder ? (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Text fw={700}>{currentSection.title}</Text>
          <Badge variant="light" color="gray">
            향후 연결 예정
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          이 화면은 아직 실제 기능이 연결되지 않았습니다. 현재는 AppShell navigation에서 후속 Phase 진입점을 명확히 보여주기 위한 placeholder입니다.
        </Text>
        <Text size="sm" fw={700}>예정 범위: {placeholder.phase}</Text>
        <Stack gap={4}>
          {placeholder.items.map((item) => (
            <Text key={item} size="sm" c="dimmed">
              - {item}
            </Text>
          ))}
        </Stack>
      </Stack>
    </Paper>
  ) : null;

  const activeContent =
    activeSection === "dashboard"
      ? (
        <Stack gap="md">
          {dashboardSummary}
          {runsTable}
        </Stack>
      )
        : activeSection === "workflow"
          ? workflowPreview
          : plannedView;

  return (
    <Stack gap="md">
      {sectionHeader}
      {activeContent}

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

      <Modal opened={opened} onClose={closeCreateRunModal} title="Create workflow run" size="lg">
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
                max={5}
                description="최대 5개까지 생성할 수 있습니다."
                {...form.getInputProps("product_count")}
              />
            </Group>
            {createRunWarning ? (
              <Alert color="yellow" icon={<IconAlertCircle size={16} />}>
                {createRunWarning}
              </Alert>
            ) : null}
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
              <Button variant="subtle" onClick={closeCreateRunModal} disabled={creating}>
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
