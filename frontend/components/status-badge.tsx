import { AlertTriangle, CheckCircle2, CircleDashed, Hand, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SessionStatus } from "@/types/api";

const STYLES: Record<SessionStatus, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  queued: { label: "Queued", className: "bg-muted text-muted-foreground", Icon: CircleDashed },
  running: { label: "Running", className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200", Icon: Loader2 },
  awaiting_approval: {
    label: "Needs approval",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200",
    Icon: Hand,
  },
  completed: {
    label: "Completed",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
    Icon: CheckCircle2,
  },
  partial: {
    label: "Partial",
    className: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
    Icon: AlertTriangle,
  },
  failed: { label: "Failed", className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200", Icon: XCircle },
};

export function StatusBadge({ status, className }: { status: SessionStatus; className?: string }) {
  const { label, className: color, Icon } = STYLES[status] ?? STYLES.queued;
  return (
    <Badge className={cn("gap-1 border-0", color, className)}>
      <Icon aria-hidden className={cn(status === "running" && "animate-spin")} />
      {label}
    </Badge>
  );
}
