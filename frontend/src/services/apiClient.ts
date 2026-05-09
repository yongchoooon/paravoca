const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

type ApiEnvelope<T> = {
  data: T;
  error: { code: string; message: string; details: Record<string, unknown> } | null;
  meta: Record<string, unknown>;
};

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(message: string, code: string, details: Record<string, unknown>, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  const body = (await response.json()) as Partial<ApiEnvelope<T>> & { detail?: unknown };
  if (!response.ok || body.error) {
    const details = body.error?.details ?? {};
    const runId = typeof details.run_id === "string" ? ` (run_id: ${details.run_id})` : "";
    const fallbackMessage =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? "요청 값을 확인해 주세요."
          : `API error ${response.status}`;
    throw new ApiError(
      `${body.error?.message ?? fallbackMessage}${runId}`,
      body.error?.code ?? "API_ERROR",
      details,
      response.status
    );
  }
  return body.data as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  return parseResponse<T>(response);
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<T>(response);
}
