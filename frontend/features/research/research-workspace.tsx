"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, RotateCw, WifiOff, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { StatusBadge } from "@/components/status-badge";
import { ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useResearchEvents } from "@/hooks/use-research-events";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { SessionDetail } from "@/types/api";

import { ApprovalPanel } from "./approval-panel";
import { CriticPanel, EventLog, EvidenceList, SourceList, TaskList } from "./evidence-panels";
import { ReportViewer } from "./report-viewer";
import { StageProgress } from "./stage-progress";

export function WorkspaceSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function RetryButton({ session }: { session: SessionDetail }) {
  const router = useRouter();
  const retry = useMutation({
    mutationFn: () =>
      api.createResearch({ question: session.question, ...session.options, max_iterations: session.max_iterations }, crypto.randomUUID()),
    onSuccess: (s) => router.push(`/research/${s.id}`),
  });
  return (
    <Button size="sm" variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending}>
      <RotateCw aria-hidden /> Run again
    </Button>
  );
}

function Workspace({ sessionId }: { sessionId: string }) {
  const session = useQuery({ queryKey: ["research", sessionId], queryFn: () => api.getResearch(sessionId) });
  const { events, state } = useResearchEvents(sessionId);

  if (session.isPending) return <WorkspaceSkeleton />;
  if (session.isError) {
    if (session.error instanceof ApiError && session.error.status === 404) {
      return <ErrorState error={new Error("This research session does not exist or belongs to another user.")} />;
    }
    return <ErrorState error={session.error} onRetry={() => session.refetch()} />;
  }

  const s = session.data;
  const active = s.status === "running" || s.status === "queued";

  return (
    <div className="space-y-5">
      <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" /> Dashboard
      </Link>

      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <StatusBadge status={s.status} />
            <span>Iteration {s.iteration} of {s.max_iterations}</span>
            <span>Started {formatDate(s.created_at)}</span>
            {active && <span className="inline-flex items-center gap-1"><Loader2 aria-hidden className="size-3 animate-spin" /> live</span>}
            {state === "reconnecting" && <span className="inline-flex items-center gap-1 text-amber-600"><WifiOff aria-hidden className="size-3" /> reconnecting…</span>}
          </div>
          <h1 className="text-xl font-semibold leading-snug">{s.question}</h1>
        </CardHeader>
        <CardContent>
          <StageProgress session={s} />
        </CardContent>
      </Card>

      {s.status === "failed" && (
        <Alert variant="destructive">
          <XCircle aria-hidden />
          <AlertTitle>Research failed</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>{s.error ?? "The workflow stopped unexpectedly."}</span>
            <RetryButton session={s} />
          </AlertDescription>
        </Alert>
      )}

      {s.status === "awaiting_approval" && s.pending_approval && (
        <ApprovalPanel sessionId={s.id} pending={s.pending_approval} />
      )}

      <Tabs defaultValue={s.has_report ? "report" : "plan"} key={String(s.has_report)}>
        <TabsList className="flex-wrap">
          <TabsTrigger value="plan">Plan ({s.tasks.filter((t) => t.status !== "dropped").length})</TabsTrigger>
          <TabsTrigger value="sources">Sources ({s.sources.length})</TabsTrigger>
          <TabsTrigger value="evidence">Evidence ({s.evidence.length})</TabsTrigger>
          <TabsTrigger value="critic">Critic</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="report" disabled={!s.has_report}>Report</TabsTrigger>
        </TabsList>
        <Card className="mt-3">
          <CardContent className="pt-6">
            <TabsContent value="plan"><TaskList tasks={s.tasks} /></TabsContent>
            <TabsContent value="sources"><SourceList sources={s.sources} /></TabsContent>
            <TabsContent value="evidence"><EvidenceList evidence={s.evidence} sources={s.sources} /></TabsContent>
            <TabsContent value="critic"><CriticPanel critic={s.critic_feedback} /></TabsContent>
            <TabsContent value="activity"><EventLog events={events} /></TabsContent>
            <TabsContent value="report">{s.has_report && <ReportViewer sessionId={s.id} />}</TabsContent>
          </CardContent>
        </Card>
      </Tabs>
    </div>
  );
}

/** Reads the dynamic route param on the client (wrapped in Suspense by the page). */
export function ResearchWorkspace() {
  const { id } = useParams<{ id: string }>();
  return <Workspace key={id} sessionId={id} />;
}
