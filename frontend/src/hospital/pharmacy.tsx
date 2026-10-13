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
  const [draft, setDraft] = useState<Values>({});
  const [filters, setFilters] = useState<Values>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [medicineId, setMedicineId] = useState("");
  return (
    <div className="pharmacy-catalog"><div className="pharmacy-search-counter">
      <MedicineAutocomplete api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} onSelect={item => setSelected(item.id)} />
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
      </div><div className="pharmacy-shelf-workspace"><div className="medicine-shelves">
      <Collection<Medicine>
        title="Medicines"
        path={query("/api/v1/pharmacy/medicines", filters)}
        revision={revision}
        renderItem={(item) => (
          <>
            <span className="medicine-box" aria-hidden="true"><DepartmentIcon department="pharmacy"/><span>{item.sku}</span></span><strong>{item.name}</strong>
            <p>
              {item.sku} • {item.availability} (stock hint)
            </p>
            <button aria-label={`View medicine ${item.id}`} onClick={() => setSelected(item.id)}>Medicine details →</button>
          </>
        )}
      />
      </div><aside className="dispensing-counter">{!selected && <Panel title="Medicine details"><div className="resource-empty"><DepartmentIcon department="pharmacy"/><strong>Choose a medicine</strong><p>Open a shelf item to review its catalog status. Prescription fulfillment remains a separate authorized workflow.</p></div></Panel>}
      <Selected<Medicine>
        path={selected ? `/api/v1/pharmacy/medicines/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <Facts
              values={{
                "Medicine ID": item.id,
                SKU: item.sku,
                Name: item.name,
                Active: String(item.active),
                "Availability hint": item.availability,
              }}
            />
            {staff && (
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
            )}
          </>
        )}
      </Selected>
      </aside></div>
      {staff && (
        <Panel title="New catalog medicine">
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
        </Panel>
      )}
      {inventory && (
        <>
          <Lookup
            label="Inventory medicine ID filter"
            onSelect={setMedicineId}
          />
          <Collection<Batch>
            title="Inventory batches"
            path={query("/api/v1/pharmacy/inventory", {
              medicine_id: medicineId,
            })}
            revision={revision}
            renderItem={(batch) => (
              <Facts
                values={{
                  "Batch ID": batch.id,
                  "Medicine ID": batch.medicine_id,
                  "Batch code": batch.batch_code,
                  Expiry: batch.expires_on,
                  "On hand": batch.on_hand,
                  Reserved: batch.reserved,
                  Available: batch.available,
                  "Batch version": batch.version,
                }}
              />
            )}
          />
          <StockAdjustment onSuccess={() => setRevision((v) => v + 1)} />
        </>
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
    <>
      <Prescriptions pharmacist={pharmacist} onSelect={setPrescription} />
      {prescription && (
        <Reserve
          key={prescription.id}
          prescription={prescription}
          onSuccess={() => setRevision((v) => v + 1)}
        />
      )}
      <Collection<Reservation>
        title="Reservations"
        path="/api/v1/pharmacy/reservations"
        revision={revision}
        renderItem={(item) => (
          <>
            <p>
              Reservation {item.id} • Prescription {item.prescription_id} •{" "}
              {item.state}
            </p>
            <button onClick={() => setSelected(item.id)}>
              View reservation {item.id}
            </button>
          </>
        )}
      />
      <Lookup label="Reservation ID" onSelect={setSelected} />
      <Selected<Reservation>
        path={selected ? `/api/v1/pharmacy/reservations/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <Facts
              values={{
                "Reservation ID": item.id,
                "Prescription ID": item.prescription_id,
                State: item.state,
                "Expires (UTC)": item.expires_at,
              }}
            />
            {item.items.map((line) => (
              <Facts
                key={line.prescription_item_id}
                values={{
                  "Prescription item": line.prescription_item_id,
                  "Medicine ID": line.medicine_id,
                  Quantity: line.quantity,
                }}
              />
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
    </>
  );
}
