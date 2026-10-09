import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NewResearchForm } from "@/features/research/new-research-form";

import { mockFetch, renderWithClient } from "./utils";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("NewResearchForm", () => {
  it("starts research with an idempotency key and navigates to the workspace", async () => {
    const calls = mockFetch({
      "GET /documents?limit=100": { items: [], total: 0, limit: 100, offset: 0 },
      "POST /research": { id: "abc", status: "queued" },
    });
    renderWithClient(<NewResearchForm />);

    const button = screen.getByRole("button", { name: /start research/i });
    expect(button).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/research question/i), "How do vector databases index embeddings?");
    await userEvent.click(screen.getByLabelText(/review before report/i));
    await userEvent.click(button);

    const post = calls.find((c) => c.method === "POST")!;
    expect(JSON.parse(String(post.init?.body))).toMatchObject({
      question: "How do vector databases index embeddings?",
      use_web: true,
      require_plan_approval: true,
      require_report_approval: true,
    });
    expect((post.init?.headers as Record<string, string>)["Idempotency-Key"]).toMatch(/[0-9a-f-]{36}/);
    expect(push).toHaveBeenCalledWith("/research/abc");
  });

  it("shows API errors", async () => {
    mockFetch({
      "GET /documents?limit=100": { items: [], total: 0, limit: 100, offset: 0 },
      "POST /research": () =>
        new Response(JSON.stringify({ error: { code: "rate_limited", message: "Too many requests" } }), {
          status: 429,
        }),
    });
    renderWithClient(<NewResearchForm />);
    await userEvent.type(screen.getByLabelText(/research question/i), "A long enough research question");
    await userEvent.click(screen.getByRole("button", { name: /start research/i }));
    expect(await screen.findByText("Too many requests")).toBeInTheDocument();
  });
});
