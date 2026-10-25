import { MoreActions } from "../../components/PageTools";
import { useState } from "react";
import { useAuth } from "../../auth/authContext";
import { WorkflowHistory } from "../../advanced/shared/WorkflowHistory";
import { ApiError } from "../../api/client";
import type { QueueEntry } from "./contracts";
import { errorMessage, idempotencyKey } from "./utils";

export function QueueTransitions({ entry, refresh }: { entry: QueueEntry; refresh: () => void }) {
  const { api } = useAuth();
  const [showReason, setShowReason] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState(false);
  const [attempt, setAttempt] = useState<{ action: "skip" | "recall"; key: string; version: number; reason: string } | null>(null);
  async function submit(command: NonNullable<typeof attempt>) {
    setAttempt(command); setBusy(true); setError("");
    try {
      await api.requestWithMetadata(`/api/v1/appointments/queue-entries/${entry.id}/${command.action}`,
        { method: "POST", body: { reason: command.reason }, ifMatch: `"${command.version}"`, idempotencyKey: command.key });
      setAttempt(null); setReason(""); refresh();
    } catch (failure) {
      setError(errorMessage(failure));
      if (failure instanceof ApiError && failure.status > 0 && failure.status < 500) { setAttempt(null); refresh(); }
    } finally { setBusy(false); }
  }
  const action = entry.state === "waiting" ? "skip" : "recall";
  return <div>
    {(entry.state === "waiting" || entry.state === "skipped") && <>
      {!showReason && <button type="button" onClick={()=>setShowReason(true)}>{action === "skip" ? "Skip" : "Recall"}</button>}
      {showReason && <label>Queue action reason<input value={reason} placeholder="Why is this patient being skipped or recalled?" maxLength={500} onChange={event => setReason(event.target.value)} /></label>}
      <span hidden={!showReason}>
      <button disabled={busy || !!attempt || !reason.trim()} onClick={() => void submit({ action, key: idempotencyKey(), version: entry.version, reason: reason.trim() })}>
        {action === "skip" ? "Skip patient" : "Recall patient"}</button></span>
    </>}
    {error && <p role="alert">{error}</p>}
    {attempt && !busy && <button onClick={() => void submit(attempt)}>Retry original queue command</button>}
    <MoreActions><button onClick={() => setHistory(!history)}>Queue history</button>
    {history && <WorkflowHistory path={`/api/v1/appointments/queue-entries/${entry.id}/history`} />}</MoreActions>
  </div>;
}
