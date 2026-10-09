"use client";

import { FileText, Loader2, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { EmptyState, ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatBytes, formatDate } from "@/lib/format";
import type { DocumentInfo } from "@/types/api";

import { useDeleteDocument, useDocuments, useUploadDocument } from "./use-documents";

const ACCEPT = ".pdf,.txt,.md,.markdown";

function DocStatus({ doc }: { doc: DocumentInfo }) {
  if (doc.status === "ready") return <Badge variant="secondary">Indexed · {doc.chunk_count} {doc.chunk_count === 1 ? "chunk" : "chunks"}</Badge>;
  if (doc.status === "failed") return <Badge variant="destructive">Failed</Badge>;
  return (
    <Badge variant="outline" className="gap-1">
      <Loader2 aria-hidden className="animate-spin" /> Indexing
    </Badge>
  );
}

export function DocumentLibrary({ compact = false }: { compact?: boolean }) {
  const documents = useDocuments();
  const upload = useUploadDocument();
  const remove = useDeleteDocument();
  const inputRef = useRef<HTMLInputElement>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const onFiles = async (files: FileList | null) => {
    setNotice(null);
    for (const file of Array.from(files ?? [])) {
      try {
        const result = await upload.mutateAsync(file);
        if (result.duplicate) setNotice(`"${file.name}" was already uploaded; reusing the existing index.`);
      } catch (e) {
        setNotice(`${file.name}: ${e instanceof Error ? e.message : "upload failed"}`);
      }
    }
    if (inputRef.current) inputRef.current.value = "";
  };

  const items = documents.data?.items ?? [];
  const shown = compact ? items.slice(0, 5) : items;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Document library</CardTitle>
          <CardDescription>PDF, TXT or Markdown. Indexed into pgvector for retrieval.</CardDescription>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          id="document-upload"
          onChange={(e) => onFiles(e.target.files)}
        />
        <Button asChild size="sm" variant="outline" disabled={upload.isPending}>
          <label htmlFor="document-upload" className="cursor-pointer">
            {upload.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <Upload aria-hidden />}
            Upload
          </label>
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {notice && (
          <p role="status" className="rounded-md bg-muted px-3 py-2 text-sm">
            {notice}
          </p>
        )}
        {documents.isError && <ErrorState error={documents.error} onRetry={() => documents.refetch()} />}
        {documents.isPending && <p className="text-sm text-muted-foreground">Loading documents…</p>}
        {documents.isSuccess && items.length === 0 && (
          <EmptyState icon={FileText} title="No documents yet">
            Upload reports, papers or notes and the research workflow will search them alongside the web.
          </EmptyState>
        )}
        <ul className="divide-y" aria-label="Uploaded documents">
          {shown.map((doc) => (
            <li key={doc.id} className="flex items-center gap-3 py-2.5">
              <FileText aria-hidden className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={doc.filename}>
                  {doc.filename}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(doc.size_bytes)}
                  {doc.page_count ? ` · ${doc.page_count} pages` : ""} · {formatDate(doc.created_at)}
                </p>
                {doc.error && <p className="text-xs text-destructive">{doc.error}</p>}
              </div>
              <DocStatus doc={doc} />
              <Button
                size="icon"
                variant="ghost"
                aria-label={`Delete ${doc.filename}`}
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Delete "${doc.filename}" and its index?`)) remove.mutate(doc.id);
                }}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
        {compact && items.length > shown.length && (
          <p className="text-xs text-muted-foreground">+{items.length - shown.length} more on the Documents page</p>
        )}
      </CardContent>
    </Card>
  );
}
