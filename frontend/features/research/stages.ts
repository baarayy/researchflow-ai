// Graph nodes grouped into user-facing stages (order matters).
export const STAGES = [
  { key: "plan", label: "Plan", nodes: ["planner"] },
  { key: "plan_review", label: "Plan review", nodes: ["plan_review"] },
  { key: "research", label: "Research", nodes: ["dispatcher", "web_researcher", "document_researcher"] },
  { key: "analyze", label: "Analyze", nodes: ["evidence_analyzer"] },
  { key: "critique", label: "Critique", nodes: ["critic"] },
  { key: "report_review", label: "Final review", nodes: ["report_review"] },
  { key: "report", label: "Report", nodes: ["report_generator", "done"] },
] as const;

export function stageIndex(node: string | null): number {
  if (!node) return -1;
  return STAGES.findIndex((s) => (s.nodes as readonly string[]).includes(node));
}

export const NODE_LABELS: Record<string, string> = {
  planner: "Planner created the research plan",
  plan_review: "Plan review",
  dispatcher: "Dispatcher selected research tools",
  web_researcher: "Web search",
  document_researcher: "Document search",
  evidence_analyzer: "Evidence analyzed",
  critic: "Critic assessed coverage",
  report_review: "Pre-report review",
  report_generator: "Report generated",
};
