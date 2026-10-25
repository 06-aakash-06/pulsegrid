import { MoreActions, ItemDetails, AdvancedLookup, PageRefresh } from "../components/PageTools";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { MedicineAutocomplete } from "../phase4";
import { useAuth } from "../auth/authContext";
import { useCallback, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PatientFulfillmentPanel } from "../advanced/patient/PatientFulfillmentPanel";
import { MedicineCabinet, PharmacyRoom, availabilityText, medicineLabel, useCursorPage } from "./pharmacyRoom";
import type {
  Batch,
  Dispensing,
  Medicine,
  Prescription,
  Reservation,
} from "./models";
import {
  formatDateTime,
  buildFields,
  Collection,
  CommandForm,
  date,
  Facts,
  FlashArea,
  idField,
  Inputs,
  integer,
  Lookup,
  Panel,
  query,
  reasonField,
  Resource,
  Selected,
  useResource,
  type Field,
  type Values,
} from "./ui";
import { PrescriptionDetail } from "./records";
export function MedicineCatalog({
  staff = false,
  inventory = false,
}: {
  staff?: boolean;
  inventory?: boolean;
}) {
  const { state, api }=useAuth();
  const [draft, setDraft] = useState<Values>({});
  const [filters, setFilters] = useState<Values>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [medicineId, setMedicineId] = useState("");
  const [availability, setAvailability] = useState<Medicine["availability"] | "">("");
  return (
    <div className="pharmacy-catalog"><div className="pharmacy-search-counter">
      <div className="pharmacy-autocomplete"><MedicineAutocomplete api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} label="Quick medicine lookup" placeholder="Search medicines…" onSelect={item => {setSelected(item.id);if(inventory)setMedicineId(item.id);}} /></div>
      <nav className="medicine-availability-tabs" aria-label="Catalog availability on this page">{[["","All medicines"],["available","Available"],["unavailable","Unavailable"],["unknown","Availability not supplied"]].map(([value,label])=><button type="button" key={value} aria-pressed={availability===value} onClick={()=>{setAvailability(value as Medicine["availability"]|"");setSelected(null);}}>{label}</button>)}</nav>
      <details className="pharmacy-catalog-search"><summary>Search & catalog filters</summary>
      <Panel title="Medicine search">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (
              draft.q &&
              (draft.q.trim().length < 2 || draft.q.trim().length > 100)
            ) {
              setError("Search must contain 2 to 100 characters.");
              return;
            }
            setFilters(draft);
            setSelected(null);
            setError("");
          }}
        >
          <Inputs
            fields={[
              { name: "q", label: "Medicine search", max: 100 },
              ...(staff
                ? [
                    {
                      name: "active",
                      label: "Medicine active filter",
                      kind: "select" as const,
                      options: ["true", "false"],
                    },
                  ]
                : []),
            ]}
            values={draft}
            change={(name, value) => setDraft({ ...draft, [name]: value })}
          />
          <button>Search medicines</button>
          {error && <p role="alert">{error}</p>}
        </form>
      </Panel>
      </details>
      </div><div className="pharmacy-shelf-workspace"><div className="medicine-table"><div className="cabinet-signage"><strong>Medicine catalogue</strong><span> · Availability from Pharmacy</span></div>
      <Collection<Medicine>
        title="Medicines"
        path={query("/api/v1/pharmacy/medicines", filters)}
        revision={revision}
        itemFilter={item=>!availability||item.availability===availability}
        onFirstItem={item=>{if(!selected){setSelected(item.id);if(inventory)setMedicineId(item.id);}}}
        renderItem={(item) => (
          <div className="medicine-table-row" data-selected={selected===item.id} data-availability={item.availability}>
            <strong>{item.name.startsWith("Synthetic")?"Medicine":item.name}</strong>
            <ItemDetails>SKU {item.sku}</ItemDetails>
            <span className="owner-state" data-state={item.availability}>{availabilityText[item.availability]}</span>
            <button aria-label={`View medicine ${item.id}`} aria-pressed={selected===item.id} onClick={() => {setSelected(item.id);if(inventory)setMedicineId(item.id);}}>{selected===item.id ? "Selected" : "Select"}</button>
          </div>
        )}
      />
      </div><aside className="dispensing-counter">{!selected && <Panel title="Medicine details"><div className="resource-empty"><DepartmentIcon department="pharmacy"/><strong>Choose a medicine</strong><p>Open a shelf item to review its catalog status. Prescription fulfillment remains a separate authorized workflow.</p></div></Panel>}
      <Selected<Medicine>
        path={selected ? `/api/v1/pharmacy/medicines/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <h2 className="selected-medicine-name">{item.name.startsWith("Synthetic")?"Medicine":item.name}</h2>
            <Facts values={{"Catalog status":item.active?"Active":"Inactive",Availability:availabilityText[item.availability]}}/>
            <ItemDetails><Facts values={{"Medicine ID":item.id,SKU:item.sku}}/></ItemDetails>
            {staff && (<details className="catalog-edit-tools"><summary>Edit selected catalog entry</summary>
              <CommandForm
                title="Save medicine" reviewLabel="Review changes" confirmLabel="Save medicine" successMessage="Medicine saved."
                path={`/api/v1/pharmacy/medicines/${item.id}`}
                method="PATCH"
                conditional
                etag={etag}
                fields={[
                  {
                    name: "name",
                    label: "Medicine name",
                    required: true,
                    max: 200,
                    initial: item.name,
                  },
                  {
                    name: "active",
                    label: "Medicine active",
                    kind: "select",
                    required: true,
                    options: ["true", "false"],
                    initial: String(item.active),
                  },
                ]}
                build={(values) => ({
                  name:
                    values.name.trim() ||
                    (() => {
                      throw new Error("Medicine name is required.");
                    })(),
                  active: values.active === "true",
                })}
                onSuccess={() => {
                  refresh();
                  setRevision((v) => v + 1);
                }}
              />
            </details>)}
          </>
        )}
      </Selected>
      </aside></div>
      {staff && (
        <details className="pharmacy-catalog-tools"><summary>Add catalog medicine</summary><Panel title="New catalog medicine">
          <CommandForm
            title="Create medicine" reviewLabel="Review medicine" confirmLabel="Add medicine" successMessage="Medicine added."
            path="/api/v1/pharmacy/medicines"
            fields={[
              { name: "sku", label: "SKU", required: true, max: 128 },
              {
                name: "name",
                label: "Medicine name",
                required: true,
                max: 200,
              },
            ]}
            onSuccess={() => setRevision((v) => v + 1)}
          />
        </Panel></details>
      )}
      {inventory && (
        <div className="pharmacy-inventory-ledger">
          <AdvancedLookup title="Inventory reference filter"><Lookup
            label="Inventory medicine ID filter"
            onSelect={setMedicineId}
          /></AdvancedLookup>
          <Collection<Batch>
            title="Inventory batches"
            path={query("/api/v1/pharmacy/inventory", {
              medicine_id: medicineId,
            })}
            revision={revision}
            renderItem={(batch) => (
              <><div className="stock-ledger-row"><strong>{batch.batch_code}</strong><time dateTime={batch.expires_on}>{formatDateTime(batch.expires_on, { utc: true, time: false })}</time><span>{batch.on_hand} on hand</span><span>{batch.reserved} reserved</span><strong>{batch.available} available</strong></div><ItemDetails><Facts values={{"Batch ID":batch.id,"Medicine ID":batch.medicine_id,"Batch version":batch.version}}/></ItemDetails></>
            )}
          />
          <details className="pharmacy-stock-tools"><summary>Adjust batch stock</summary><StockAdjustment onSuccess={() => setRevision((v) => v + 1)} /></details>
        </div>
      )}
    </div>
  );
}
export function StockAdjustment({ onSuccess }: { onSuccess: () => void }) {
  const fields: Field[] = [
    idField("medicine_id", "Medicine ID"),
    { name: "batch_code", label: "Batch code", required: true, max: 128 },
    { name: "expires_on", label: "Batch expiry", kind: "date", required: true },
    {
      name: "delta",
      label: "Stock delta (positive or negative)",
      kind: "number",
      required: true,
      min: -1000000,
      max: 1000000,
    },
    {
      name: "expected_batch_version",
      label: "Expected batch version (0 for new batch)",
      kind: "number",
      required: true,
      min: 0,
    },
    reasonField,
  ];
  return (
    <Panel title="Stock adjustment">
      <CommandForm<{ movement_id: string; batch: Batch }>
        title="Adjust stock" reviewLabel="Review stock change" confirmLabel="Adjust stock" successMessage="Stock adjusted."
        path="/api/v1/pharmacy/inventory-adjustments"
        fields={fields}
        build={(values) => {
          const body = buildFields(fields, values);
          if (integer(values.delta, -1000000, 1000000) === 0)
            throw new Error("Stock delta cannot be zero.");
          if (
            values.expected_batch_version === "0" &&
            date(values.expires_on) < new Date().toISOString().slice(0, 10)
          )
            throw new Error("New batches cannot expire before today (UTC).");
          return body;
        }}
        onSuccess={onSuccess}
        notice="Use the displayed batch version for an existing batch. Expiry cannot be changed for an existing batch."
      />
    </Panel>
  );
}
function Reserve({
  prescription,
  onSuccess,
}: {
  prescription: Prescription;
  onSuccess: () => void;
}) {
  const fields: Field[] = prescription.items.map((item) => ({
    name: item.id,
    label: `Quantity for item ${item.id} (medicine ${item.medicine_id}, prescribed ${item.quantity})`,
    kind: "number",
    min: 1,
    max: item.quantity,
  }));
  return (
    <Panel title="Request prescribed medicines">
      <CommandForm
        title="Reserve medicines" reviewLabel="Review reservation" confirmLabel="Reserve medicines" successMessage="Medicines reserved."
        path="/api/v1/pharmacy/reservations"
        fields={fields}
        build={(values) => {
          const items = prescription.items
            .filter((item) => (values[item.id] ?? "").trim())
            .map((item) => ({
              prescription_item_id: item.id,
              quantity: integer(values[item.id], 1, item.quantity),
            }));
          if (!items.length || items.length > 50)
            throw new Error("Request at least one prescribed item.");
          return { prescription_id: prescription.id, items };
        }}
        notice="Leave unrequested items blank. Reservations last 30 minutes; Pharmacy validates remaining prescription allowance and stock."
        onSuccess={onSuccess}
      />
    </Panel>
  );
}
function PrescriptionLookupStand({ onLookup, children }: { onLookup: (id: string) => void; children?: ReactNode }) {
  return (<AdvancedLookup title="Open a prescription">
    <section className="prescription-stand" aria-labelledby="pharmacist-prescription-stand-title">
      <header><DepartmentIcon department="records" /><h2 id="pharmacist-prescription-stand-title">Prescription counter</h2><span aria-hidden="true">Rx</span></header>
      <p>Enter a Records prescription ID to place it on the counter.</p>
      <div data-rx-primary><Lookup label="Prescription ID" onSelect={onLookup} /></div>
      {children}
    </section>
  </AdvancedLookup>);
}
function PrescriptionPaper({ prescriptionId, children }: { prescriptionId: string | null; children?: (prescription: Prescription) => ReactNode }) {
  const prescription = useResource<Prescription>(prescriptionId ? `/api/v1/records/prescriptions/${prescriptionId}` : null);
  if (!prescriptionId)
    return <AdvancedLookup title="Prescription document"><p>Select a prescription reference to review its medicine instructions.</p></AdvancedLookup>;
  return (
    <article className="prescription-paper" aria-label="Prescription details">
      <header><h2>Prescription details</h2><PageRefresh type="button" disabled={prescription.loading} onClick={prescription.refresh}>Refresh</PageRefresh></header>
      {prescription.loading && <p role="status">Loading prescription…</p>}
      {prescription.error && <p role="alert">{prescription.error}</p>}
      {prescription.response && (
        <div key={`${prescription.response.data.id}:${prescription.response.data.version}`}>
          <PrescriptionDetail prescription={prescription.response.data} compact />
          {children?.(prescription.response.data)}
        </div>
      )}
    </article>
  );
}
function BatchShelfLedger({ medicineId, revision }: { medicineId: string; revision: number }) {
  const batches = useCursorPage<Batch>(query("/api/v1/pharmacy/inventory", { medicine_id: medicineId }), revision);
  return (
    <div className="batch-ledger" aria-label="Inventory batches">
      <div className="batch-ledger__heading"><h3>Inventory batches</h3><PageRefresh type="button" disabled={batches.loading} onClick={batches.refresh}>Refresh</PageRefresh></div>
      {batches.loading && <p role="status">Loading inventory batches…</p>}
      {batches.error && <p role="alert">{batches.error}</p>}
      {batches.loaded && !batches.loading && batches.items.length === 0 && <p>No batches are recorded for this medicine.</p>}
      {batches.items.length > 0 && (
        <table>
          <caption className="sr-only">Batch quantities reported by Pharmacy</caption>
          <thead><tr><th scope="col">Batch</th><th scope="col">Expires</th><th scope="col">On hand</th><th scope="col">Reserved</th><th scope="col">Available</th></tr></thead>
          <tbody>{batches.items.map((batch) => <tr key={batch.id}><th scope="row">Stock batch</th><td><time dateTime={batch.expires_on}>{formatDateTime(batch.expires_on, { utc: true, time: false })}</time></td><td>{batch.on_hand}</td><td>{batch.reserved}</td><td><strong>{batch.available}</strong></td></tr>)}</tbody>
        </table>
      )}
      {(batches.hasPrevious || batches.hasNext) && <div className="batch-ledger__pages"><button type="button" disabled={!batches.hasPrevious} onClick={batches.previous}>Previous batches</button><button type="button" disabled={!batches.hasNext} onClick={batches.next}>More batches</button></div>}
      {batches.items.length > 0 && <ItemDetails><Facts values={Object.fromEntries(batches.items.map((batch) => [batch.batch_code, `Batch ID ${batch.id} · Medicine ID ${batch.medicine_id} · Version ${batch.version}`]))} /></ItemDetails>}
    </div>
  );
}
export function PharmacistPharmacy({ title, workspaceName }: { title: string; workspaceName: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [prescriptionId, setPrescriptionId] = useState<string | null>(null);
  const [ledgerMedicine, setLedgerMedicine] = useState("");
  const [revision, setRevision] = useState(0);
  const select = useCallback((id: string | null) => { setSelected(id); setLedgerMedicine(""); }, []);
  const medicine = useResource<Medicine>(selected ? `/api/v1/pharmacy/medicines/${selected}` : null, revision);
  const item = medicine.response?.data;
  const changed = () => setRevision((value) => value + 1);
  return (
    <PharmacyRoom
      title={title}
      workspaceName={workspaceName}
      cabinet={<MedicineCabinet staff selected={selected} onSelect={select} revision={revision} />}
      stand={<PrescriptionLookupStand onLookup={setPrescriptionId} />}
      tray={<PrescriptionPaper prescriptionId={prescriptionId} />}
      right={<>
        <section className="counter-upper" aria-labelledby="selected-medicine-title">
          <header className="counter-heading"><h2 id="selected-medicine-title">Selected medicine</h2>{selected && <PageRefresh type="button" disabled={medicine.loading} onClick={medicine.refresh}>Refresh</PageRefresh>}</header>
          {!selected && <p>Choose a medicine on the shelf to review its catalog entry and batches.</p>}
          {medicine.loading && <p role="status">Loading medicine…</p>}
          {medicine.error && <p role="alert">{medicine.error}</p>}
          {item && (
            <div key={`${item.id}:${item.version}`}>
              <p className="selected-medicine-name">{medicineLabel(item)}</p>
              <Facts values={{ "Catalog status": item.active ? "Active" : "Inactive", Availability: availabilityText[item.availability] }} />
              <p className="counter-note">Availability is advisory. Pharmacy rechecks stock when a reservation is made.</p>
              <BatchShelfLedger medicineId={ledgerMedicine || item.id} revision={revision} />
              <ItemDetails><Facts values={{ "Medicine ID": item.id, SKU: item.sku, "Catalog version": item.catalog_version, Version: item.version }} /></ItemDetails>
            </div>
          )}
        </section>
        <section className="counter-lower" aria-labelledby="dispensing-entry-title">
          <h2 id="dispensing-entry-title">Dispensing</h2>
          <p>Validate a Records prescription and review its Pharmacy reservation before dispensing.</p>
          <Link className="button" to={selected ? `/pharmacist/prescriptions?medicine=${encodeURIComponent(selected)}` : "/pharmacist/prescriptions"}>Open dispensing workspace →</Link>
          <MoreActions>
          {item && (
            <details className="catalog-edit-tools"><summary>Edit selected catalog entry</summary>
              <CommandForm
                key={`${item.id}:${item.version}`}
                title="Save medicine" reviewLabel="Review changes" confirmLabel="Save medicine" successMessage="Medicine saved."
                path={`/api/v1/pharmacy/medicines/${item.id}`}
                method="PATCH"
                conditional
                etag={medicine.response?.etag}
                fields={[
                  { name: "name", label: "Medicine name", required: true, max: 200, initial: item.name },
                  { name: "active", label: "Medicine active", kind: "select", required: true, options: ["true", "false"], initial: String(item.active) },
                ]}
                build={(values) => ({
                  name: values.name.trim() || (() => { throw new Error("Medicine name is required."); })(),
                  active: values.active === "true",
                })}
                onSuccess={changed}
              />
            </details>
          )}
          <details className="pharmacy-catalog-tools"><summary>Add catalog medicine</summary>
            <CommandForm title="Create medicine" reviewLabel="Review medicine" confirmLabel="Add medicine" successMessage="Medicine added." path="/api/v1/pharmacy/medicines" fields={[{ name: "sku", label: "SKU", required: true, max: 128 }, { name: "name", label: "Medicine name", required: true, max: 200 }]} onSuccess={changed} />
          </details>
          <details className="pharmacy-stock-tools"><summary>Adjust batch stock</summary><StockAdjustment onSuccess={changed} /></details>
          </MoreActions>
          <AdvancedLookup title="Inventory reference filter"><Lookup label="Inventory medicine ID filter" onSelect={setLedgerMedicine} /></AdvancedLookup>
        </section>
      </>}
    />
  );
}
export function PatientPharmacy({ title, workspaceName }: { title: string; workspaceName: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <PatientFulfillmentPanel
      counter
      room={({ stand, tray, right }) => (
        <PharmacyRoom
          title={title}
          workspaceName={workspaceName}
          cabinet={<MoreActions><h2>Browse medicines</h2><MedicineCabinet selected={selected} onSelect={setSelected} showSelection /></MoreActions>}
          stand={stand}
          tray={tray}
          right={right}
        />
      )}
    />
  );
}
export function Fulfillment({
  pharmacist = false,
  title = "Prescription fulfillment",
  workspaceName = "Pharmacy workspace",
  verification,
}: {
  pharmacist?: boolean;
  title?: string;
  workspaceName?: string;
  verification?: ReactNode;
}) {
  const [prescriptionId, setPrescriptionId] = useState<string | null>(null);
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [searchParams] = useSearchParams();
  const carried = searchParams.get("medicine");
  const [medicine, setMedicine] = useState<string | null>(carried && /^[1-9][0-9]*$/.test(carried) ? carried : null);
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const reservation = useResource<Reservation>(selected ? `/api/v1/pharmacy/reservations/${selected}` : null);
  const item = reservation.response?.data;
  const etag = reservation.response?.etag ?? null;
  const changed = () => {
    reservation.refresh();
    setRevision((v) => v + 1);
  };
  return (
    <PharmacyRoom
      title={title}
      workspaceName={workspaceName}
      cabinet={<MedicineCabinet staff selected={medicine} onSelect={setMedicine} showSelection />}
      stand={<PrescriptionLookupStand onLookup={(id) => { setPrescriptionId(id); setPrescription(null); }} />}
      tray={
        <PrescriptionPaper prescriptionId={prescriptionId}>
          {(current) => (
            <>
              {current.state === "issued" && prescription?.id !== current.id && (
                <button type="button" onClick={() => setPrescription(current)}>Request medicines from this prescription</button>
              )}
              {prescription && prescription.id === current.id && (
                <Reserve key={prescription.id} prescription={prescription} onSuccess={() => setRevision((v) => v + 1)} />
              )}
            </>
          )}
        </PrescriptionPaper>
      }
      right={<>
        <section className="counter-upper reservation-slip-panel" aria-labelledby="current-reservation-title">
          <header className="counter-heading"><h2 id="current-reservation-title">Current reservation</h2>{selected && <PageRefresh type="button" disabled={reservation.loading} onClick={reservation.refresh}>Refresh</PageRefresh>}</header>
          {!selected && <p>Choose a reservation from the register below to review it.</p>}
          {reservation.loading && <p role="status">Loading reservation…</p>}
          {reservation.error && <p role="alert">{reservation.error}</p>}
          <FlashArea resetKey={selected}>
          {item && (
            <div key={item.id}>
              <h3 className="dispensing-reservation-title">Current reservation</h3>
              <Facts values={{ State: item.state, "Expires (UTC)": item.expires_at }} />
              {item.items.map((line) => (
                <div className="dispensing-medicine-line" key={line.prescription_item_id}>
                  <DepartmentIcon department="pharmacy" />
                  <div><Resource<Medicine> path={`/api/v1/pharmacy/medicines/${line.medicine_id}`} showReload={false}>{(found) => <strong>{medicineLabel(found)}</strong>}</Resource></div>
                  <span>Quantity <strong>{line.quantity}</strong></span>
                </div>
              ))}
              <ItemDetails><Facts values={{ "Reservation ID": item.id, "Prescription ID": item.prescription_id, Version: item.version, Items: item.items.map((line) => `Prescription item ${line.prescription_item_id} · Medicine ${line.medicine_id}`).join("; ") }} /></ItemDetails>
              {pharmacist && item.state === "reserved" && (
                <div className="dispense-primary" data-check="pharmacy-dispense">
                  <CommandForm<Dispensing>
                    title="Dispense reservation" reviewLabel="Review dispensing" confirmLabel="Dispense" successMessage={(result: Dispensing) => `Dispensed (…${result.id.slice(-4)}). Billing can now import this dispensing.`}
                    path={`/api/v1/pharmacy/reservations/${item.id}/dispense`}
                    conditional
                    etag={etag}
                    onReload={reservation.refresh}
                    reloadLabel="Reload reservation"
                    onSuccess={changed}
                  />
                </div>
              )}
              {item.state !== "dispensed" && (pharmacist ? (
                <details className="reservation-more-actions">
                  <summary>More actions</summary>
                  <CommandForm title="Revalidate reservation" reviewLabel="Revalidate…" confirmLabel="Revalidate reservation" successMessage="Reservation revalidated." path={`/api/v1/pharmacy/reservations/${item.id}/revalidate`} conditional etag={etag} onReload={reservation.refresh} reloadLabel="Reload reservation" onSuccess={changed} />
                  <CommandForm title="Release reservation" reviewLabel="Release…" confirmLabel="Release reservation" successMessage="Reservation released." path={`/api/v1/pharmacy/reservations/${item.id}`} method="DELETE" conditional etag={etag} onReload={reservation.refresh} reloadLabel="Reload reservation" onSuccess={changed} />
                </details>
              ) : (
                <CommandForm title="Release reservation" reviewLabel="Release…" confirmLabel="Release reservation" successMessage="Reservation released." path={`/api/v1/pharmacy/reservations/${item.id}`} method="DELETE" conditional etag={etag} onReload={reservation.refresh} reloadLabel="Reload reservation" onSuccess={changed} />
              ))}
            </div>
          )}
          </FlashArea>
        </section>
        <section className="counter-lower" aria-labelledby="reservation-register-title">
          <h2 id="reservation-register-title" className="sr-only">Reservation register</h2>
          <Collection<Reservation>
            title="Reservations"
            path="/api/v1/pharmacy/reservations"
            revision={revision}
            sourceNote={null}
            onFirstItem={(first) => { if (!selected) setSelected(first.id); }}
            renderItem={(entry) => (
              <div className="reservation-slip">
                <span><strong>Reservation</strong><span className="owner-state">{entry.state}</span></span>
                <button aria-label={`View reservation ${entry.id}`} aria-pressed={selected === entry.id} onClick={() => setSelected(entry.id)}>Review →</button>
              </div>
            )}
          />
          <AdvancedLookup title="Open a reservation by ID"><Lookup label="Reservation ID" onSelect={setSelected} /></AdvancedLookup>
          <details className="dispensing-register"><summary>Completed dispensing ledger</summary>
            <Collection<Dispensing>
              title="Dispensings"
              path="/api/v1/pharmacy/dispensings"
              revision={revision}
              sourceNote={null}
              renderItem={(entry) => (
                <Facts values={{ "Dispensing ID": entry.id, "Prescription ID": entry.prescription_id, "Appointment ID": entry.appointment_id, "Completed (UTC)": entry.completed_at, Items: entry.items.map((line) => `${line.medicine_id}: ${line.quantity}`).join(", ") }} />
              )}
            />
          </details>
          {verification}
        </section>
      </>}
    />
  );
}
