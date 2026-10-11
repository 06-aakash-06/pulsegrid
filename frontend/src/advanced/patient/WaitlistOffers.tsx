import { useEffect, useState } from "react";
import { PatientGate, usePagedItems, usePatientAccess } from "./hooks";
import { formatTime, getErrorMessage, idempotencyRecovery, newIdempotencyKey, sendCommand } from "./api";

interface Offer {
  id: string; entry_id: string; slot_id: string; patient_id: string;
  state: "pending" | "accepted" | "declined" | "expired" | "revoked";
  expires_at: string; appointment_id: string | null; version: number;
}
interface Attempt { offer: Offer; action: "accept" | "decline"; key: string }

export function WaitlistOffers() {
  const { api, gate } = usePatientAccess();
  const list = usePagedItems<Offer>(api, "/api/v1/appointments/waitlist-offers?limit=100", gate === "ready");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null), [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(Date.now()); if (!document.hidden && !busy && !attempt) list.reload();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [busy, attempt, list.reload]);
  async function submit(command: Attempt) {
    setAttempt(command); setBusy(true); setError(null);
    try {
      const response = await sendCommand<Offer | { offer: Offer; appointment: { id: string } }>(api,
        `/api/v1/appointments/waitlist-offers/${command.offer.id}/${command.action}`, {},
        { ifMatch: `"${command.offer.version}"` }, command.key);
      setReceipt("appointment" in response.data ? `Booking confirmed: appointment ${response.data.appointment.id}.`
        : `Offer ${response.data.state}.`);
      setAttempt(null); list.reload();
    } catch (failure) {
      setError(getErrorMessage(failure));
      if (!idempotencyRecovery(failure)) { setAttempt(null); list.reload(); }
    } finally { setBusy(false); }
  }
  if (gate !== "ready") return <PatientGate state={gate} />;
  return <section className="patient-workflow__panel">
    <h2>Temporary slot offers</h2><p>An offer holds a slot until the expiry shown. The service confirms acceptance and releases declined or expired offers.</p>
    {list.error && <p role="alert">{list.error}</p>}{error && <p role="alert">{error}</p>}
    {receipt && <p role="status">{receipt}</p>}
    {list.items.map(offer => <article key={offer.id}>
      <p>Slot {offer.slot_id} — {offer.state}. Expires {formatTime(offer.expires_at)}.</p>
      {offer.state === "pending" && Date.parse(offer.expires_at) > clock && <>
        <button disabled={busy || !!attempt} onClick={() => void submit({ offer, action: "accept", key: newIdempotencyKey() })}>Accept slot offer</button>
        <button disabled={busy || !!attempt} onClick={() => void submit({ offer, action: "decline", key: newIdempotencyKey() })}>Decline slot offer</button>
      </>}
      {offer.state === "pending" && Date.parse(offer.expires_at) <= clock && <p>Offer deadline passed; awaiting the service's expiry update.</p>}
    </article>)}
    {attempt && !busy && <button onClick={() => void submit(attempt)}>Retry original offer command</button>}
    <button disabled={busy} onClick={list.reload}>Refresh offers</button>
    {list.nextCursor && <button onClick={() => void list.loadMore()}>Load more offers</button>}
  </section>;
}
