import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  message: string;
  action?: ReactNode;
}

export function EmptyState({ title, message, action }: EmptyStateProps) {
  return (
    <section className="empty-state" aria-labelledby="empty-state-title">
      <span className="empty-state-mark" aria-hidden="true">—</span>
      <div>
        <h2 id="empty-state-title">{title}</h2>
        <p>{message}</p>
        {action ? <div className="empty-state-action">{action}</div> : null}
      </div>
    </section>
  );
}
