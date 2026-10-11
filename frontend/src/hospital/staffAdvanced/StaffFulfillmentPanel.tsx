import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/authContext";
import { Fulfillment as ExistingFulfillment } from "../pharmacy";
import { Collection, Panel, query } from "../ui";
import type { Batch, Fulfillment, Prescription } from "./contracts";
import { StaffRoleGate } from "./StaffRoleGate";
import "./staffAdvanced.css";
import { errorMessage, id, scheduleLocalTime } from "./utils";

function FulfillmentStatusLookup() {
  const { api } = useAuth();
  const [draft, setDraft] = useState("");
  const [prescriptionId, setPrescriptionId] = useState<string | null>(null);
  const [fulfillment, setFulfillment] = useState<Fulfillment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function load(value = draft) {
    let selectedId: string;
    try {
      selectedId = id(value);
    } catch (validationError) {
      setError(validationError instanceof Error ? validationError.message : "Enter a valid prescription ID.");
      return;
    }
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setPrescriptionId(selectedId);
    setFulfillment(null);
    setLoading(true);
    setError("");
    try {
      const prescriptionResponse = await api.requestWithMetadata<Prescription>(
        `/api/v1/records/prescriptions/${selectedId}`,
        { signal: controller.signal },
      );
      if (prescriptionResponse.data.id !== selectedId || !["issued", "revoked"].includes(prescriptionResponse.data.state)) {
        throw new Error("Records returned an invalid prescription summary. Reload before acting.");
      }
      const response = await api.requestWithMetadata<Fulfillment>(
        `/api/v1/pharmacy/prescriptions/${selectedId}/fulfillment`,
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      if (
        response.data.prescription_id !== selectedId ||
        response.data.prescription_state !== prescriptionResponse.data.state ||
        response.data.prescription_revision !== prescriptionResponse.data.revision
      ) {
        throw new Error("Records and Pharmacy returned different prescription revisions. Reload and review before dispensing.");
      }
      setFulfillment(response.data);
      setDraft(selectedId);
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setError(errorMessage(requestError));
        setFulfillment(null);
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <Panel title="Prescription fulfillment status">
      <p>
        Enter a prescription ID. The Records owner confirms its current state before Pharmacy returns reservation, dispensing and review status. This summary does not display diagnosis or dosage text.
      </p>
      <form className="hospital-form" noValidate onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <label>
          Prescription ID for fulfillment status
          <input value={draft} onChange={(event) => {
            const value = event.target.value;
            setDraft(value);
            if (value !== prescriptionId) {
              activeRequest.current?.abort();
              setPrescriptionId(null);
              setFulfillment(null);
              setError("");
              setLoading(false);
            }
          }} inputMode="numeric" autoComplete="off" disabled={loading} />
        </label>
        <button type="submit" disabled={loading}>{loading ? "Loading fulfillment…" : "Load fulfillment status"}</button>
        {prescriptionId && (
          <button type="button" disabled={loading} onClick={() => { setRefreshVersion((value) => value + 1); void load(prescriptionId); }}>
            Refresh fulfillment status
          </button>
        )}
      </form>
      {loading && <p role="status">Checking Records and Pharmacy…</p>}
      {error && <p role="alert">{error}</p>}
      {fulfillment && (
        <div className="staff-advanced-summary" key={`${fulfillment.prescription_id}:${fulfillment.version}:${refreshVersion}`}>
          <h3>Prescription {fulfillment.prescription_id}</h3>
          <p>Prescription state: {fulfillment.prescription_state} • Snapshot version {fulfillment.version}</p>
          <p>Observed (UTC): {scheduleLocalTime(fulfillment.observed_at)}</p>
          <p role={fulfillment.review_required ? "alert" : "status"}>
            {fulfillment.review_required ? "Pharmacy review is required before the journey can be discharged." : "No Pharmacy review flag is reported in this snapshot."}
          </p>
          {fulfillment.items.length === 0 ? (
            <p>No fulfillment items were returned.</p>
          ) : (
            <ul className="staff-advanced-summary-list">
              {fulfillment.items.map((item) => (
                <li className="staff-advanced-summary" key={item.prescription_item_id}>
                  Prescription item {item.prescription_item_id} • medicine {item.medicine_id}
                  <p>Prescribed {item.prescribed_quantity}; reserved {item.reserved_quantity}; dispensed {item.dispensed_quantity}; remaining {item.remaining_quantity}.</p>
                </li>
              ))}
            </ul>
          )}
          <h4>Reservations</h4>
          {fulfillment.reservations.length ? (
            <ul>{fulfillment.reservations.map((reservation) => <li key={reservation.id}>Reservation {reservation.id}: {reservation.state}, version {reservation.version}</li>)}</ul>
          ) : <p>No reservations are reported.</p>}
          <h4>Dispensings</h4>
          {fulfillment.dispensings.length ? (
            <ul>{fulfillment.dispensings.map((dispensing) => <li key={dispensing.id}>Dispensing {dispensing.id}, version {dispensing.version}; source item IDs {dispensing.source_item_ids.join(", ") || "none"}</li>)}</ul>
          ) : <p>No completed dispensings are reported.</p>}
        </div>
      )}
    </Panel>
  );
}

function StockVerification() {
  const [medicineId, setMedicineId] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  return (
    <Panel title="Verify available stock">
      <p>Stock is an owner snapshot. Pharmacy checks stock again during reservation; this view does not guarantee a later reservation.</p>
      <form className="hospital-form" noValidate onSubmit={(event) => {
        event.preventDefault();
        try {
          const selectedId = id(draft);
          setMedicineId(selectedId);
          setDraft(selectedId);
          setError("");
        } catch (validationError) {
          setError(validationError instanceof Error ? validationError.message : "Enter a valid medicine ID.");
        }
      }}>
        <label>
          Medicine ID
          <input value={draft} onChange={(event) => {
            setDraft(event.target.value);
            setMedicineId("");
            setError("");
          }} inputMode="numeric" autoComplete="off" />
        </label>
        <button type="submit">Check stock</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <Collection<Batch>
        title="Stock batches"
        path={medicineId ? query("/api/v1/pharmacy/inventory", { medicine_id: medicineId }) : null}
        renderItem={(batch) => (
          <>
            <strong>Batch {batch.batch_code}</strong>
            <p>Medicine {batch.medicine_id} • expiry {batch.expires_on}</p>
            <p>On hand {batch.on_hand}; reserved {batch.reserved}; available {batch.available}; version {batch.version}.</p>
          </>
        )}
      />
    </Panel>
  );
}

export function StaffFulfillmentPanel() {
  return (
    <StaffRoleGate role="pharmacist">
      <div className="staff-advanced-page">
        <FulfillmentStatusLookup />
        <StockVerification />
        <ExistingFulfillment pharmacist />
      </div>
    </StaffRoleGate>
  );
}
