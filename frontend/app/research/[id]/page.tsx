import { Suspense } from "react";

import { ResearchWorkspace, WorkspaceSkeleton } from "@/features/research/research-workspace";

export default function ResearchPage() {
  // With cacheComponents, request-time params must be read inside a Suspense boundary.
  return (
    <Suspense fallback={<WorkspaceSkeleton />}>
      <ResearchWorkspace />
    </Suspense>
  );
}
