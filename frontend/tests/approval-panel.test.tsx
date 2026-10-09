import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApprovalPanel } from "@/features/research/approval-panel";
import type { PlanReviewPayload } from "@/types/api";

import { mockFetch, renderWithClient } from "./utils";

const plan: PlanReviewPayload = {
  kind: "plan_review",
  objective: "Answer the question",
  revision: 0,
  tasks: [{ id: "T1", question: "What is pgvector?", rationale: "Basics", evidence_type: "docs" }],
};

describe("ApprovalPanel", () => {
  it("shows the plan and approves it", async () => {
    const calls = mockFetch({ "POST /research/s1/approve": { id: "s1", status: "running" } });
    renderWithClient(<ApprovalPanel sessionId="s1" pending={plan} />);
    expect(screen.getByText("What is pgvector?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /approve plan/i }));
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/research/s1/approve");
  });

  it("requires feedback before requesting changes", async () => {
    const calls = mockFetch({ "POST /research/s1/revise": { id: "s1", status: "running" } });
    renderWithClient(<ApprovalPanel sessionId="s1" pending={plan} />);
    await userEvent.click(screen.getByRole("button", { name: /request changes/i }));
    const send = screen.getByRole("button", { name: /send feedback/i });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/what should change/i), "Add a licensing task");
    await userEvent.click(send);
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ feedback: "Add a licensing task" });
  });
});
