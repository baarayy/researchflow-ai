import { DocumentLibrary } from "@/features/documents/document-library";

export default function DocumentsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Uploaded files are validated, split into page-aware chunks, embedded and stored in pgvector. Deleting a
          document also deletes its chunks and embeddings.
        </p>
      </div>
      <DocumentLibrary />
    </div>
  );
}
