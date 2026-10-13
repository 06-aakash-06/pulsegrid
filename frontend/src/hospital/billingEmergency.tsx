import { DepartmentIcon } from "../design/DepartmentIcon";
import { InsuranceEstimatePanel, InsuranceRefreshPanel } from "../phase4";
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import type {
  Emergency,
  Invoice,
  PatientProfile,
  Payment,
  Tariff,
} from "./models";
import {
  buildFields,
  Collection,
  CommandForm,
  Facts,
  id,
  idField,
  ids,
  integer,
  Lookup,
  money,
  Panel,
  reasonField,
  Resource,
  Selected,
  textField,
  type Field,
} from "./ui";
export function BillingPage({ staff = false }: { staff?: boolean }) {
  const { state: authState, api }=useAuth();
  const location = useLocation();
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [payment, setPayment] = useState<Payment | null>(null);
  return (
    <div className="billing-workbench">
      <p className="billing-service-note">
        Payments are simulated. Do not enter card, bank or real payment
        credentials. Invoice balances include only charges explicitly imported
        by billing staff.
      </p>
      <section className="billing-source-desk">
      {staff && (
        <Panel title="Create invoice">
          <CommandForm<Invoice>
            title="Create invoice"
            path="/api/v1/billing/invoices"
            fields={[idField("appointment_id", "Appointment ID")]}
            build={(values) => ({
              appointment_id: id(values.appointment_id.trim()),
              currency: "INR",
            })}
            onSuccess={(item) => {
              setSelected(item.id);
              setRevision((v) => v + 1);
            }}
          />
        </Panel>
      )}
      {staff && selected && <InvoiceChargeSources invoiceId={selected} revision={revision} onChange={()=>setRevision(v=>v+1)}/>}
      <details className="invoice-register" open={!staff||location.pathname.endsWith("/invoices")||location.pathname.endsWith("/payments")}><summary>Invoice register</summary>
      <Collection<Invoice>
        title="Invoices"
        path="/api/v1/billing/invoices"
        revision={revision}
        onFirstItem={item=>{if(!selected)setSelected(item.id);}}
        renderItem={(item) => (
          <>
            <div className="billing-ledger-row"><span>Invoice …{item.id.slice(-4)}</span><strong>{money(item.total_minor)}</strong><span className="owner-state">{item.status}</span><small>Balance {money(item.balance_minor)}</small></div>
            <details className="owner-identifiers"><summary>Reference identifiers</summary><Facts values={{"Invoice ID":item.id,"Appointment ID":item.appointment_id}}/></details>
            <button
              aria-label={`View invoice ${item.id}`}
              onClick={() => {
                setSelected(item.id);
                setPayment(null);
              }}
            >
              Open invoice →
            </button>
          </>
        )}
      />
      <Lookup
        label="Invoice ID"
        onSelect={(value) => {
          setSelected(value);
          setPayment(null);
        }}
      />
      </details></section><aside className="invoice-receipt">{!selected && <Panel title="Current bill"><div className="resource-empty"><DepartmentIcon department="billing"/><strong>Open an invoice</strong><p>Choose an invoice to review its authoritative line items, insurance estimate and balance.</p></div></Panel>}
      <Selected<Invoice>
        path={selected ? `/api/v1/billing/invoices/${selected}` : null}
        revision={revision}
      >
        {(invoice, etag, refresh) => {
          const changed = () => {
            refresh();
            setRevision((v) => v + 1);
          };
          return (
            <>
              <div className="invoice-status-strip"><strong>Invoice …{invoice.id.slice(-4)}</strong><span className="owner-state">{invoice.status}</span></div>
              <Facts values={{Total:money(invoice.total_minor),Paid:money(invoice.paid_minor),Balance:money(invoice.balance_minor)}}/>
              <details className="owner-identifiers"><summary>Patient, visit and invoice references</summary><Facts values={{"Invoice ID":invoice.id,"Patient ID":invoice.patient_id,"Appointment ID":invoice.appointment_id}}/></details>
              {invoice.items.length === 0 && (
                <p>No charges have been imported.</p>
              )}
              <div className="invoice-line-scroll" tabIndex={0} role="region" aria-label="Invoice line items"><table className="invoice-lines"><caption>Itemized invoice</caption><thead><tr><th scope="col">Charge / source</th><th scope="col">Qty</th><th scope="col">Unit price</th><th scope="col">Amount</th></tr></thead><tbody>{invoice.items.map(item=><tr key={item.id}><th scope="row">{item.charge_code==="consultation"?"Consultation":"Medicine"}<small>{item.source_service}</small><details className="owner-identifiers"><summary>Source</summary>{item.charge_code} · {item.source_item_id} · Tariff {item.tariff_revision}</details></th><td>{item.quantity}</td><td>{money(item.unit_amount_minor)}</td><td>{money(item.quantity*item.unit_amount_minor)}</td></tr>)}</tbody></table></div>
              <div className="invoice-total"><span>Balance due</span><strong>{money(invoice.balance_minor)}</strong></div>
              {invoice.balance_minor > 0 && (
                <CommandForm<Payment>
                  title="Submit simulated payment"
                  path={`/api/v1/billing/invoices/${invoice.id}/payments`}
                  conditional
                  etag={etag}
                  fields={[
                    {
                      name: "amount_minor",
                      label: "Amount in paise (integer)",
                      kind: "number",
                      required: true,
                      min: 1,
                      max: invoice.balance_minor,
                      initial: String(invoice.balance_minor),
                    },
                    {
                      name: "simulated_outcome",
                      label: "Simulated outcome",
                      kind: "select",
                      required: true,
                      options: ["success", "decline"],
                      initial: "success",
                    },
                  ]}
                  build={(values) => ({
                    amount_minor: integer(
                      values.amount_minor,
                      1,
                      invoice.balance_minor,
                    ),
                    currency: "INR",
                    simulated_outcome: values.simulated_outcome,
                  })}
                  onSuccess={(result) => {
                    setPayment(result);
                    changed();
                  }}
                />
              )}
              <details className="insurance-receipt"><summary>Insurance estimates</summary><InsuranceEstimatePanel api={api} roleHints={authState.status === "authenticated" ? authState.roleHints : []} invoiceId={invoice.id} providerChoices={syntheticProviders} /></details>
              <details className="payment-history"><summary>Payment history</summary><Collection<Payment>
                title="Invoice payments"
                path={`/api/v1/billing/invoices/${invoice.id}/payments`}
                renderItem={(item) => (
                  <Facts
                    values={{
                      "Payment ID": item.id,
                      Amount: money(item.amount_minor),
                      Status: item.status,
                    }}
                  />
                )}
              /></details>
            </>
          );
        }}
      </Selected>
      {payment && (
        <p role="status">
          Payment {payment.id}:{" "}
          {payment.status === "declined"
            ? "simulated decline recorded; balance was not paid"
            : "simulated success recorded"}
          . Amount {money(payment.amount_minor)}.
        </p>
      )}
      </aside>
      {staff && <details className="billing-tariff-desk"><summary>Tariffs and charge pricing</summary><Tariffs /></details>}
    </div>
  );
}
function InvoiceChargeSources({invoiceId,revision,onChange}:{invoiceId:string;revision:number;onChange:()=>void}) {
  return <Panel title="Charge sources"><div className="charge-source-tabs"><span>Consultation · Records</span><span>Medicines · Pharmacy</span></div><Resource<Invoice> path={`/api/v1/billing/invoices/${invoiceId}`} revision={revision}>{(invoice,etag)=>(
<CommandForm
                  title="Import charges manually"
                  path={`/api/v1/billing/invoices/${invoice.id}/charges`}
                  conditional
                  etag={etag}
                  fields={[
                    idField(
                      "consultation_id",
                      "Finalized consultation ID",
                      false,
                    ),
                    {
                      name: "dispensing_ids",
                      label: "Completed dispensing IDs (comma separated)",
                    },
                  ]}
                  build={(values) => {
                    const consultationId = values.consultation_id.trim();
                    const dispensingIds = ids(values.dispensing_ids);
                    if (!consultationId && !dispensingIds.length)
                      throw new Error(
                        "Select at least one consultation or dispensing source.",
                      );
                    return {
                      ...(consultationId
                        ? { consultation_id: id(consultationId) }
                        : {}),
                      dispensing_ids: dispensingIds,
                    };
                  }}
                  onSuccess={onChange}
                  notice="Source IDs must belong to this invoice's appointment and patient. Missing imports are not automatically detected. Prices come from Billing tariffs."
                />
  )}</Resource></Panel>;
}
function Tariffs() {
  const [revision, setRevision] = useState(0);
  const fields: Field[] = [
    {
      name: "charge_code",
      label: "Charge code (consultation or medicine:ID)",
      required: true,
      max: 128,
    },
    {
      name: "unit_amount_minor",
      label: "Unit amount in paise",
      kind: "number",
      required: true,
      min: 0,
    },
  ];
  return (
    <>
      <Panel title="Tariff revisions">
        <CommandForm
          title="Create tariff revision"
          path="/api/v1/billing/tariffs"
          fields={fields}
          build={(values) => {
            const body = buildFields(fields, values);
            const code = values.charge_code.trim();
            if (code !== "consultation") {
              if (!code.startsWith("medicine:"))
                throw new Error("Use consultation or medicine:ID.");
              id(code.slice(9));
            }
            return { ...body, currency: "INR" };
          }}
          onSuccess={() => setRevision((v) => v + 1)}
        />
      </Panel>
      <Collection<Tariff>
        title="Tariffs"
        path="/api/v1/billing/tariffs"
        revision={revision}
        renderItem={(item) => (
          <Facts
            values={{
              "Tariff ID": item.id,
              Code: item.charge_code,
              Revision: item.revision,
              "Unit amount": money(item.unit_amount_minor),
            }}
          />
        )}
      />
    </>
  );
}
export function EmergencyPage({ staff = false }: { staff?: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const { state } = useAuth();
  const userId = state.status === "authenticated" ? state.user.id : undefined;
  return (
    <div className="emergency-workbench">
      <p className="emergency-service-note">
        Synthetic educational requests only. This prototype does not provide
        emergency dispatch or certified clinical triage.
      </p>
      <section className="emergency-register">
      {!staff && (
        <Panel title="Submit emergency request">
          <Resource<PatientProfile> path="/api/v1/patients/me">
            {(profile) => (
              <CommandForm<Emergency>
                title="Submit emergency request"
                path="/api/v1/emergencies"
                fields={[
                  textField("description", "Synthetic request description"),
                  {
                    name: "reported_urgency",
                    label: "Reported urgency (advisory)",
                    kind: "select",
                    required: true,
                    options: ["unspecified", "urgent"],
                    initial: "unspecified",
                  },
                  {
                    name: "synthetic_contact",
                    label: "Synthetic contact",
                    max: 256,
                  },
                ]}
                build={(values) => ({
                  ...buildFields(
                    [
                      textField("description", "Description"),
                      {
                        name: "reported_urgency",
                        label: "Urgency",
                        required: true,
                        options: ["unspecified", "urgent"],
                      },
                      {
                        name: "synthetic_contact",
                        label: "Synthetic contact",
                        max: 256,
                      },
                    ],
                    values,
                  ),
                  patient_id: profile.id,
                })}
                onSuccess={(item) => {
                  setSelected(item.id);
                  setRevision((v) => v + 1);
                }}
              />
            )}
          </Resource>
        </Panel>
      )}
      <Collection<Emergency>
        title="Emergency requests"
        path="/api/v1/emergencies"
        revision={revision}
        onFirstItem={item=>{if(!selected)setSelected(item.id);}}
        renderItem={(item) => (
          <>
            <div className="emergency-triage-row"><DepartmentIcon department="reception"/><strong>Request …{item.id.slice(-4)}</strong><span className="owner-state">{item.state}</span><span>{item.assigned_priority?`Priority ${item.assigned_priority}`:item.reported_urgency}</span><time>{new Date(item.updated_at).toLocaleTimeString('en',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'})} UTC</time></div>
            <button aria-label={`Track request ${item.id}`} onClick={() => setSelected(item.id)}>
              Review request →
            </button>
          </>
        )}
      />
      <Lookup label="Emergency request ID" onSelect={setSelected} />
      </section><section className="emergency-active">{!selected && <Panel title="Active request"><div className="resource-empty"><DepartmentIcon department="emergency"/><strong>Select an emergency request</strong><p>Review a request to see its owner-confirmed priority, claim and allowed next actions.</p></div></Panel>}
      <Selected<Emergency>
        path={selected ? `/api/v1/emergencies/${selected}` : null}
      >
        {(item, etag, refresh) => {
          const changed = () => {
            refresh();
            setRevision((v) => v + 1);
          };
          const terminal = ["resolved", "cancelled"].includes(item.state);
          const ownedClaim = !!userId && item.claimed_by_user_id === userId;
          return (
            <div className="emergency-case-layout">
              <Facts
                values={{
                  "Request ID": item.id,
                  State: item.state,
                  "Reported urgency": item.reported_urgency,
                  "Assigned priority": item.assigned_priority,
                  "Created (UTC)": item.created_at,
                  "Updated (UTC)": item.updated_at,
                }}
              />
              {staff && (
                <Facts
                  values={{
                    "Patient ID": item.patient_id,
                    Description: item.description,
                    "Synthetic contact": item.synthetic_contact,
                    "Claimed by": item.claimed_by_user_id,
                    "Claim expiry (UTC)": item.claim_expires_at,
                  }}
                />
              )}
              {staff && !terminal && (
                <CommandForm
                  title="Set priority"
                  path={`/api/v1/emergencies/${item.id}/priority`}
                  method="PATCH"
                  conditional
                  etag={etag}
                  fields={[
                    {
                      name: "assigned_priority",
                      label: "Assigned priority (1 highest, 5 lowest)",
                      kind: "number",
                      min: 1,
                      max: 5,
                      required: true,
                    },
                    reasonField,
                  ]}
                  onSuccess={changed}
                />
              )}
              {staff && item.state === "triaged" && (
                <CommandForm
                  title="Claim request"
                  path={`/api/v1/emergencies/${item.id}/claim`}
                  conditional
                  etag={etag}
                  onSuccess={changed}
                  notice="Claims have a 15-minute lease. Reload before processing to check the current claim."
                />
              )}
              {staff && ownedClaim && item.state === "claimed" && (
                <CommandForm
                  title="Release claim"
                  path={`/api/v1/emergencies/${item.id}/release`}
                  conditional
                  etag={etag}
                  fields={[reasonField]}
                  onSuccess={changed}
                />
              )}
              {staff && ownedClaim && item.state === "claimed" && (
                <CommandForm
                  title="Start processing"
                  path={`/api/v1/emergencies/${item.id}/transitions`}
                  conditional
                  etag={etag}
                  fields={[reasonField]}
                  build={(values) => ({
                    ...buildFields([reasonField], values),
                    state: "processing",
                  })}
                  onSuccess={changed}
                />
              )}
              {staff && ownedClaim && item.state === "processing" && (
                <CommandForm
                  title="Resolve request"
                  path={`/api/v1/emergencies/${item.id}/transitions`}
                  conditional
                  etag={etag}
                  fields={[reasonField]}
                  build={(values) => ({
                    ...buildFields([reasonField], values),
                    state: "resolved",
                  })}
                  onSuccess={changed}
                />
              )}
              {(["submitted", "triaged"].includes(item.state) ||
                (staff && item.state === "claimed")) && (
                <CommandForm
                  title="Cancel emergency request"
                  path={`/api/v1/emergencies/${item.id}/transitions`}
                  conditional
                  etag={etag}
                  fields={[reasonField]}
                  build={(values) => ({
                    ...buildFields([reasonField], values),
                    state: "cancelled",
                  })}
                  onSuccess={changed}
                />
              )}
            </div>
          );
        }}
      </Selected>
    </section></div>
  );
}

// Matches the explicit coordinator fixture seed; no external insurer discovery.
const syntheticProviders = [4101,4102,4103].map(id => ({id:String(id),syntheticSlug:`phase4-synthetic-${id}`,policyCodes:["DEMO"]}));
export function InsurancePage() {
  const {state,api}=useAuth();
  return <InsuranceRefreshPanel api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} />;
}
