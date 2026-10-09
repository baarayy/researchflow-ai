"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hand, Loader2, MessageSquareText } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { percent } from "@/lib/format";
import type { PendingApproval } from "@/types/api";

export function ApprovalPanel({ sessionId, pending }: { sessionId: string; pending: PendingApproval }) {
  const qc = useQueryClient();
  const [feedback, setFeedback] = useState("");
  const [mode, setMode] = useState<"idle" | "revising">("idle");

  const decide = useMutation({
    mutationFn: (action: "approve" | "revise") =>
      action === "approve" ? api.approve(sessionId) : api.revise(sessionId, feedback.trim()),
    onSuccess: () => {
      setFeedback("");
      setMode("idle");
      qc.invalidateQueries({ queryKey: ["research", sessionId] });
    },
  });

  const isPlan = pending.kind === "plan_review";

  return (
    <Card className="border-violet-300 bg-violet-50/60 dark:border-violet-900 dark:bg-violet-950/30" role="region" aria-label="Approval required">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Hand aria-hidden className="size-5 text-violet-600" />
          {isPlan ? "Review the research plan" : "Review before the report is written"}
        </CardTitle>
        <CardDescription>
          The workflow is paused at a durable checkpoint. It resumes when you respond — even after a server restart.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {pending.kind === "plan_review" ? (
          <div className="space-y-3">
            {pending.objective && <p className="text-sm"><span className="font-medium">Objective:</span> {pending.objective}</p>}
            <ol className="space-y-2">
              {pending.tasks.map((t) => (
                <li key={t.id} className="rounded-md border bg-background p-3 text-sm">
                  <p className="font-medium"><span className="mr-2 font-mono text-xs text-muted-foreground">{t.id}</span>{t.question}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{t.rationale} · needs {t.evidence_type}</p>
                </li>
              ))}
            </ol>
          </div>
        ) : (
          <div className="grid gap-2 text-sm sm:grid-cols-3">
            <p><span className="text-muted-foreground">Coverage</span><br /><span className="text-lg font-semibold">{percent(pending.coverage)}</span></p>
            <p><span className="text-muted-foreground">Evidence items</span><br /><span className="text-lg font-semibold">{pending.evidence_count}</span></p>
            <p><span className="text-muted-foreground">Sources</span><br /><span className="text-lg font-semibold">{pending.source_count}</span></p>
            {pending.critic_summary && <p className="sm:col-span-3">{pending.critic_summary}</p>}
            {pending.remaining_gaps.length > 0 && (
              <ul className="list-disc pl-5 text-muted-foreground sm:col-span-3">
                {pending.remaining_gaps.map((g) => <li key={g}>{g}</li>)}
              </ul>
            )}
          </div>
        )}

        {mode === "revising" && (
          <div className="space-y-2">
            <Label htmlFor="feedback">{isPlan ? "What should change in the plan?" : "What else should be researched?"}</Label>
            <Textarea id="feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)} rows={3} maxLength={2000} autoFocus />
          </div>
        )}

        {decide.isError && (
          <Alert variant="destructive"><AlertDescription>{decide.error.message}</AlertDescription></Alert>
        )}

        <div className="flex flex-wrap gap-2">
          {mode === "idle" ? (
            <>
              <Button onClick={() => decide.mutate("approve")} disabled={decide.isPending}>
                {decide.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <CheckCircle2 aria-hidden />}
                {isPlan ? "Approve plan" : "Write the report"}
              </Button>
              <Button variant="outline" onClick={() => setMode("revising")} disabled={decide.isPending}>
                <MessageSquareText aria-hidden /> Request changes
              </Button>
            </>
          ) : (
            <>
              <Button onClick={() => decide.mutate("revise")} disabled={decide.isPending || feedback.trim().length < 3}>
                {decide.isPending && <Loader2 aria-hidden className="animate-spin" />}
                Send feedback & resume
              </Button>
              <Button variant="ghost" onClick={() => setMode("idle")}>Cancel</Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
