import { useEffect, useState, type FormEvent } from "react";
import { DepartmentIcon } from "../../design/DepartmentIcon";
import {
  buildQuery,
  formatTime,
  getErrorMessage,
  idempotencyRecovery,
  newIdempotencyKey,
  sendCommand,
} from "./api";
import { PatientGate, useLoad, usePagedItems, usePatientAccess } from "./hooks";
import type {
  Fulfillment,
  PatientProfile,
  Prescription,
  Reservation,
} from "./contracts";
import "./patient.css";

interface ReserveLine {
  prescription_item_id: string;
  quantity: number;
}

interface ReservationAttempt {
  body: { prescription_id: string; items: ReserveLine[] };
  key: string;
}

function ReservationStatus({
  api,
  profile,
  prescription,
  compact = false,
  onLockChange,
}: {
  api: ReturnType<typeof usePatientAccess>["api"];
  profile: PatientProfile;
  prescription: Prescription;
  compact?: boolean;
  onLockChange?: (locked: boolean) => void;
}) {
  const fulfillment = useLoad<Fulfillment>(
    api,
    `/api/v1/pharmacy/prescriptions/${prescription.id}/fulfillment`,
    true,
  );
  const reservationPath = buildQuery("/api/v1/pharmacy/reservations", {
    patient_id: profile.id,
    prescription_id: prescription.id,
    limit: "100",
  });
  const reservations = usePagedItems<Reservation>(api, reservationPath, true);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<ReservationAttempt | null>(null);
  const [created, setCreated] = useState<Reservation | null>(null);
  useEffect(() => { onLockChange?.(pending || !!attempt); }, [pending, attempt, onLockChange]);

  async function reserve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setCreated(null);
    if (!fulfillment.data || fulfillment.error) {
      setError("Load the current pharmacy fulfillment snapshot before requesting a reservation.");
      return;
    }
    if (fulfillment.data.prescription_state !== "issued" || fulfillment.data.review_required) {
      setError("This prescription is revoked or flagged for review. A new reservation cannot be requested.");
      return;
    }

    let currentAttempt = attempt;
    if (!currentAttempt) {
      try {
        const items = fulfillment.data.items.flatMap((item) => {
          const raw = (quantities[item.prescription_item_id] ?? "").trim();
          if (!raw) return [];
          if (!/^[1-9][0-9]*$/.test(raw)) {
            throw new Error(`Quantity for prescription item ${item.prescription_item_id} must be a positive whole number.`);
          }
          const quantity = Number(raw);
          const available = item.prescribed_quantity - item.dispensed_quantity - item.reserved_quantity;
          if (!Number.isSafeInteger(quantity) || quantity > available) {
            throw new Error(`Quantity for prescription item ${item.prescription_item_id} exceeds the current unreserved allowance (${Math.max(0, available)}).`);
          }
          return [{ prescription_item_id: item.prescription_item_id, quantity }];
        });
        if (items.length < 1 || items.length > 50) {
          throw new Error("Choose at least one prescribed item to request from Pharmacy.");
        }
        currentAttempt = {
          body: { prescription_id: prescription.id, items },
          key: newIdempotencyKey(),
        };
        setAttempt(currentAttempt);
      } catch (reason) {
        setError(getErrorMessage(reason));
        return;
      }
    }
    if (!currentAttempt) return;

    setPending(true);
    try {
      const response = await sendCommand<Reservation>(
        api,
        "/api/v1/pharmacy/reservations",
        currentAttempt.body,
        {},
        currentAttempt.key,
      );
      setCreated(response.data);
      setAttempt(null);
      setQuantities({});
      fulfillment.reload();
      reservations.reload();
    } catch (reason) {
      setError(getErrorMessage(reason));
      if (!idempotencyRecovery(reason)) setAttempt(null);
    } finally {
      setPending(false);
    }
  }

  const isIssued = prescription.state === "issued" && fulfillment.data?.prescription_state === "issued";
  const allDispensed = !!fulfillment.data && fulfillment.data.items.length > 0 && fulfillment.data.items.every(
    (item) => item.dispensed_quantity === item.prescribed_quantity,
  );
  const HistorySection = compact ? "details" : "section";

  return (
    <article className="patient-workflow__item" aria-labelledby={`fulfillment-${prescription.id}`}>
      <h3 id={`fulfillment-${prescription.id}`}>Prescription {compact ? `…${prescription.id.slice(-4)}` : prescription.id}</h3>
      <p>Prescription status: <strong>{prescription.state}</strong> · Revision {prescription.revision}</p>
      {fulfillment.loading && <p role="status">Loading current Pharmacy summary…</p>}
      {fulfillment.error && <div role="alert"><p>{fulfillment.error}</p><button type="button" onClick={fulfillment.reload}>Retry fulfillment status</button></div>}
      {fulfillment.data && <>
        <dl className="patient-workflow__facts">
          <div><dt>Appointment</dt><dd>{compact ? `Visit …${fulfillment.data.appointment_id.slice(-4)}` : fulfillment.data.appointment_id}</dd></div>
          <div><dt>Prescription source revision</dt><dd>{fulfillment.data.prescription_revision}</dd></div>
          <div><dt>Fulfillment status</dt><dd>{fulfillment.data.review_required ? "Review required" : allDispensed ? "All prescribed quantities dispensed" : fulfillment.data.prescription_state === "revoked" ? "Revoked" : "In progress"}</dd></div>
          <div><dt>Snapshot observed</dt><dd><time dateTime={fulfillment.data.observed_at}>{formatTime(fulfillment.data.observed_at)}</time></dd></div>
        </dl>
        {compact ? <div className="pharmacy-allowance-table" tabIndex={0} role="region" aria-label="Prescribed medicine quantities"><table><thead><tr><th scope="col">Medicine</th><th scope="col">Prescribed</th><th scope="col">Reserved</th><th scope="col">Dispensed</th></tr></thead><tbody>{fulfillment.data.items.map(item=><tr key={item.prescription_item_id}><th scope="row"><PrescribedMedicineName api={api} medicineId={item.medicine_id}/></th><td>{item.prescribed_quantity}</td><td>{item.reserved_quantity}</td><td>{item.dispensed_quantity}</td></tr>)}</tbody></table></div> : fulfillment.data.items.map((item) => {
          const available = Math.max(0, item.prescribed_quantity - item.dispensed_quantity - item.reserved_quantity);
          return <div className="patient-workflow__item" key={item.prescription_item_id}>
            <h4>Prescription item {item.prescription_item_id}</h4>
            <dl className="patient-workflow__facts">
              <div><dt>Medicine ID</dt><dd>{item.medicine_id}</dd></div>
              <div><dt>Prescribed</dt><dd>{item.prescribed_quantity}</dd></div>
              <div><dt>Reserved</dt><dd>{item.reserved_quantity}</dd></div>
              <div><dt>Dispensed</dt><dd>{item.dispensed_quantity}</dd></div>
              <div><dt>Remaining, including reserved</dt><dd>{item.remaining_quantity}</dd></div>
              <div><dt>Currently available to reserve</dt><dd>{available}</dd></div>
            </dl>
          </div>;
        })}
        {fulfillment.data.review_required && <p role="alert">Pharmacy reports a review requirement. This panel cannot clear it.</p>}
      </>}

      {isIssued && fulfillment.data && <form onSubmit={(event) => void reserve(event)} noValidate>
        <fieldset disabled={pending || !!attempt || fulfillment.data.review_required}>
          <legend>Request a Pharmacy reservation</legend>
          {fulfillment.data.items.map((item) => {
            const available = Math.max(0, item.prescribed_quantity - item.dispensed_quantity - item.reserved_quantity);
            return <label key={item.prescription_item_id} htmlFor={`reserve-${prescription.id}-${item.prescription_item_id}`}>
              Item {item.prescription_item_id} quantity (up to {available})
              <input
                id={`reserve-${prescription.id}-${item.prescription_item_id}`}
                inputMode="numeric"
                min={1}
                max={available}
                value={quantities[item.prescription_item_id] ?? ""}
                onChange={(event) => setQuantities((current) => ({ ...current, [item.prescription_item_id]: event.target.value }))}
                aria-describedby={`reserve-help-${prescription.id}-${item.prescription_item_id}`}
              />
              <span className="patient-workflow__hint" id={`reserve-help-${prescription.id}-${item.prescription_item_id}`}>Leave blank to omit this item. Stock and allowance are rechecked by Pharmacy.</span>
            </label>;
          })}
        </fieldset>
        <button type="submit" disabled={pending || fulfillment.data.items.every((item) => item.prescribed_quantity - item.dispensed_quantity - item.reserved_quantity <= 0)}>
          {pending ? "Submitting…" : attempt ? "Retry reservation request" : "Request reservation"}
        </button>
        {attempt && <p role="status">The response was uncertain. Retry uses the same idempotency key and quantities.</p>}
      </form>}
      {error && <p role="alert">{error}</p>}
      {created && <p role="status">Pharmacy returned reservation {created.id}, state {created.state}, expiring <time dateTime={created.expires_at}>{formatTime(created.expires_at)}</time>.</p>}

      <HistorySection aria-label={`Reservation status for prescription ${prescription.id}`}>
        {compact ? <summary>Reservations</summary> : <h4>Reservations</h4>}
        {reservations.loading && <p role="status">Loading reservation records…</p>}
        {reservations.error && <div role="alert"><p>{reservations.error}</p><button type="button" onClick={reservations.reload}>Retry reservation records</button></div>}
        {reservations.items.length === 0 && !reservations.error && !reservations.loading && <p>No reservation records were returned.</p>}
        {reservations.items.map((reservation) => <dl className="patient-workflow__facts" key={reservation.id}>
          <div><dt>Reservation</dt><dd>{reservation.id}</dd></div>
          <div><dt>Status</dt><dd>{reservation.state}</dd></div>
          <div><dt>Expires</dt><dd><time dateTime={reservation.expires_at}>{formatTime(reservation.expires_at)}</time></dd></div>
          <div><dt>Items</dt><dd>{reservation.items.map((item) => `${item.prescription_item_id}: ${item.quantity}`).join(", ")}</dd></div>
        </dl>)}
        {reservations.nextCursor && <button type="button" disabled={reservations.loadingMore} onClick={() => void reservations.loadMore()}>{reservations.loadingMore ? "Loading reservations…" : "Load more reservations"}</button>}
        {reservations.loadMoreError && <div role="alert"><p>{reservations.loadMoreError}</p><button type="button" onClick={() => void reservations.loadMore()}>Retry loading reservations</button></div>}
      </HistorySection>

      <HistorySection aria-label={`Dispensing status for prescription ${prescription.id}`}>
        {compact ? <summary>Dispensing status</summary> : <h4>Dispensing status</h4>}
        {fulfillment.loading && <p role="status">Loading dispensing status…</p>}
        {fulfillment.data?.dispensings.length === 0 && !fulfillment.error && !fulfillment.loading && <p>No dispensing records were returned.</p>}
        {fulfillment.data?.dispensings.map((dispensing) => <p key={dispensing.id}>
          Dispensing {dispensing.id}, version {dispensing.version}; source item IDs {dispensing.source_item_ids.length ? dispensing.source_item_ids.join(", ") : "none reported"}.
        </p>)}
        {fulfillment.data?.items.some((item) => item.reserved_quantity > 0) && <p>Reserved quantities are not counted as dispensed.</p>}
      </HistorySection>
    </article>
  );
}

