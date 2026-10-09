import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageProgress } from "@/features/research/stage-progress";
import type { SessionDetail } from "@/types/api";

const base = {
  id: "s", question: "q", iteration: 1, max_iterations: 3, created_at: "", updated_at: "",
  options: { use_web: true, use_documents: true, document_ids: null, require_plan_approval: true, require_report_approval: false },
  pending_approval: null, critic_feedback: null, error: null, tasks: [], sources: [], evidence: [], has_report: false,
} satisfies Omit<SessionDetail, "status" | "stage">;

describe("StageProgress", () => {
  it("marks the persisted stage as current and hides disabled review steps", () => {
    render(<StageProgress session={{ ...base, status: "running", stage: "web_researcher" }} />);
    expect(screen.getByText("Research").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.queryByText("Final review")).not.toBeInTheDocument();
  });

  it("marks everything done when completed", () => {
    render(<StageProgress session={{ ...base, status: "completed", stage: "done" }} />);
    expect(screen.queryByRole("listitem", { current: "step" })).toBeNull();
  });
});
