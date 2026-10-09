"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { DocumentPicker } from "@/features/documents/document-picker";
import { api } from "@/lib/api";
import type { CreateResearchRequest } from "@/types/api";

const EXAMPLE =
  "Compare the leading open-source LLMs for building AI agents in 2026. Evaluate their reasoning capabilities, hardware requirements, licensing, and suitability for production.";

function Toggle({ id, label, hint, checked, onChange }: {
  id: string; label: string; hint: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <Label htmlFor={id}>{label}</Label>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

export function NewResearchForm() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [useWeb, setUseWeb] = useState(true);
  const [useDocs, setUseDocs] = useState(true);
  const [documentIds, setDocumentIds] = useState<string[] | null>(null);
  const [planApproval, setPlanApproval] = useState(true);
  const [reportApproval, setReportApproval] = useState(false);
  const [iterations, setIterations] = useState(3);
  // One key per logical submission: a retried/double-clicked request can't start two runs.
  const idempotencyKey = useRef<string | null>(null);

  const create = useMutation({
    mutationFn: (body: CreateResearchRequest) => {
      idempotencyKey.current ??= crypto.randomUUID();
      return api.createResearch(body, idempotencyKey.current);
    },
    onSuccess: (session) => {
      idempotencyKey.current = null;
      router.push(`/research/${session.id}`);
    },
  });

  const tooShort = question.trim().length < 10;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Start a research session</CardTitle>
        <CardDescription>
          Ask a complex question. The workflow plans subquestions, searches the web and your documents, critiques
          its evidence and writes a cited report.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (tooShort) return;
            create.mutate({
              question: question.trim(),
              use_web: useWeb,
              use_documents: useDocs,
              document_ids: useDocs ? documentIds : null,
              require_plan_approval: planApproval,
              require_report_approval: reportApproval,
              max_iterations: iterations,
            });
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="question">Research question</Label>
            <Textarea
              id="question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={EXAMPLE}
              rows={4}
              maxLength={2000}
              aria-describedby="question-hint"
            />
            <div id="question-hint" className="flex justify-between text-xs text-muted-foreground">
              <button type="button" className="underline-offset-2 hover:underline" onClick={() => setQuestion(EXAMPLE)}>
                Use example question
              </button>
              <span>{question.length}/2000</span>
            </div>
          </div>

          <div className="grid gap-4 rounded-lg border bg-muted/30 p-4 sm:grid-cols-2">
            <Toggle id="use-web" label="Web search" hint="Search the public web" checked={useWeb} onChange={setUseWeb} />
            <Toggle id="use-docs" label="My documents" hint="Semantic search over uploads" checked={useDocs} onChange={setUseDocs} />
            <Toggle id="plan-approval" label="Review plan first" hint="Pause for approval after planning" checked={planApproval} onChange={setPlanApproval} />
            <Toggle id="report-approval" label="Review before report" hint="Pause before writing the report" checked={reportApproval} onChange={setReportApproval} />
            <div className="flex items-center justify-between gap-4 sm:col-span-2">
              <div>
                <Label htmlFor="iterations">Max research iterations</Label>
                <p className="text-xs text-muted-foreground">Upper bound on critique-and-research loops</p>
              </div>
              <select
                id="iterations"
                value={iterations}
                onChange={(e) => setIterations(Number(e.target.value))}
                className="h-9 rounded-md border bg-background px-2 text-sm"
              >
                {[1, 2, 3].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
            {useDocs && (
              <div className="sm:col-span-2">
                <DocumentPicker value={documentIds} onChange={setDocumentIds} />
              </div>
            )}
          </div>

          {create.isError && (
            <Alert variant="destructive">
              <AlertDescription>{create.error.message}</AlertDescription>
            </Alert>
          )}

          <Button type="submit" size="lg" disabled={tooShort || create.isPending || (!useWeb && !useDocs)}>
            {create.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <Search aria-hidden />}
            Start research
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
