import { Badge } from "@mantine/core";

const statusColor: Record<string, string> = {
  pending: "gray",
  running: "blue",
  awaiting_approval: "yellow",
  changes_requested: "yellow",
  succeeded: "green",
  approved: "green",
  rejected: "red",
  started: "blue",
  failed: "red",
  cancelled: "gray",
  unsupported: "gray",
  needs_clarification: "red",
};

const statusLabel: Record<string, string> = {
  pending: "대기",
  running: "실행 중",
  awaiting_approval: "승인 대기",
  changes_requested: "수정 요청",
  succeeded: "성공",
  approved: "승인됨",
  rejected: "반려됨",
  started: "시작됨",
  failed: "실패",
  cancelled: "취소됨",
  unsupported: "지원 범위 밖",
  needs_clarification: "실패",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={statusColor[status] ?? "gray"} variant="light" size="sm">
      {statusLabel[status] ?? status}
    </Badge>
  );
}
