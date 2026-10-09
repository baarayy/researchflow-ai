import type {
  CreateResearchRequest,
  DocumentInfo,
  Health,
  Page,
  Report,
  SessionDetail,
  SessionSummary,
} from "@/types/api";

// Public URL of the FastAPI backend. Not a secret: server API keys never reach the browser.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1${path}`, init);
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the ResearchFlow API. Is the backend running?");
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(response.status, error?.code ?? "error", error?.message ?? response.statusText);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  health: () => request<Health>("/health"),

  createResearch: (data: CreateResearchRequest, idempotencyKey: string) =>
    request<SessionSummary>("/research", {
      ...json("POST", data),
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    }),
  getResearch: (id: string) => request<SessionDetail>(`/research/${id}`),
  getReport: (id: string) => request<Report>(`/research/${id}/report`),
  approve: (id: string, feedback?: string) => request<SessionSummary>(`/research/${id}/approve`, json("POST", { feedback })),
  revise: (id: string, feedback: string) => request<SessionSummary>(`/research/${id}/revise`, json("POST", { feedback })),
  listSessions: (limit = 20, offset = 0) =>
    request<Page<SessionSummary>>(`/sessions?limit=${limit}&offset=${offset}`),

  listDocuments: () => request<Page<DocumentInfo>>("/documents?limit=100"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ document: DocumentInfo; duplicate: boolean }>("/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
};
