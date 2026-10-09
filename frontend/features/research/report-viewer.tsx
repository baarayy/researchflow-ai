"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Copy, Download, ExternalLink, FileText, Globe } from "lucide-react";
import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { ErrorState } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { BibliographyEntry, Report } from "@/types/api";

/** The bibliography is rendered from structured data (with anchors), so drop it from the Markdown. */
export function stripBibliography(markdown: string): string {
  return markdown.split(/\n## Bibliography\n/)[0];
}

const markdownComponents: Components = {
  a: ({ href, children }) => {
    if (href?.startsWith("#ref-")) {
      return (
        <a href={href} className="citation no-underline" aria-label={`Citation ${href.slice(5)}`}>
          {children}
        </a>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    );
  },
  blockquote: ({ children }) => (
    <blockquote className="not-italic rounded-r-md border-l-4 border-amber-400 bg-amber-50 py-1 dark:bg-amber-950/40">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table>{children}</table>
    </div>
  ),
};

function Bibliography({ entries }: { entries: BibliographyEntry[] }) {
  if (!entries.length) return null;
  return (
    <section aria-labelledby="bibliography-heading" className="mt-8 border-t pt-6">
      <h2 id="bibliography-heading" className="mb-3 text-lg font-semibold">Bibliography</h2>
      <ol className="space-y-2 text-sm">
        {entries.map((b) => (
          <li key={b.number} id={`ref-${b.number}`} className="flex scroll-mt-20 gap-2 rounded-md p-1 target:bg-yellow-100 dark:target:bg-yellow-900/40">
            <span className="w-6 shrink-0 text-right font-mono text-muted-foreground">{b.number}.</span>
            {b.kind === "web" ? <Globe aria-hidden className="mt-0.5 size-4 shrink-0 text-sky-600" /> : <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
            <span>
              {b.url ? (
                <a href={b.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium text-primary hover:underline">
                  {b.title} <ExternalLink aria-hidden className="inline size-3" />
                </a>
              ) : (
                <span className="font-medium">{b.title}</span>
              )}
              <span className="text-muted-foreground">
                {b.kind === "document" ? ` — uploaded document${b.page_number ? `, p. ${b.page_number}` : ""}` : ""}
                {b.published_date ? ` — published ${b.published_date}` : ""}
                {b.content_kind === "snippet" ? " — search snippet" : ""}
                {b.possibly_outdated ? " — possibly outdated" : ""}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function ReportBody({ report }: { report: Report }) {
  const [copied, setCopied] = useState(false);
  const { content } = report;

  const copy = async () => {
    await navigator.clipboard.writeText(report.markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([report.markdown], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `research-report-${report.session_id.slice(0, 8)}.md` });
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />} {copied ? "Copied" : "Copy Markdown"}
        </Button>
        <Button variant="outline" size="sm" onClick={download}>
          <Download aria-hidden /> Download .md
        </Button>
      </div>

      {content.status !== "complete" && (
        <Alert className="border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40">
          <AlertTriangle aria-hidden className="text-amber-600" />
          <AlertTitle>{content.status === "partial" ? "Partial report — evidence is incomplete" : "Insufficient evidence"}</AlertTitle>
          <AlertDescription>Treat findings with caution and check the limitations section.</AlertDescription>
        </Alert>
      )}
      {content.warnings.length > 0 && (
        <Alert>
          <AlertTriangle aria-hidden />
          <AlertTitle>Citation checks adjusted this report</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">{content.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1"><span className="citation">[1]</span> sourced claim with citation</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block size-3 rounded-sm border-l-4 border-amber-400 bg-amber-50" /> model interpretation (not directly sourced)</span>
      </div>

      <article className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-20">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]} components={markdownComponents}>
          {stripBibliography(report.markdown)}
        </ReactMarkdown>
      </article>
      <Bibliography entries={content.bibliography} />
    </div>
  );
}

export function ReportViewer({ sessionId }: { sessionId: string }) {
  const report = useQuery({ queryKey: ["research", sessionId, "report"], queryFn: () => api.getReport(sessionId) });
  if (report.isPending) return <p className="text-sm text-muted-foreground">Loading report…</p>;
  if (report.isError) return <ErrorState error={report.error} onRetry={() => report.refetch()} />;
  return <ReportBody report={report.data} />;
}
