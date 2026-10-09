"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/status-badge";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";

const PAGE = 10;

export function useSessions() {
  return useInfiniteQuery({
    queryKey: ["sessions"],
    queryFn: ({ pageParam }) => api.listSessions(PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.items.length < last.total ? last.offset + PAGE : undefined),
    refetchInterval: 5_000,
  });
}

export function SessionList() {
  const sessions = useSessions();
  const items = sessions.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent research</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {sessions.isError && <ErrorState error={sessions.error} onRetry={() => sessions.refetch()} />}
        {sessions.isPending && <p className="text-sm text-muted-foreground">Loading sessions…</p>}
        {sessions.isSuccess && items.length === 0 && (
          <EmptyState icon={History} title="No research yet">
            Sessions are saved automatically, so you can come back to them later.
          </EmptyState>
        )}
        <ul className="divide-y">
          {items.map((s) => (
            <li key={s.id}>
              <Link
                href={`/research/${s.id}`}
                className="flex flex-col gap-1 rounded-md px-2 py-3 hover:bg-muted focus-visible:outline-2 sm:flex-row sm:items-center sm:gap-4"
              >
                <span className="line-clamp-2 flex-1 text-sm font-medium">{s.question}</span>
                <span className="flex shrink-0 items-center gap-3">
                  <StatusBadge status={s.status} />
                  <span className="text-xs text-muted-foreground">{formatDate(s.created_at)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {sessions.hasNextPage && (
          <Button variant="ghost" size="sm" onClick={() => sessions.fetchNextPage()} disabled={sessions.isFetchingNextPage}>
            Load more
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function WorkflowStatusCard() {
  const sessions = useSessions();
  const items = sessions.data?.pages.flatMap((p) => p.items) ?? [];
  const count = (status: string) => items.filter((s) => s.status === status).length;
  const stats = [
    { label: "Running", value: count("running") + count("queued") },
    { label: "Awaiting approval", value: count("awaiting_approval") },
    { label: "Completed", value: count("completed") + count("partial") },
  ];
  const waiting = items.filter((s) => s.status === "awaiting_approval");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Workflow status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-3 gap-2 text-center">
          {stats.map((s) => (
            <div key={s.label} className="rounded-md bg-muted/50 p-2">
              <dt className="text-xs text-muted-foreground">{s.label}</dt>
              <dd className="text-2xl font-semibold tabular-nums">{s.value}</dd>
            </div>
          ))}
        </dl>
        {waiting.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Waiting for you</p>
            {waiting.slice(0, 3).map((s) => (
              <Link key={s.id} href={`/research/${s.id}`} className="block truncate text-sm text-primary hover:underline">
                {s.question}
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
