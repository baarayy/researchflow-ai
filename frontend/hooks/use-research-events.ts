"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import { readSse } from "@/lib/sse";
import type { WorkflowEvent } from "@/types/api";

export type StreamState = "connecting" | "open" | "reconnecting" | "closed";

/**
 * Subscribes to the persisted workflow event log over SSE. Each event also invalidates the
 * session query, so the workspace re-reads real state rather than guessing progress.
 * Reconnects with Last-Event-ID (exponential backoff) if the connection drops.
 * Mount with `key={sessionId}` so state resets when the session changes.
 */
export function useResearchEvents(sessionId: string) {
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [state, setState] = useState<StreamState>("connecting");

  useEffect(() => {
    const controller = new AbortController();
    const url = `${API_BASE_URL}/api/v1/research/${sessionId}/events`;
    let lastEventId: string | undefined;
    let ended = false;

    const refresh = () => {
      queryClient.invalidateQueries({ queryKey: ["research", sessionId] });
    };

    (async () => {
      for (let attempt = 0; !controller.signal.aborted && !ended; ) {
        try {
          await readSse(url, {
            lastEventId,
            signal: controller.signal,
            onMessage: (message) => {
              setState("open");
              attempt = 0;
              if (message.event === "end") {
                ended = true;
                refresh();
                return;
              }
              lastEventId = message.id ?? lastEventId;
              const event = JSON.parse(message.data) as WorkflowEvent;
              setEvents((prev) => (prev.some((e) => e.id === event.id) ? prev : [...prev, event]));
              refresh();
            },
          });
        } catch {
          if (controller.signal.aborted) return;
        }
        if (!ended && !controller.signal.aborted) {
          setState("reconnecting");
          attempt += 1;
          await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 15000)));
        }
      }
      if (!controller.signal.aborted) setState("closed");
    })();

    return () => controller.abort();
  }, [sessionId, queryClient]);

  return { events, state };
}
