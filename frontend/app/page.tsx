import { DocumentLibrary } from "@/features/documents/document-library";
import { HowItWorks } from "@/features/research/how-it-works";
import { NewResearchForm } from "@/features/research/new-research-form";
import { SessionList, WorkflowStatusCard } from "@/features/sessions/session-list";

export default function DashboardPage() {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="min-w-0 space-y-6 lg:col-span-2">
        <NewResearchForm />
        <SessionList />
      </div>
      <div className="min-w-0 space-y-6">
        <WorkflowStatusCard />
        <DocumentLibrary compact />
        <HowItWorks />
      </div>
    </div>
  );
}
