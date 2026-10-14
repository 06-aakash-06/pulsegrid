import { useLocalDemo } from "../design/localDemo";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { MedicineAutocomplete } from "../phase4";
import { useAuth } from "../auth/authContext";
import { useState } from "react";
import type {
  Batch,
  Dispensing,
  Medicine,
  Prescription,
  Reservation,
} from "./models";
import {
  buildFields,
  Collection,
  CommandForm,
  date,
  Facts,
  idField,
  Inputs,
  integer,
  Lookup,
  Panel,
  query,
  reasonField,
  Resource,
  Selected,
  type Field,
  type Values,
} from "./ui";
import { Prescriptions } from "./records";
export function MedicineCatalog({
  staff = false,
  inventory = false,
}: {
  staff?: boolean;
  inventory?: boolean;
}) {
  const { state, api }=useAuth();
  const demo = useLocalDemo();
  const [showAll, setShowAll] = useState(false);
  const [demoSelected, setDemoSelected] = useState(false);
  const [draft, setDraft] = useState<Values>({});
  const [filters, setFilters] = useState<Values>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [medicineId, setMedicineId] = useState("");
  const [availability, setAvailability] = useState<Medicine["availability"] | "">("");
  return (
    <div className="pharmacy-catalog"><div className="pharmacy-search-counter">
      <div className="pharmacy-autocomplete"><MedicineAutocomplete api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} label="Quick medicine lookup" placeholder="Find a medicine by name…" onSelect={item => {setSelected(item.id);if(inventory)setMedicineId(item.id);setDemoSelected(true);}} /></div>
      <nav className="medicine-availability-tabs" aria-label="Catalog availability on this page">{[["","All medicines"],["available","Available"],["unavailable","Unavailable"],["unknown","Not reported"]].map(([value,label])=><button type="button" key={value} aria-pressed={availability===value} onClick={()=>{setAvailability(value as Medicine["availability"]|"");setSelected(null);setDemoSelected(false);}}>{label}</button>)}</nav>
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
      {demo&&<label className="catalog-cohort"><input type="checkbox" checked={showAll} onChange={e=>{setShowAll(e.target.checked);setSelected(null);}}/>Show all owner records · Fictional demo catalog</label>}
      </div><div className="pharmacy-shelf-workspace"><div className="medicine-shelves"><div className="cabinet-signage"><strong>MEDICINE CABINET</strong><span>Catalog availability · Pharmacy</span></div>
      <Collection<Medicine>
        title="Medicines"
        path={query("/api/v1/pharmacy/medicines", filters)}
        revision={revision}
        itemFilter={item=>(!demo||showAll||!!filters.q||item.sku.startsWith("DEMO-"))&&(!availability||item.availability===availability)}
        onFirstItem={item=>{if(!selected||(demo&&!showAll&&!demoSelected)){setSelected(item.id);if(inventory)setMedicineId(item.id);setDemoSelected(Boolean(demo));}}}
        renderItem={(item) => (
          <div className="medicine-shelf-slot" data-selected={selected===item.id} data-availability={item.availability}>
            <div className="carton-space"><span className="medicine-box" aria-hidden="true"><small>PULSEGRID · DEMO</small><DepartmentIcon department="pharmacy"/><span>{item.name.startsWith("Synthetic") ? "Catalog medicine" : item.name}</span><i /></span></div>
            <button aria-label={`View medicine ${item.id}`} aria-pressed={selected===item.id} onClick={() => {setSelected(item.id);if(inventory)setMedicineId(item.id);}}><strong>{item.name.startsWith("Synthetic")?`Demo catalog item …${item.id.slice(-4)}`:item.name}</strong><span>Details →</span></button>
            <p>{item.availability.replaceAll("_", " ")} · Stock hint</p>
          </div>
        )}
      />
      </div><aside className="dispensing-counter">{!selected && <Panel title="Medicine details"><div className="resource-empty"><DepartmentIcon department="pharmacy"/><strong>Choose a medicine</strong><p>Open a shelf item to review its catalog status. Prescription fulfillment remains a separate authorized workflow.</p></div></Panel>}
      <Selected<Medicine>
        path={selected ? `/api/v1/pharmacy/medicines/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <h2 className="selected-medicine-name">{item.name.startsWith("Synthetic")?`Demo catalog item …${item.id.slice(-4)}`:item.name}</h2>
            <Facts values={{"Catalog status":item.active?"Active":"Inactive","Availability hint":item.availability}}/>
            <details className="owner-identifiers"><summary>Catalog identifiers</summary><Facts values={{"Medicine ID":item.id,SKU:item.sku}}/></details>
            {staff && (<details className="catalog-edit-tools"><summary>Edit selected catalog entry</summary>
              <CommandForm
                title="Save medicine"
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
            title="Create medicine"
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
          <details className="inventory-source-filter"><summary>Inventory reference filter</summary><Lookup
            label="Inventory medicine ID filter"
            onSelect={setMedicineId}
          /></details>
          <Collection<Batch>
            title="Inventory batches"
            path={query("/api/v1/pharmacy/inventory", {
              medicine_id: medicineId,
            })}
            revision={revision}
            renderItem={(batch) => (
              <><div className="stock-ledger-row"><strong>{batch.batch_code}</strong><time>{batch.expires_on}</time><span>{batch.on_hand} on hand</span><span>{batch.reserved} reserved</span><strong>{batch.available} available</strong></div><details className="owner-identifiers"><summary>Batch identifiers and version</summary><Facts values={{"Batch ID":batch.id,"Medicine ID":batch.medicine_id,"Batch version":batch.version}}/></details></>
            )}
          />
          <details className="pharmacy-stock-tools"><summary>Adjust batch stock</summary><StockAdjustment onSuccess={() => setRevision((v) => v + 1)} /></details>
        </div>
      )}
    </div>
  );
}
function StockAdjustment({ onSuccess }: { onSuccess: () => void }) {
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
        title="Adjust stock"
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
        title="Reserve medicines"
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
export function Fulfillment({ pharmacist = false }: { pharmacist?: boolean }) {
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [dispensing, setDispensing] = useState<Dispensing | null>(null);
  return (
    <div className="fulfillment-workspace"><section className="prescription-counter prescription-stand"><header><DepartmentIcon department="records"/><h2>Prescription counter</h2><span aria-hidden="true">Rx</span></header>
      <Prescriptions pharmacist={pharmacist} onSelect={setPrescription} />
      {prescription && (
        <Reserve
          key={prescription.id}
          prescription={prescription}
          onSuccess={() => setRevision((v) => v + 1)}
        />
      )}
      </section><section className="reservation-counter"><details className="reservation-register"><summary>Reservation register</summary>
      <Collection<Reservation>
        title="Reservations"
        path="/api/v1/pharmacy/reservations"
        revision={revision}
        onFirstItem={item=>{if(!selected)setSelected(item.id);}}
        renderItem={(item) => (
          <>
            <div className="reservation-slip"><strong>Reservation …{item.id.slice(-4)}</strong><span className="owner-state">{item.state}</span></div>
            <details className="owner-identifiers"><summary>Prescription and reservation references</summary><Facts values={{"Reservation ID":item.id,"Prescription ID":item.prescription_id}}/></details>
            <button aria-label={`View reservation ${item.id}`} onClick={() => setSelected(item.id)}>Review reservation →</button>
          </>
        )}
      />
      <Lookup label="Reservation ID" onSelect={setSelected} />
      </details>
      <Selected<Reservation>
        path={selected ? `/api/v1/pharmacy/reservations/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <h3 className="dispensing-reservation-title">Reservation …{item.id.slice(-4)}</h3><Facts
              values={{
                State: item.state,
                "Expires (UTC)": item.expires_at,
              }}
            />
            <details className="owner-identifiers"><summary>Reservation and prescription references</summary>Reservation {item.id} · Prescription {item.prescription_id}</details>
            {item.items.map((line) => (
              <div className="dispensing-medicine-line" key={line.prescription_item_id}><DepartmentIcon department="pharmacy"/><div><Resource<Medicine> path={`/api/v1/pharmacy/medicines/${line.medicine_id}`} showReload={false}>{medicine=><strong>{medicine.name.startsWith("Synthetic")?`Catalog item …${medicine.id.slice(-4)}`:medicine.name}</strong>}</Resource><details className="owner-identifiers"><summary>Item references</summary>Medicine {line.medicine_id} · Prescription item {line.prescription_item_id}</details></div><span>Quantity <strong>{line.quantity}</strong></span></div>
            ))}
            {item.state !== "dispensed" && (
              <CommandForm
                title="Release reservation"
                path={`/api/v1/pharmacy/reservations/${item.id}`}
                method="DELETE"
                conditional
                etag={etag}
                onSuccess={() => {
                  refresh();
                  setRevision((v) => v + 1);
                }}
              />
            )}
            {pharmacist && (
              <>
                <CommandForm
                  title="Revalidate reservation"
                  path={`/api/v1/pharmacy/reservations/${item.id}/revalidate`}
                  conditional
                  etag={etag}
                  onSuccess={() => {
                    refresh();
                    setRevision((v) => v + 1);
                  }}
                />
                {item.state === "reserved" && (
                  <CommandForm<Dispensing>
                    title="Dispense reservation"
                    path={`/api/v1/pharmacy/reservations/${item.id}/dispense`}
                    conditional
                    etag={etag}
                    onSuccess={(result) => {
                      setDispensing(result);
                      refresh();
                      setRevision((v) => v + 1);
                    }}
                  />
                )}
              </>
            )}
          </>
        )}
      </Selected>
      {dispensing && (
        <p role="status">
          Completed dispensing {dispensing.id}. Billing must explicitly import
          this source ID.
        </p>
      )}
      </section><details className="dispensing-register"><summary>Completed dispensing ledger</summary>
      <Collection<Dispensing>
        title="Dispensings"
        path="/api/v1/pharmacy/dispensings"
        revision={revision}
        renderItem={(item) => (
          <Facts
            values={{
              "Dispensing ID": item.id,
              "Prescription ID": item.prescription_id,
              "Appointment ID": item.appointment_id,
              "Completed (UTC)": item.completed_at,
              Items: item.items
                .map((i) => `${i.medicine_id}: ${i.quantity}`)
                .join(", "),
            }}
          />
        )}
      />
    </details></div>
  );
}
