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
        <StatusBadge>Integration pending</StatusBadge>
      </div>
      <EmptyState title="No service data is connected" message={page.emptyMessage} />
    </div>
  );
}
