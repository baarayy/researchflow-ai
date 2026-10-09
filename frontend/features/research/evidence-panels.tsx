import { BadgeCheck, CircleDashed, ExternalLink, FileText, Globe, Quote, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CriticFeedback, Evidence, ResearchTask, Source, WorkflowEvent } from "@/types/api";

import { NODE_LABELS } from "./stages";

const TASK_STATUS: Record<ResearchTask["status"], string> = {
  pending: "Pending",
  in_progress: "Researching",
  done: "Answered",
  no_evidence: "No evidence",
  dropped: "Dropped",
};

export function TaskList({ tasks }: { tasks: ResearchTask[] }) {
  const active = tasks.filter((t) => t.status !== "dropped");
  if (!active.length) return <EmptyState icon={CircleDashed} title="No plan yet">The planner is working on it.</EmptyState>;
  return (
    <ol className="space-y-2">
      {active.map((t) => (
        <li key={t.task_key} className="rounded-md border bg-background p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{t.task_key}</span>
            <Badge variant={t.status === "done" ? "secondary" : "outline"} className={cn(t.status === "no_evidence" && "text-amber-700 dark:text-amber-300")}>
              {TASK_STATUS[t.status]}
            </Badge>
            {t.origin !== "plan" && <Badge variant="outline">{t.origin === "critic" ? "Added by critic" : "Added by reviewer"}</Badge>}
          </div>
          <p className="mt-1.5 text-sm font-medium">{t.question}</p>
          {t.rationale && <p className="text-xs text-muted-foreground">{t.rationale}</p>}
        </li>
      ))}
    </ol>
  );
}

export function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return <EmptyState icon={Globe} title="No sources yet">Sources appear as researchers find them.</EmptyState>;
  return (
    <ul className="space-y-2">
      {sources.map((s) => (
        <li key={s.source_key} className="rounded-md border bg-background p-3 text-sm">
          <div className="flex items-start gap-2">
            {s.kind === "web" ? <Globe aria-hidden className="mt-0.5 size-4 shrink-0 text-sky-600" /> : <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
            <div className="min-w-0 flex-1">
              {s.url ? (
                <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                  <span className="break-all">{s.title}</span> <ExternalLink aria-hidden className="size-3" />
                </a>
              ) : (
                <p className="font-medium">{s.title}{s.page_number ? `, p. ${s.page_number}` : ""}</p>
              )}
              <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{s.excerpt}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <Badge variant="outline">{s.content_kind === "snippet" ? "Search snippet (unverified page)" : s.content_kind === "passage" ? "Document passage" : "Full text"}</Badge>
                {s.published_date && <Badge variant="outline">Published {s.published_date}</Badge>}
                {s.possibly_outdated && <Badge variant="outline" className="text-amber-700 dark:text-amber-300">Possibly outdated</Badge>}
              </div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function EvidenceList({ evidence, sources }: { evidence: Evidence[]; sources: Source[] }) {
  if (!evidence.length) return <EmptyState icon={Quote} title="No evidence yet">Claims extracted from sources will appear here, each linked to its source.</EmptyState>;
  const byKey = new Map(sources.map((s) => [s.source_key, s]));
  return (
    <ul className="space-y-2">
      {evidence.map((e) => {
        const src = byKey.get(e.source_key);
        return (
          <li key={e.evidence_key} className="rounded-md border-l-4 border-l-sky-500 bg-background p-3 text-sm shadow-xs">
            <p><span className="sr-only">Sourced fact: </span>{e.claim}</p>
            {e.quote && (
              <blockquote className="mt-2 border-l-2 pl-3 text-xs italic text-muted-foreground">“{e.quote}”</blockquote>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span>Source: {src?.title ?? e.source_key}{src?.page_number ? `, p. ${src.page_number}` : ""}</span>
              {e.task_key && <Badge variant="outline">{e.task_key}</Badge>}
              {e.quote &&
                (e.quote_verified ? (
                  <Badge variant="secondary" className="gap-1"><BadgeCheck aria-hidden /> Quote verified</Badge>
                ) : (
                  <Badge variant="outline" className="gap-1 text-amber-700 dark:text-amber-300"><TriangleAlert aria-hidden /> Quote not found in source</Badge>
                ))}
              <Badge variant="outline">Confidence {percent(e.confidence)}</Badge>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function CriticPanel({ critic }: { critic: CriticFeedback | null }) {
  if (!critic) return <EmptyState icon={CircleDashed} title="Not assessed yet">The critic runs after each research iteration.</EmptyState>;
  return (
    <div className="space-y-4 text-sm">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Coverage", percent(critic.coverage)],
          ["Evidence quality", critic.evidence_quality],
          ["Citation completeness", percent(critic.citation_completeness)],
          ["Verdict", critic.sufficient ? "Sufficient" : "Needs more"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-md border bg-background p-3">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="text-lg font-semibold capitalize">{v}</dd>
          </div>
        ))}
      </dl>
      <p>{critic.summary}</p>
      {critic.remaining_gaps.length > 0 && (
        <div>
          <p className="font-medium">Remaining gaps</p>
          <ul className="list-disc pl-5 text-muted-foreground">{critic.remaining_gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Routing uses explicit rules (coverage threshold, quality, iteration and tool budgets); the model&apos;s opinion can only veto “sufficient”.
      </p>
    </div>
  );
}

function describe(e: WorkflowEvent): string {
  const p = e.payload as Record<string, unknown>;
  if (e.type === "interrupt") return `Paused for ${p.kind === "plan_review" ? "plan approval" : "pre-report approval"}`;
  if (e.type === "approval") return p.action === "approve" ? "Approved by reviewer" : `Changes requested: ${p.feedback ?? ""}`;
  if (e.type === "status") return `Status: ${p.status}${p.resumed ? " (resumed from checkpoint)" : ""}`;
  if (e.type === "error") return String(p.message ?? "Error");
  const label = NODE_LABELS[e.node ?? ""] ?? e.node ?? "Step";
  if (e.node === "web_researcher" || e.node === "document_researcher") return `${label}: “${p.query}” → ${p.result_count} result(s)${p.status === "error" ? " (failed)" : ""}`;
  if (e.node === "dispatcher") return `${label} (iteration ${p.iteration}, ${(p.tool_calls as unknown[] | undefined)?.length ?? 0} call(s))`;
  if (e.node === "evidence_analyzer") return `${label}: ${p.new_evidence} new item(s)`;
  if (e.node === "critic") return `${label}: coverage ${percent(p.coverage as number)} — ${p.sufficient ? "sufficient" : "more research needed"}`;
  if (e.node === "planner") return p.failed ? "Planner failed" : `${label} (${p.task_count} tasks)`;
  return label;
}

export function EventLog({ events }: { events: WorkflowEvent[] }) {
  if (!events.length) return <EmptyState icon={CircleDashed} title="Waiting for events" />;
  return (
    <ol className="space-y-1.5 font-mono text-xs" aria-live="polite">
      {events.map((e) => (
        <li key={e.id} className={cn("flex gap-3", e.type === "error" && "text-destructive")}>
          <time className="shrink-0 text-muted-foreground">{new Date(e.created_at).toLocaleTimeString()}</time>
          <span>{describe(e)}</span>
        </li>
      ))}
    </ol>
  );
}
