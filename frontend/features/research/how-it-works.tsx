import { BrainCircuit, FileSearch, Hand, ListChecks, Scale, ScrollText } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STEPS = [
  { Icon: ListChecks, title: "Plan", text: "The question is split into focused subquestions you can review." },
  { Icon: FileSearch, title: "Research", text: "Web search and document retrieval run in parallel per subquestion." },
  { Icon: BrainCircuit, title: "Analyze", text: "Claims are extracted and kept linked to the exact source." },
  { Icon: Scale, title: "Critique", text: "A critic checks coverage; gaps trigger another bounded iteration." },
  { Icon: Hand, title: "Approve", text: "Optional human checkpoints pause the workflow durably." },
  { Icon: ScrollText, title: "Report", text: "Citations are validated against the evidence registry." },
];

export function HowItWorks() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>How it works</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3">
          {STEPS.map(({ Icon, title, text }) => (
            <li key={title} className="flex gap-3">
              <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
              <p className="text-sm">
                <span className="font-medium">{title}.</span> <span className="text-muted-foreground">{text}</span>
              </p>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
