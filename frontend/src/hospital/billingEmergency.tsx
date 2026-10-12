import { InsuranceEstimatePanel, InsuranceRefreshPanel } from "../phase4";
import { useState } from "react";
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
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [payment, setPayment] = useState<Payment | null>(null);
  return (
    <>
      <p>
        Payments are simulated. Do not enter card, bank or real payment
        credentials. Invoice balances include only charges explicitly imported
        by billing staff.
      </p>
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
      <Collection<Invoice>
        title="Invoices"
        path="/api/v1/billing/invoices"
        revision={revision}
        renderItem={(item) => (
          <>
            <Facts
              values={{
                "Invoice ID": item.id,
                "Appointment ID": item.appointment_id,
                Status: item.status,
                Total: money(item.total_minor),
                Balance: money(item.balance_minor),
              }}
            />
            <button
              onClick={() => {
                setSelected(item.id);
                setPayment(null);
              }}
            >
              View invoice {item.id}
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
      <Selected<Invoice>
        path={selected ? `/api/v1/billing/invoices/${selected}` : null}
      >
        {(invoice, etag, refresh) => {
          const changed = () => {
            refresh();
            setRevision((v) => v + 1);
          };
          return (
            <>
              <Facts
                values={{
                  "Invoice ID": invoice.id,
                  "Patient ID": invoice.patient_id,
                  "Appointment ID": invoice.appointment_id,
                  Status: invoice.status,
                  Total: money(invoice.total_minor),
                  Paid: money(invoice.paid_minor),
                  Balance: money(invoice.balance_minor),
                }}
              />
              <InsuranceEstimatePanel api={api} roleHints={authState.status === "authenticated" ? authState.roleHints : []} invoiceId={invoice.id} providerChoices={syntheticProviders} />
              {invoice.items.length === 0 && (
                <p>No charges have been imported.</p>
              )}
              {invoice.items.map((item) => (
                <Facts
                  key={item.id}
                  values={{
                    Charge: item.charge_code,
                    Source: `${item.source_service} ${item.source_item_id}`,
                    Quantity: item.quantity,
                    "Unit price": money(item.unit_amount_minor),
                    "Tariff revision": item.tariff_revision,
                  }}
                />
              ))}
              {staff && (
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
                  onSuccess={changed}
                  notice="Source IDs must belong to this invoice's appointment and patient. Missing imports are not automatically detected. Prices come from Billing tariffs."
                />
              )}
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
              <Collection<Payment>
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
              />
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
      {staff && <Tariffs />}
    </>
  );
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
    <>
      <p>
        Synthetic educational requests only. This prototype does not provide
        emergency dispatch or certified clinical triage.
      </p>
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
        renderItem={(item) => (
          <>
            <Facts
              values={{
                "Request ID": item.id,
                State: item.state,
                "Reported urgency": item.reported_urgency,
                "Assigned priority": item.assigned_priority,
                "Updated (UTC)": item.updated_at,
              }}
            />
            <button onClick={() => setSelected(item.id)}>
              Track request {item.id}
            </button>
          </>
        )}
      />
      <Lookup label="Emergency request ID" onSelect={setSelected} />
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
            <>
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
            </>
          );
        }}
      </Selected>
    </>
  );
}

// Matches the explicit coordinator fixture seed; no external insurer discovery.
const syntheticProviders = [4101,4102,4103].map(id => ({id:String(id),syntheticSlug:`phase4-synthetic-${id}`,policyCodes:["DEMO"]}));
export function InsurancePage() {
  const {state,api}=useAuth();
  return <InsuranceRefreshPanel api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} />;
}