function PrescribedMedicineName({api,medicineId}:{api:ReturnType<typeof usePatientAccess>["api"];medicineId:string}) {
  const medicine=useLoad<{name:string}>(api,`/api/v1/pharmacy/medicines/${medicineId}`,true);
  return <span>{typeof medicine.data?.name === "string" && !medicine.data.name.startsWith("Synthetic") ? medicine.data.name : `Catalog item …${medicineId.slice(-4)}`}</span>;
}

export function PatientFulfillmentPanel({ counter = false }: { counter?: boolean }) {
  const { api, gate } = usePatientAccess();
  const profile = useLoad<PatientProfile>(api, gate === "ready" ? "/api/v1/patients/me" : null, gate === "ready");
  const prescriptionsPath = profile.data
    ? buildQuery("/api/v1/records/prescriptions", { patient_id: profile.data.id, limit: "20" })
    : null;
  const prescriptions = usePagedItems<Prescription>(api, prescriptionsPath, gate === "ready" && !!profile.data);
  const [selectedId,setSelectedId]=useState("");
  const [selectionLocked,setSelectionLocked]=useState(false);
  const selected=prescriptions.items.find(item=>item.id===selectedId) ?? prescriptions.items[0];
  if (gate !== "ready") return <PatientGate state={gate} />;
  if (counter) return <div className="pharmacy-prescription-desk">
    <section className="prescription-stand" aria-labelledby="patient-prescription-stand-title">
      <header><DepartmentIcon department="records"/><h2 id="patient-prescription-stand-title">Patient & Prescription</h2><span aria-hidden="true">Rx</span></header>
      <p>{profile.data?.display_name?.startsWith("Synthetic") ? "Your patient account" : profile.data?.display_name ?? "Your patient account"}</p>
      {profile.loading && <p role="status">Loading your profile…</p>}
      {profile.error && <div role="alert"><p>{profile.error}</p><button type="button" onClick={profile.reload}>Retry profile</button></div>}
      {prescriptions.loading && <p role="status">Loading your prescriptions…</p>}
      {prescriptions.error && <div role="alert"><p>{prescriptions.error}</p><button type="button" onClick={prescriptions.reload}>Retry prescriptions</button></div>}
      {!prescriptions.loading && !prescriptions.error && prescriptions.items.length===0 && <p>No prescriptions were returned for this patient.</p>}
      {selected && <><label htmlFor="counter-prescription">Your prescription</label><select id="counter-prescription" value={selected.id} disabled={selectionLocked} onChange={event=>setSelectedId(event.target.value)}>{prescriptions.items.map(item=><option key={item.id} value={item.id}>Prescription …{item.id.slice(-4)} · {item.state}</option>)}</select>
        <p className="prescription-source-line">Records · {selected.state} · Revision {selected.revision}</p>
        {selected.state==="revoked" && <p className="prescription-revoked-note">Revoked prescription. Instructions are retained as history.</p>}
        <div className="prescribed-document-lines">{selected.items.map(item=><article key={item.id}><strong><PrescribedMedicineName api={api} medicineId={item.medicine_id}/></strong><span>Quantity {item.quantity}</span><p>{item.dosage}</p><p>{item.instructions}</p></article>)}</div>
        <details className="owner-identifiers"><summary>Prescription references</summary>Prescription {selected.id} · Consultation {selected.consultation_id}</details></>}
      {prescriptions.nextCursor && <button type="button" disabled={prescriptions.loadingMore||selectionLocked} onClick={()=>void prescriptions.loadMore()}>Load more prescriptions</button>}
      {prescriptions.loadMoreError && <div role="alert"><p>{prescriptions.loadMoreError}</p><button type="button" disabled={selectionLocked} onClick={()=>void prescriptions.loadMore()}>Retry loading prescriptions</button></div>}
    </section>
    <aside className="patient-dispensing-workspace" aria-label="Prescription and Pharmacy status"><h2>Pharmacy fulfillment</h2><p>Reservations and dispensing are confirmed by Pharmacy.</p>{selected && profile.data ? <ReservationStatus key={`${selected.id}:${selected.revision}`} api={api} profile={profile.data} prescription={selected} compact onLockChange={setSelectionLocked}/> : <p>Choose one of your prescriptions to see its fulfillment and permitted actions.</p>}</aside>
  </div>;
  return <section className="patient-workflow__panel" aria-labelledby="patient-fulfillment-title">
    <h2 id="patient-fulfillment-title">Prescription and Pharmacy status</h2>
    <p>Prescription authority stays with Records; Pharmacy confirms reservations and dispensing. A reservation does not count as dispensed.</p>
    {profile.loading && <p role="status">Loading your profile…</p>}
    {profile.error && <div role="alert"><p>{profile.error}</p><button type="button" onClick={profile.reload}>Retry profile</button></div>}
    {prescriptions.loading && <p role="status">Loading your prescriptions…</p>}
    {prescriptions.error && <div role="alert"><p>{prescriptions.error}</p><button type="button" onClick={prescriptions.reload}>Retry prescriptions</button></div>}
    {!prescriptions.loading && !prescriptions.error && prescriptions.items.length === 0 && <p>No prescriptions were returned for this patient.</p>}
    {profile.data && prescriptions.items.map((prescription) => <ReservationStatus
      key={`${prescription.id}:${prescription.revision}`}
      api={api}
      profile={profile.data!}
      prescription={prescription}
    />)}
    {prescriptions.nextCursor && <button type="button" disabled={prescriptions.loadingMore} onClick={() => void prescriptions.loadMore()}>{prescriptions.loadingMore ? "Loading prescriptions…" : "Load more prescriptions"}</button>}
    {prescriptions.loadMoreError && <div role="alert"><p>{prescriptions.loadMoreError}</p><button type="button" onClick={() => void prescriptions.loadMore()}>Retry loading prescriptions</button></div>}
  </section>;
}
