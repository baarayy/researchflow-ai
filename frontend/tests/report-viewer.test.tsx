import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReportBody, stripBibliography } from "@/features/research/report-viewer";
import type { Report } from "@/types/api";

import { renderWithClient } from "./utils";

const report: Report = {
  session_id: "1234567890",
  status: "partial",
  created_at: "2026-01-01T00:00:00Z",
  markdown: [
    "# Research report",
    "## Main findings",
    "Apache 2.0 permits commercial use. [[1]](#ref-1)",
    "> **Interpretation (model inference, not directly sourced):** Permissive licenses are easier.",
    '<script>alert("xss")</script><img src=x onerror="alert(1)">',
    "[bad](javascript:alert(1))",
    "## Bibliography",
    "1. Should not be rendered from markdown",
  ].join("\n\n"),
  content: {
    status: "partial",
    outcome: "iteration_limit",
    findings: [],
    warnings: ["Removed a URL that does not belong to any collected source."],
    limitations: [],
    demo_mode: false,
    bibliography: [
      {
        number: 1, source_id: "W-1", kind: "web", title: "License guide", url: "https://example.org/license",
        document_id: null, page_number: null, content_kind: "snippet", published_date: "2026-01-01",
        retrieved_at: null, possibly_outdated: false,
      },
    ],
  },
};

describe("ReportBody", () => {
  it("renders citations linked to the structured bibliography", () => {
    const { container } = renderWithClient(<ReportBody report={report} />);
    const citation = screen.getByRole("link", { name: "Citation 1" });
    expect(citation).toHaveAttribute("href", "#ref-1");
    expect(container.querySelector("#ref-1")).toHaveTextContent("License guide");
    expect(screen.getByRole("link", { name: /license guide/i })).toHaveAttribute("rel", "noopener noreferrer nofollow");
    expect(screen.queryByText(/Should not be rendered/)).not.toBeInTheDocument();
  });

  it("sanitizes model output", () => {
    const { container } = renderWithClient(<ReportBody report={report} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img[onerror]")).toBeNull();
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });

  it("warns about partial evidence and citation adjustments", () => {
    renderWithClient(<ReportBody report={report} />);
    expect(screen.getByText(/partial report/i)).toBeInTheDocument();
    expect(screen.getByText(/does not belong to any collected source/)).toBeInTheDocument();
    expect(screen.getByText(/model inference, not directly sourced/)).toBeInTheDocument();
  });

  it("strips only the bibliography section", () => {
    expect(stripBibliography("a\n## Bibliography\n1. x")).toBe("a");
  });
});
