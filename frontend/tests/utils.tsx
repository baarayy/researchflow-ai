import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

export function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <TooltipProvider>{ui}</TooltipProvider>
      </QueryClientProvider>,
    ),
  };
}

/** Route fetch() calls by "METHOD path" → JSON body (or a function of the request). */
export function mockFetch(routes: Record<string, unknown | ((init?: RequestInit) => unknown)>) {
  const calls: { method: string; path: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const path = url.pathname.replace("/api/v1", "") + url.search;
    calls.push({ method, path, init });
    const key = Object.keys(routes).find((k) => k === `${method} ${path}` || k === `${method} ${url.pathname.replace("/api/v1", "")}`);
    if (!key) return new Response(JSON.stringify({ error: { code: "not_found", message: "not mocked" } }), { status: 404 });
    const value = routes[key];
    const body = typeof value === "function" ? (value as (i?: RequestInit) => unknown)(init) : value;
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}
