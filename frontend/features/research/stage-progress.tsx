import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import type { SessionDetail } from "@/types/api";

import { STAGES, stageIndex } from "./stages";

/** Shows the persisted `stage` of the session — never an estimated or animated fake. */
export function StageProgress({ session }: { session: SessionDetail }) {
  const done = session.status === "completed" || session.status === "partial";
  const current = done ? STAGES.length : stageIndex(session.stage);
  const visible = STAGES.filter(
    (s) =>
      (s.key !== "plan_review" || session.options.require_plan_approval) &&
      (s.key !== "report_review" || session.options.require_report_approval),
  );

  return (
    <ol aria-label="Workflow progress" className="flex flex-wrap items-center gap-x-2 gap-y-3">
      {visible.map((stage, i) => {
        const idx = STAGES.findIndex((s) => s.key === stage.key);
        const state = idx < current ? "done" : idx === current ? "current" : "todo";
        return (
          <li key={stage.key} className="flex items-center gap-2" aria-current={state === "current" ? "step" : undefined}>
            <span
              className={cn(
                "flex size-6 items-center justify-center rounded-full border text-xs font-medium",
                state === "done" && "border-primary bg-primary text-primary-foreground",
                state === "current" && "border-primary text-primary ring-2 ring-primary/30",
                state === "todo" && "text-muted-foreground",
                state === "current" && session.status === "failed" && "border-destructive text-destructive ring-destructive/30",
              )}
            >
              {state === "done" ? <Check aria-hidden className="size-3.5" /> : i + 1}
            </span>
            <span className={cn("text-sm", state === "todo" && "text-muted-foreground", state === "current" && "font-medium")}>
              {stage.label}
            </span>
            {i < visible.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-border" />}
          </li>
        );
      })}
    </ol>
  );
}
