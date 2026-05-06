const KST_FORMATTER = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:\d{2})$/;

export function formatKstDateTime(value: string | null | undefined) {
  if (!value) return "-";
  const normalized = HAS_TIMEZONE.test(value) ? value : `${value}+09:00`;
  return KST_FORMATTER.format(new Date(normalized));
}
