import { PageRefresh } from "../../components/PageTools";
import { useAuth } from "../../auth/authContext";
import { usePagedItems } from "../patient/hooks";
import { formatTime } from "../patient/api";

interface Transition { id: string; stage?: string | null; from_state: string | null; to_state: string; occurred_at: string }
export function WorkflowHistory({ path }: { path: string }) {
  const { api } = useAuth();
  const history = usePagedItems<Transition>(api, `${path}?limit=20`, true);
  return <section><h3>Timestamped workflow history</h3>
    {history.error && <p role="alert">{history.error}</p>}
    <ol>{history.items.map(item => <li key={item.id}>{item.stage ? `${item.stage}: ` : ""}
      {item.from_state ?? "created"} → {item.to_state} — {formatTime(item.occurred_at)}</li>)}</ol>
    <PageRefresh onClick={history.reload}>Refresh history</PageRefresh>
    {history.nextCursor && <button onClick={() => void history.loadMore()}>Load more history</button>}
  </section>;
}
