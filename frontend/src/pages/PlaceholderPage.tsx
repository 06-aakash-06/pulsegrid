import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import type { WorkspacePage } from "../navigation/workspaces";

interface PlaceholderPageProps {
  page: WorkspacePage;
  workspaceName: string;
}

export function PlaceholderPage({ page, workspaceName }: PlaceholderPageProps) {
  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{workspaceName}</p>
          <h1>{page.title}</h1>
          <p className="page-description">{page.description}</p>
        </div>
        <StatusBadge>Unavailable in Phase 2</StatusBadge>
      </div>
      <EmptyState title="Future workflow unavailable" message="This workflow is deferred. Phase 2 does not implement automatic waitlists, QR check-in, live queues, patient journey automation, insurance, monitoring or administrative settings." />
    </div>
  );
}
