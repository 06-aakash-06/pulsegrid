import { m } from "motion/react";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { DepartmentSign } from "../design/DepartmentSign";
import { useCursorPage } from "./pharmacyRoom";
import { InsuranceEstimatePanel, InsuranceRefreshPanel } from "../phase4";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAuth } from "../auth/authContext";
import type {
  Emergency,
  Invoice,
  Medicine,
  PatientProfile,
  Payment,
  Tariff,
} from "./models";
import {
  buildFields,
  Collection,
  CommandForm,
  Facts,
  FlashArea,
  formatDateTime,
  id,
  idField,
  ids,
  integer,
  Lookup,
  money,
  reasonField,
  Resource,
  textField,
  useResource,
  type Field,
} from "./ui";
function MedicineCharge({ code }: { code: string }) {
  const medicineId = code.startsWith("medicine:") ? code.slice(9) : null;
  const medicine = useResource<Medicine>(medicineId ? `/api/v1/pharmacy/medicines/${medicineId}` : null);
  if (code === "consultation") return <>Consultation fee</>;
  const name = medicine.response?.data.name;
  return <>{name && !name.startsWith("Synthetic") ? name : code}</>;
}
function InvoiceStatus({ invoice }: { invoice: Invoice }) {
  const label = invoice.status === "paid" ? "Paid" : invoice.paid_minor > 0 ? "Part paid" : "Unpaid";
  return <span className="owner-state" data-state={label.toLowerCase().replace(" ", "-")}>{label}</span>;
}
function rupees(minor: number) {
  const amount = BigInt(minor);
  return `${amount / 100n}.${String(amount % 100n).padStart(2, "0")}`;
}
function paiseFromRupees(value: string, max: number) {
  const match = /^(\d{1,15})(?:\.(\d{1,2}))?$/.exec(value.trim());
  if (!match) throw new Error("Enter the amount in rupees with up to two decimals, for example 500 or 500.50.");
  return integer(String(Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"))), 1, max);
}
const chargeSources = [
  { source: "records", label: "Consultation" },
  { source: "pharmacy", label: "Pharmacy" },
] as const;

function InvoiceReceipt({
  invoice,
  etag,
  loading,
  onRefresh,
  onChange,
  payment,
  onPayment,
}: {
  invoice: Invoice;
  etag: string | null;
  loading: boolean;
  onRefresh: () => void;
  onChange: () => void;
  payment: Payment | null;
  onPayment: (payment: Payment) => void;
}) {
  const { state: authState, api } = useAuth();
  return (
    <>
      <header className="cashier-receipt__header">
        <div><h2 id="cashier-receipt-title">Receipt</h2><p>Invoice …{invoice.id.slice(-4)} · <InvoiceStatus invoice={invoice} /></p></div>
        <button type="button" disabled={loading} onClick={onRefresh}>Refresh</button>
      </header>
      {invoice.items.length === 0 ? (
        <p className="cashier-receipt__empty">No charges have been imported.</p>
      ) : (
        <div className="invoice-line-scroll" tabIndex={0} role="region" aria-label="Invoice line items">
          <table className="cashier-lines">
            <caption className="sr-only">Itemized invoice</caption>
            <thead><tr><th scope="col">Charge</th><th scope="col">Qty × unit</th><th scope="col">Amount</th></tr></thead>
            {chargeSources.map(({ source, label }) => {
              const lines = invoice.items.filter((line) => line.source_service === source);
              if (!lines.length) return null;
              return (
                <tbody key={source}>
                  <tr className="cashier-lines__group"><th scope="colgroup" colSpan={3}>{label} <span>({lines.length} {lines.length === 1 ? "item" : "items"})</span></th></tr>
                  {lines.map((line) => (
                    <tr key={line.id}>
                      <th scope="row"><MedicineCharge code={line.charge_code} /></th>
                      <td>{line.quantity} × {money(line.unit_amount_minor)}</td>
                      <td>{money(line.quantity * line.unit_amount_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              );
            })}
          </table>
        </div>
      )}
      <dl className="cashier-balance" data-check="billing-balance">
        <div><dt>Total</dt><dd>{money(invoice.total_minor)}</dd></div>
        <div><dt>Paid</dt><dd>{money(invoice.paid_minor)}</dd></div>
        <div className="cashier-balance__due"><dt>Balance due</dt><dd>{money(invoice.balance_minor)}</dd></div>
      </dl>
      <p className="cashier-simulated">Payments are simulated. Do not enter card, bank or real payment credentials.</p>
      {invoice.balance_minor > 0 && (
        <CommandForm<Payment>
          title="Submit simulated payment"
          reviewLabel="Review payment"
          confirmLabel="Pay (simulated)"
          successMessage="Simulated payment submitted."
          onReload={onRefresh}
          reloadLabel="Reload invoice"
          path={`/api/v1/billing/invoices/${invoice.id}/payments`}
          conditional
          etag={etag}
          fields={[
            { name: "amount_rupees", label: "Payment amount (₹)", required: true, max: 20, initial: rupees(invoice.balance_minor) },
            { name: "simulated_outcome", label: "Simulated outcome", kind: "select", required: true, options: ["success", "decline"], initial: "success" },
          ]}
          preview={(values) => {
            try {
              const paise = paiseFromRupees(values.amount_rupees ?? "", invoice.balance_minor);
              return <p className="paise-preview" aria-live="polite">You will pay {money(paise)}.</p>;
            } catch (problem) {
              return <p className="paise-preview" aria-live="polite">{problem instanceof Error ? problem.message : "Enter an amount."}</p>;
            }
          }}
          build={(values) => ({
            amount_minor: paiseFromRupees(values.amount_rupees, invoice.balance_minor),
            currency: "INR",
            simulated_outcome: values.simulated_outcome,
          })}
          onSuccess={(result) => {
            onPayment(result);
            onChange();
          }}
        />
      )}
      {payment && payment.invoice_id === invoice.id && (
        <m.p key={payment.id} initial={{ backgroundColor: "#f3dd9a" }} animate={{ backgroundColor: "#f1ebe1" }} transition={{ duration: 1.2 }} role="status" className="cashier-payment-result">
          Payment …{payment.id.slice(-4)}:{" "}
          {payment.status === "declined" ? "simulated decline recorded; balance was not paid" : "simulated success recorded"}. Amount {money(payment.amount_minor)}.
        </m.p>
      )}
      <details className="cashier-more"><summary>Payment history</summary>
        <Collection<Payment>
          title="Invoice payments"
          path={`/api/v1/billing/invoices/${invoice.id}/payments`}
          renderItem={(item) => <div className="cashier-payment-row"><span>{money(item.amount_minor)}</span><span className="owner-state" data-state={item.status}>{item.status === "declined" ? "Declined" : "Succeeded"}</span><small>…{item.id.slice(-4)}</small></div>}
        />
      </details>
      <details className="cashier-more"><summary>Insurance estimates</summary><InsuranceEstimatePanel api={api} roleHints={authState.status === "authenticated" ? authState.roleHints : []} invoiceId={invoice.id} providerChoices={syntheticProviders} /></details>
      <details className="owner-identifiers"><summary>Details</summary>
        <Facts values={{ "Invoice ID": invoice.id, "Patient ID": invoice.patient_id, "Appointment ID": invoice.appointment_id, Version: invoice.version }} />
        <ul className="cashier-sources">{invoice.items.map((line) => <li key={line.id}>{line.source_service} · source {line.source_item_id} · {line.charge_code} · tariff revision {line.tariff_revision}</li>)}</ul>
      </details>
    </>
  );
}

function TariffReference() {
  const [revision, setRevision] = useState(0);
  const tariffs = useCursorPage<Tariff>("/api/v1/billing/tariffs", revision);
  const latest = new Map<string, number>();
  tariffs.items.forEach((item) => latest.set(item.charge_code, Math.max(latest.get(item.charge_code) ?? 0, item.revision)));
  return (
    <div className="cashier-tariffs">
      <div className="cashier-panel-heading"><p>Billing sets prices when charges are imported. Historical revisions stay for reference; this list does not add charges.</p><button type="button" disabled={tariffs.loading} onClick={tariffs.refresh}>Refresh</button></div>
      {tariffs.loading && <p role="status">Loading tariffs…</p>}
      {tariffs.error && <p role="alert">{tariffs.error}</p>}
      <table className="cashier-price-table">
        <caption className="sr-only">Tariff reference</caption>
        <thead><tr><th scope="col">Charge</th><th scope="col">Revision</th><th scope="col">Unit price</th></tr></thead>
        <tbody>{tariffs.items.map((item) => {
          const current = latest.get(item.charge_code) === item.revision;
          return <tr key={item.id} data-historical={!current}><th scope="row"><MedicineCharge code={item.charge_code} /></th><td>{current ? `Current · revision ${item.revision}` : `Historical · revision ${item.revision}`}</td><td>{money(item.unit_amount_minor)}</td></tr>;
        })}</tbody>
      </table>
      {(tariffs.hasPrevious || tariffs.hasNext) && <div className="cashier-pages"><button type="button" disabled={!tariffs.hasPrevious} onClick={tariffs.previous}>Previous page</button><button type="button" disabled={!tariffs.hasNext} onClick={tariffs.next}>Next page</button></div>}
      <details className="cashier-more"><summary>Add a tariff revision</summary><Tariffs onCreated={() => setRevision((v) => v + 1)} /></details>
    </div>
  );
}

const cashierTabs = [
  { key: "import", label: "Import charges" },
  { key: "tariffs", label: "Tariff reference" },
  { key: "new", label: "New invoice" },
] as const;

export function BillingPage({ staff = false, title, subtitle }: { staff?: boolean; title?: string; subtitle?: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [tab, setTab] = useState<(typeof cashierTabs)[number]["key"]>("import");
  const registerRef = useRef<HTMLElement>(null);
  const register = useCursorPage<Invoice>("/api/v1/billing/invoices", revision);
  const firstId = register.items[0]?.id;
  useEffect(() => {
    if (!selected && firstId) setSelected(firstId);
  }, [selected, firstId]);
  const invoice = useResource<Invoice>(selected ? `/api/v1/billing/invoices/${selected}` : null, revision);
  const profile = useResource<PatientProfile>(staff ? null : "/api/v1/patients/me");
  const current = invoice.response?.data;
  const etag = invoice.response?.etag ?? null;
  const changed = () => setRevision((v) => v + 1);
  const select = (value: string) => {
    setSelected(value);
    setPayment(null);
  };
  const ownName = profile.response && current && profile.response.data.id === current.patient_id && !profile.response.data.display_name.startsWith("Synthetic") ? profile.response.data.display_name : null;
  const openRegister = () => {
    registerRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    registerRef.current?.focus({ preventScroll: true });
  };

  const context = (
    <section className="cashier-context" aria-label="Selected invoice">
      {current ? (
        <dl>
          <div className="cashier-context__patient"><dt>Patient</dt><dd>{ownName ?? `Patient …${current.patient_id.slice(-4)}`}{ownName && <small>ID …{current.patient_id.slice(-4)}</small>}</dd></div>
          <div><dt>Visit</dt><dd>Visit …{current.appointment_id.slice(-4)}</dd></div>
          <div><dt>Invoice</dt><dd>Invoice …{current.id.slice(-4)}</dd></div>
          <div><dt>Status</dt><dd><InvoiceStatus invoice={current} /></dd></div>
        </dl>
      ) : (
        <p>{register.loading || invoice.loading ? "Loading invoice…" : "No invoice selected."}</p>
      )}
      <button type="button" onClick={openRegister}>Change invoice</button>
    </section>
  );
  const registerTable = (
    <section className="cashier-register" ref={registerRef} tabIndex={-1} aria-labelledby="cashier-register-title">
      <div className="cashier-panel-heading"><h2 id="cashier-register-title">{staff ? "Invoice register" : "Your invoices"}</h2><button type="button" disabled={register.loading} onClick={register.refresh}>Refresh</button></div>
      {register.loading && <p role="status">Loading invoices…</p>}
      {register.error && <p role="alert">{register.error}</p>}
      {register.loaded && !register.loading && register.items.length === 0 && <p>No invoices found.</p>}
      {register.items.length > 0 && (
        <table className="cashier-register__table">
          <caption className="sr-only">Invoices</caption>
          <thead><tr><th scope="col">Invoice</th><th scope="col" className="cashier-register__visit">Visit</th><th scope="col">Status</th><th scope="col">Total</th><th scope="col">Balance</th><th scope="col"><span className="sr-only">Open</span></th></tr></thead>
          <tbody>{register.items.map((item) => (
            <tr key={item.id} data-selected={selected === item.id}>
              <th scope="row" data-label="Invoice">…{item.id.slice(-4)}</th>
              <td className="cashier-register__visit">…{item.appointment_id.slice(-4)}</td>
              <td data-label="Status"><InvoiceStatus invoice={item} /></td>
              <td data-label="Total">{money(item.total_minor)}</td>
              <td data-label="Balance">{money(item.balance_minor)}</td>
              <td><button type="button" aria-label={`View invoice ${item.id}`} aria-pressed={selected === item.id} onClick={() => select(item.id)}>{selected === item.id ? "Open" : "View"}</button></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {(register.hasPrevious || register.hasNext) && <div className="cashier-pages"><button type="button" disabled={!register.hasPrevious} onClick={register.previous}>Previous page</button><button type="button" disabled={!register.hasNext} onClick={register.next}>Next page</button></div>}
      <details className="cashier-more"><summary>Open an invoice by ID</summary><Lookup label="Invoice ID" onSelect={select} /></details>
    </section>
  );
  const receipt = (
    <aside className="cashier-receipt" aria-labelledby="cashier-receipt-title">
      {!selected && !register.loading && <p className="cashier-receipt__empty"><DepartmentIcon department="billing" />Choose an invoice to review its line items and balance.</p>}
      {invoice.loading && !current && <p role="status">Loading invoice…</p>}
      {invoice.error && <p role="alert">{invoice.error}</p>}
      {current && <InvoiceReceipt invoice={current} etag={etag} loading={invoice.loading} onRefresh={invoice.refresh} onChange={changed} payment={payment} onPayment={setPayment} />}
    </aside>
  );
  return (
    <div className={`cashier-desk cashier-desk--${staff ? "staff" : "patient"}`}>
      {title && (
        <DepartmentSign department="billing" title={title} subtitle={subtitle ?? ""}>
          <p className="department-sign__note"><strong>Simulated payments</strong><span>Balances include only charges imported by Billing staff.</span></p>
        </DepartmentSign>
      )}
      {context}
      {staff ? (
        <>
          <div className="cashier-left">
            <section className="cashier-workbench" aria-label="Cashier actions">
              <div className="cashier-tabs" role="tablist" aria-label="Cashier actions">
                {cashierTabs.map((item, index) => (
                  <button
                    key={item.key}
                    type="button"
                    role="tab"
                    id={`cashier-tab-${item.key}`}
                    aria-controls="cashier-tabpanel"
                    aria-selected={tab === item.key}
                    tabIndex={tab === item.key ? 0 : -1}
                    onClick={() => setTab(item.key)}
                    onKeyDown={(event) => {
                      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                      const next = cashierTabs[(index + (event.key === "ArrowRight" ? 1 : cashierTabs.length - 1)) % cashierTabs.length];
                      setTab(next.key);
                      document.getElementById(`cashier-tab-${next.key}`)?.focus();
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="cashier-tabpanel" role="tabpanel" id="cashier-tabpanel" aria-labelledby={`cashier-tab-${tab}`}>
                {tab === "import" && (current
                  ? <ChargeImport invoice={current} etag={etag} onChange={changed} />
                  : <p>Choose an invoice before importing charges.</p>)}
                {tab === "tariffs" && <TariffReference />}
                {tab === "new" && (
                  <CommandForm<Invoice>
                    title="Create invoice"
                    reviewLabel="Review invoice"
                    confirmLabel="Create invoice"
                    successMessage="Invoice created."
                    path="/api/v1/billing/invoices"
                    fields={[idField("appointment_id", "Appointment ID")]}
                    build={(values) => ({ appointment_id: id(values.appointment_id.trim()), currency: "INR" })}
                    onSuccess={(item) => {
                      select(item.id);
                      changed();
                      setTab("import");
                    }}
                    notice="Creates an empty invoice for a visit. Charges are added by importing finalized sources."
                  />
                )}
              </div>
            </section>
            {registerTable}
          </div>
          {receipt}
        </>
      ) : (
        <>
          {receipt}
          {registerTable}
        </>
      )}
    </div>
  );
}
function ChargeImport({ invoice, etag, onChange }: { invoice: Invoice; etag: string | null; onChange: () => void }) {
  return (
    <div className="cashier-import">
      <p>Import finalized sources for <strong>Visit …{invoice.appointment_id.slice(-4)}</strong>: a finalized consultation from Records and completed dispensings from Pharmacy. Prices come from Billing tariffs.</p>
      <CommandForm
        title="Import charges manually"
        reviewLabel="Review import"
        confirmLabel="Import charges"
        successMessage="Charges imported. The receipt shows the new lines."
        path={`/api/v1/billing/invoices/${invoice.id}/charges`}
        conditional
        etag={etag}
        fields={[
          idField("consultation_id", "Finalized consultation ID", false),
          { name: "dispensing_ids", label: "Completed dispensing IDs (comma separated)" },
        ]}
        build={(values) => {
          const consultationId = values.consultation_id.trim();
          const dispensingIds = ids(values.dispensing_ids);
          if (!consultationId && !dispensingIds.length) throw new Error("Select at least one consultation or dispensing source.");
          return { ...(consultationId ? { consultation_id: id(consultationId) } : {}), dispensing_ids: dispensingIds };
        }}
        onSuccess={onChange}
        notice="Source IDs must belong to this invoice's appointment and patient. Missing imports are not detected automatically."
      />
    </div>
  );
}
function Tariffs({ onCreated }: { onCreated: () => void }) {
  const fields: Field[] = [
    { name: "charge_code", label: "Charge code (consultation or medicine:ID)", required: true, max: 128 },
    { name: "unit_amount_minor", label: "Unit amount in paise", kind: "number", required: true, min: 0 },
  ];
  return (
    <CommandForm
      title="Create tariff revision"
      reviewLabel="Review tariff"
      confirmLabel="Create tariff revision"
      successMessage="Tariff revision created."
      path="/api/v1/billing/tariffs"
      fields={fields}
      build={(values) => {
        const body = buildFields(fields, values);
        const code = values.charge_code.trim();
        if (code !== "consultation") {
          if (!code.startsWith("medicine:")) throw new Error("Use consultation or medicine:ID.");
          id(code.slice(9));
        }
        return { ...body, currency: "INR" };
      }}
      onSuccess={onCreated}
    />
  );
}
function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
function elapsed(from: string, now: number) {
  const minutes = Math.max(0, Math.round((now - Date.parse(from)) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 48 ? `${hours} h ${minutes % 60} min` : `${Math.floor(hours / 24)} days`;
}
const utcTime = (value: string) => formatDateTime(value);
function PriorityChip({ priority }: { priority: number | null }) {
  return (
    <span className="priority-chip" data-priority={priority ?? "none"}>
      {priority ? <><span className="sr-only">Priority </span>P{priority}</> : "No priority"}
    </span>
  );
}
function StateChip({ state }: { state: string }) {
  return <span className="owner-state" data-state={state}>{state.replaceAll("_", " ")}</span>;
}
function requestTitle(item: Emergency) {
  return item.description?.trim() || `Request …${item.id.slice(-4)}`;
}
const terminalStates = ["resolved", "cancelled"];
export function sortEmergencyQueue(items: Emergency[]): Emergency[] {
  return [...items].sort((a, b) => (a.assigned_priority ?? 99) - (b.assigned_priority ?? 99) || a.created_at.localeCompare(b.created_at));
}

function NextSteps({
  item,
  etag,
  staff,
  userId,
  onChange,
}: {
  item: Emergency;
  etag: string | null;
  staff: boolean;
  userId?: string;
  onChange: () => void;
}) {
  const owned = !!userId && item.claimed_by_user_id === userId;
  const [openAction, setOpenAction] = useState<string | null>(null);
  useEffect(() => setOpenAction(null), [item.state, item.claimed_by_user_id]);
  const transition = (title: string, target: Emergency["state"], labels: { review: string; confirm: string; success: string; reason: string }) => {
    const reason = { ...reasonField, label: labels.reason };
    return (
      <CommandForm
        title={title}
        reviewLabel={labels.review}
        confirmLabel={labels.confirm}
        successMessage={labels.success}
        path={`/api/v1/emergencies/${item.id}/transitions`}
        conditional
        etag={etag}
        onReload={onChange}
        reloadLabel="Reload request"
        fields={[reason]}
        build={(values) => ({ ...buildFields([reason], values), state: target })}
        onSuccess={onChange}
      />
    );
  };
  const priority = (title: string) => (
    <CommandForm
      title={title}
      reviewLabel="Review priority"
      confirmLabel="Set priority"
      successMessage={(updated: Emergency) => `Priority set to P${updated.assigned_priority ?? "—"}.`}
      path={`/api/v1/emergencies/${item.id}/priority`}
      method="PATCH"
      conditional
      etag={etag}
      onReload={onChange}
      reloadLabel="Reload request"
      fields={[
        { name: "assigned_priority", label: "Assigned priority (1 highest, 5 lowest)", kind: "number", min: 1, max: 5, required: true },
        { ...reasonField, label: "Reason for priority" },
      ]}
      onSuccess={onChange}
    />
  );
  const claim = (
    <CommandForm
      title="Claim request"
      reviewLabel="Review claim"
      confirmLabel="Claim request"
      successMessage="Request claimed. You hold it for 15 minutes."
      path={`/api/v1/emergencies/${item.id}/claim`}
      conditional
      etag={etag}
      onReload={onChange}
      reloadLabel="Reload request"
      onSuccess={onChange}
      notice="Claims have a 15-minute lease. Refresh before processing to check the current claim."
    />
  );
  const release = (
    <CommandForm
      title="Release claim"
      reviewLabel="Review release"
      confirmLabel="Confirm release"
      successMessage="Claim released."
      path={`/api/v1/emergencies/${item.id}/release`}
      conditional
      etag={etag}
      onReload={onChange}
      reloadLabel="Reload request"
      fields={[{ ...reasonField, label: "Reason for releasing" }]}
      onSuccess={onChange}
    />
  );
  const cancel = transition("Cancel emergency request", "cancelled", { review: "Review cancellation", confirm: "Confirm cancellation", success: "Request cancelled.", reason: "Reason for cancelling" });
  const claimUntil = item.claim_expires_at ? ` until ${utcTime(item.claim_expires_at)}` : "";

  let primary: ReactNode = null;
  let note = "";
  const secondary: { label: string; form: ReactNode }[] = [];
  if (terminalStates.includes(item.state)) {
    note = `This request is ${item.state}. No further workflow actions are available.`;
  } else if (!staff) {
    if (["submitted", "triaged"].includes(item.state)) secondary.push({ label: "Cancel this request", form: cancel });
    else note = "Emergency staff are handling this request. It can no longer be cancelled here.";
  } else if (item.state === "submitted") {
    primary = priority("Set priority");
    secondary.push({ label: "Cancel request", form: cancel });
  } else if (item.state === "triaged") {
    primary = claim;
    secondary.push({ label: "Change priority", form: priority("Set priority") }, { label: "Cancel request", form: cancel });
  } else if (item.state === "claimed") {
    if (owned) {
      primary = transition("Start processing", "processing", { review: "Review start", confirm: "Start processing", success: "Processing started.", reason: "Reason for starting" });
      secondary.push({ label: "Release claim", form: release });
    } else note = `Claimed by another staff member${claimUntil}. Only the claim holder can process or release it.`;
    secondary.push({ label: "Change priority", form: priority("Set priority") }, { label: "Cancel request", form: cancel });
  } else if (item.state === "processing") {
    if (owned) primary = transition("Resolve request", "resolved", { review: "Review resolution", confirm: "Resolve request", success: "Request resolved.", reason: "Reason for resolving" });
    else note = "Another staff member is processing this request.";
    secondary.push({ label: "Change priority", form: priority("Set priority") });
  }
  return (
    <aside className="er-steps" aria-labelledby="er-steps-title">
      <h2 id="er-steps-title">{staff ? "Next steps" : "Request actions"}</h2>
      <FlashArea resetKey={item.id}>
        {note && <p className="er-steps__note">{note}</p>}
        {primary && <div className="er-primary" data-check="emergency-primary">{primary}</div>}
        {secondary.length > 0 && (
          <div className="er-secondary-actions" role="group" aria-label="Other actions">
            {secondary.map(({ label }) => (
              <button key={label} type="button" aria-expanded={openAction === label} onClick={() => setOpenAction(openAction === label ? null : label)}>{label}</button>
            ))}
          </div>
        )}
        {secondary.filter(({ label }) => label === openAction).map(({ label, form }) => <div className="er-secondary" key={label}>{form}</div>)}
      </FlashArea>
    </aside>
  );
}

function EmergencyRow({ entry, staff, now, selected, onSelect }: { entry: Emergency; staff: boolean; now: number; selected: boolean; onSelect: (id: string) => void }) {
  const rowTitle = staff ? requestTitle(entry) : `Request …${entry.id.slice(-4)}`;
  return (
    <li>
      <button type="button" className="er-row" data-state={entry.state} aria-pressed={selected} aria-label={`Track request ${entry.id}`} onClick={() => onSelect(entry.id)}>
        <span className="er-row__main">
          <strong title={rowTitle}>{rowTitle}</strong>
          <small><StateChip state={entry.state} /><span>{entry.reported_urgency === "urgent" ? "Reported urgent" : "Urgency not specified"}</span><time dateTime={entry.created_at}>{elapsed(entry.created_at, now)}</time></small>
        </span>
        <PriorityChip priority={entry.assigned_priority} />
      </button>
    </li>
  );
}
function EmergencyCase({ item, staff, userId, loading, onRefresh, now }: { item: Emergency; staff: boolean; userId?: string; loading: boolean; onRefresh: () => void; now: number }) {
  const claimHolder = item.claimed_by_user_id ? (item.claimed_by_user_id === userId ? "You" : "Another staff member") : null;
  return (
    <section className="er-case" aria-labelledby="er-case-title">
      <header className="er-case__header">
        <div>
          <p className="er-case__eyebrow">Emergency request <span>…{item.id.slice(-4)}</span></p>
          <h2 id="er-case-title">{staff ? requestTitle(item) : `Your request from ${utcTime(item.created_at)}`}</h2>
        </div>
        <div className="er-case__chips"><StateChip state={item.state} /><PriorityChip priority={item.assigned_priority} /></div>
        <button type="button" disabled={loading} onClick={onRefresh}>Refresh</button>
      </header>
      <dl className="er-facts">
        <div><dt>Submitted</dt><dd><time dateTime={item.created_at}>{utcTime(item.created_at)}</time><small>{elapsed(item.created_at, now)} ago</small></dd></div>
        <div><dt>Last updated</dt><dd><time dateTime={item.updated_at}>{utcTime(item.updated_at)}</time></dd></div>
        <div><dt>Reported urgency (advisory)</dt><dd>{item.reported_urgency === "urgent" ? "Urgent" : "Not specified"}</dd></div>
        <div><dt>Assigned priority</dt><dd>{item.assigned_priority ? `Priority ${item.assigned_priority} of 5` : "Priority not yet assigned"}</dd></div>
        {staff && <div><dt>Contact</dt><dd>{item.synthetic_contact || "None provided"}</dd></div>}
        {staff && <div><dt>Claim</dt><dd>{claimHolder ? <>{claimHolder}{item.claim_expires_at && <small>Lease ends <time dateTime={item.claim_expires_at}>{utcTime(item.claim_expires_at)}</time></small>}</> : "Not claimed"}</dd></div>}
      </dl>
      {staff && item.description && <section className="er-description"><h3>Request description</h3><p>{item.description}</p></section>}
      <details className="owner-identifiers">
        <summary>Details</summary>
        <Facts values={{ "Request ID": item.id, Version: item.version, ...(staff ? { "Patient ID": item.patient_id, "Claimed by": item.claimed_by_user_id } : {}) }} />
      </details>
    </section>
  );
}

export function EmergencyPage({ staff = false, title, subtitle }: { staff?: boolean; title?: string; subtitle?: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [listOpen, setListOpen] = useState(false);
  const { state } = useAuth();
  const userId = state.status === "authenticated" ? state.user.id : undefined;
  const now = useNow();
  const register = useCursorPage<Emergency>("/api/v1/emergencies", revision);
  const firstId = register.items[0]?.id;
  useEffect(() => {
    if (!selected && firstId) setSelected(firstId);
  }, [selected, firstId]);
  const request = useResource<Emergency>(selected ? `/api/v1/emergencies/${selected}` : null, revision);
  const item = request.response?.data;
  const changed = () => setRevision((v) => v + 1);
  const openEntries = register.items.filter((entry) => !terminalStates.includes(entry.state));
  const open = staff ? sortEmergencyQueue(openEntries) : [...openEntries].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const closed = register.items.filter((entry) => terminalStates.includes(entry.state));
  const paged = register.hasNext || register.hasPrevious;
  const counts = [
    { label: "Unassigned", value: open.filter((entry) => entry.assigned_priority === null).length, tone: "neutral" },
    { label: "Priority 1–2", value: open.filter((entry) => (entry.assigned_priority ?? 9) <= 2).length, tone: "urgent" },
    { label: "Claimed", value: register.items.filter((entry) => entry.state === "claimed").length, tone: "claimed" },
  ];
  const registerList = (
    <section className="er-register" data-open={listOpen} aria-labelledby="er-register-title">
      <header className="er-register__header">
        <h2 id="er-register-title">{staff ? "Request queue" : "Your requests"} <span>({register.items.length}{paged ? " on this page" : ""})</span></h2>
        <button type="button" className="er-register__toggle" aria-expanded={listOpen} onClick={() => setListOpen(!listOpen)}>{listOpen ? "Hide requests" : `All requests (${register.items.length})`}</button>
        <button type="button" disabled={register.loading} onClick={register.refresh}>Refresh</button>
      </header>
      {register.loading && <p role="status">Loading emergency requests…</p>}
      {register.error && <p role="alert">{register.error}</p>}
      {register.loaded && !register.loading && register.items.length === 0 && <p>No emergency requests found.</p>}
      <ol className="er-queue">
        {open.map((entry) => <EmergencyRow key={entry.id} entry={entry} staff={staff} now={now} selected={selected === entry.id} onSelect={setSelected} />)}
        {closed.length > 0 && <li className="er-queue__divider" role="presentation"><span>Closed</span></li>}
        {closed.map((entry) => <EmergencyRow key={entry.id} entry={entry} staff={staff} now={now} selected={selected === entry.id} onSelect={setSelected} />)}
      </ol>
      {paged && <div className="er-register__pages"><button type="button" disabled={!register.hasPrevious} onClick={register.previous}>Previous page</button><button type="button" disabled={!register.hasNext} onClick={register.next}>Next page</button></div>}
      <details className="er-lookup"><summary>Open a request by ID</summary><Lookup label="Emergency request ID" onSelect={setSelected} /></details>
    </section>
  );
  const casePanel = (
    <>
      {!selected && !register.loading && <section className="er-case er-case--empty"><DepartmentIcon department="emergency" /><p>Select a request to see its owner-confirmed priority, claim and allowed next steps.</p></section>}
      {request.loading && !item && <p role="status" className="er-case">Loading request…</p>}
      {request.error && <p role="alert" className="er-case">{request.error}</p>}
      {item && <EmergencyCase key={`${item.id}:${item.version}`} item={item} staff={staff} userId={userId} loading={request.loading} onRefresh={request.refresh} now={now} />}
      {item && <NextSteps key={`steps:${item.id}`} item={item} etag={request.response?.etag ?? null} staff={staff} userId={userId} onChange={changed} />}
    </>
  );
  return (
    <div className={`er-desk er-desk--${staff ? "staff" : "patient"}`}>
      {title && (
        <DepartmentSign department="emergency" title={title} subtitle={subtitle ?? ""}>
          {staff && (
            <ul className="er-counts" aria-label={paged ? "Counts in this list page" : "Counts in this list"}>
              {counts.map((count) => <li key={count.label} data-tone={count.tone}><strong>{count.value}</strong><span>{count.label}</span></li>)}
              <li className="er-counts__scope">in this list{paged ? " page" : ""}</li>
            </ul>
          )}
        </DepartmentSign>
      )}
      <p className="er-notice" role="note">Synthetic educational requests only. This prototype does not provide emergency dispatch or certified clinical triage.</p>
      {!staff && (
        <section className="er-intake" aria-labelledby="er-intake-title">
          <h2 id="er-intake-title">New request</h2>
          <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>
            {(profile) => (
              <CommandForm<Emergency>
                title="Submit emergency request"
                reviewLabel="Review request"
                confirmLabel="Send emergency request"
                successMessage="Request sent. It now appears in Your requests."
                path="/api/v1/emergencies"
                fields={[
                  textField("description", "Synthetic request description"),
                  { name: "reported_urgency", label: "Reported urgency (advisory)", kind: "select", required: true, options: ["unspecified", "urgent"], optionLabels: { unspecified: "Not sure", urgent: "Urgent" }, initial: "unspecified" },
                  { name: "synthetic_contact", label: "Synthetic contact", max: 256 },
                ]}
                build={(values) => ({
                  ...buildFields(
                    [
                      textField("description", "Description"),
                      { name: "reported_urgency", label: "Urgency", required: true, options: ["unspecified", "urgent"] },
                      { name: "synthetic_contact", label: "Synthetic contact", max: 256 },
                    ],
                    values,
                  ),
                  patient_id: profile.id,
                })}
                onSuccess={(created) => {
                  setSelected(created.id);
                  changed();
                }}
              />
            )}
          </Resource>
        </section>
      )}
      {staff ? <>{registerList}{casePanel}</> : <div className="er-patient-requests">{registerList}<div className="er-patient-case">{casePanel}</div></div>}
    </div>
  );
}

// Matches the explicit coordinator fixture seed; no external insurer discovery.
const syntheticProviders = [4101,4102,4103].map(id => ({id:String(id),syntheticSlug:`phase4-synthetic-${id}`,policyCodes:["DEMO"]}));
export function InsurancePage() {
  const {state,api}=useAuth();
  return <InsuranceRefreshPanel api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} />;
}
