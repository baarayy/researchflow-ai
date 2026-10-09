"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

import { useDocuments } from "./use-documents";

/** Choose which ready documents a research session may search. `null` means all of them. */
export function DocumentPicker({
  value,
  onChange,
}: {
  value: string[] | null;
  onChange: (ids: string[] | null) => void;
}) {
  const { data } = useDocuments();
  const ready = (data?.items ?? []).filter((d) => d.status === "ready");
  if (ready.length === 0) {
    return <p className="text-xs text-muted-foreground">No indexed documents. Upload some in the library.</p>;
  }
  const selected = value ?? ready.map((d) => d.id);
  const toggle = (id: string, checked: boolean) => {
    const next = checked ? [...selected, id] : selected.filter((x) => x !== id);
    onChange(next.length === ready.length ? null : next);
  };
  return (
    <fieldset className="space-y-2">
      <legend className="text-xs text-muted-foreground">Documents to search</legend>
      {ready.map((d) => (
        <div key={d.id} className="flex items-center gap-2">
          <Checkbox
            id={`doc-${d.id}`}
            checked={selected.includes(d.id)}
            onCheckedChange={(c) => toggle(d.id, c === true)}
          />
          <Label htmlFor={`doc-${d.id}`} className="truncate text-sm font-normal">
            {d.filename}
          </Label>
        </div>
      ))}
    </fieldset>
  );
}
