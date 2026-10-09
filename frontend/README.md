# ResearchFlow AI — frontend

Next.js (App Router, `cacheComponents`) + TypeScript (strict) + Tailwind v4 + shadcn/ui + TanStack Query.
See the [root README](../README.md) for setup. Feature code lives in `features/` (`research`, `documents`, `sessions`);
live progress comes from the backend's SSE event log via `hooks/use-research-events.ts`.

```bash
npm run dev        # http://localhost:3000 (expects the API at NEXT_PUBLIC_API_BASE_URL)
npm test           # Vitest + Testing Library
npm run lint && npm run typecheck
```
