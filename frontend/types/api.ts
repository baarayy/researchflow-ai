// Mirrors backend/app/schemas. Keep in sync when the API changes.

export type SessionStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "partial"
  | "failed";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionSummary {
  id: string;
  question: string;
  status: SessionStatus;
  stage: string | null;
  iteration: number;
  max_iterations: number;
  created_at: string;
  updated_at: string;
}

export interface ResearchTask {
  task_key: string;
  question: string;
  rationale: string;
  evidence_type: string;
  status: "pending" | "in_progress" | "done" | "no_evidence" | "dropped";
  origin: "plan" | "critic" | "human";
  iteration_added: number;
}

export interface Source {
  source_key: string;
  kind: "web" | "document";
  title: string;
  url: string | null;
  document_id: string | null;
  page_number: number | null;
  excerpt: string;
  content_kind: "snippet" | "full_text" | "passage";
  published_date: string | null;
  retrieved_at: string;
  possibly_outdated: boolean;
}

export interface Evidence {
  evidence_key: string;
  source_key: string;
  task_key: string | null;
  claim: string;
  quote: string | null;
  quote_verified: boolean;
  confidence: number;
}

export interface CriticFeedback {
  iteration: number;
  coverage: number;
  evidence_quality: "low" | "medium" | "high";
  citation_completeness: number | null;
  remaining_gaps: string[];
  model_requested_more: boolean;
  summary: string;
  sufficient: boolean;
}

export interface PlanReviewPayload {
  kind: "plan_review";
  objective: string;
  revision: number;
  tasks: { id: string; question: string; rationale: string; evidence_type: string }[];
}

export interface ReportReviewPayload {
  kind: "report_review";
  outcome: string;
  coverage: number | null;
  evidence_count: number;
  source_count: number;
  critic_summary: string | null;
  remaining_gaps: string[];
}

export type PendingApproval = PlanReviewPayload | ReportReviewPayload;

export interface ResearchOptions {
  use_web: boolean;
  use_documents: boolean;
  document_ids: string[] | null;
  require_plan_approval: boolean;
  require_report_approval: boolean;
}

export interface SessionDetail extends SessionSummary {
  options: ResearchOptions;
  pending_approval: PendingApproval | null;
  critic_feedback: CriticFeedback | null;
  error: string | null;
  tasks: ResearchTask[];
  sources: Source[];
  evidence: Evidence[];
  has_report: boolean;
}

export interface CreateResearchRequest extends Partial<ResearchOptions> {
  question: string;
  max_iterations?: number;
}

export interface BibliographyEntry {
  number: number;
  source_id: string;
  kind: "web" | "document";
  title: string;
  url: string | null;
  document_id: string | null;
  page_number: number | null;
  content_kind: string;
  published_date: string | null;
  retrieved_at: string | null;
  possibly_outdated: boolean;
}

export interface ReportContent {
  status: "complete" | "partial" | "insufficient_evidence";
  outcome: string;
  findings: { heading: string; statement: string; kind: "fact" | "inference"; citations: number[] }[];
  bibliography: BibliographyEntry[];
  warnings: string[];
  limitations: string[];
  demo_mode: boolean;
}

export interface Report {
  session_id: string;
  status: ReportContent["status"];
  markdown: string;
  content: ReportContent;
  created_at: string;
}

export interface WorkflowEvent {
  id: number;
  type: "node" | "interrupt" | "status" | "error" | "approval";
  node: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "pending" | "indexing" | "ready" | "failed";
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  created_at: string;
}

export interface Health {
  status: string;
  demo_mode: boolean;
  providers: { llm: string; search: string; embeddings: string };
  limits: { max_iterations: number; max_upload_mb: number };
}
