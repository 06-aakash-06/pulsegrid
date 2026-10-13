import { DepartmentIcon } from "../design/DepartmentIcon";
import { useState } from "react";
import type {
  Consultation,
  Content,
  FinalizeResult,
  Grant,
  MedicalRecord,
  PatientProfile,
  Prescription,
  PrescriptionItemInput,
  RecordSummary,
} from "./models";
import {
  buildFields,
  Collection,
  CommandForm,
  Facts,
  id,
  idField,
  integer,
  Lookup,
  Panel,
  query,
  reasonField,
  Resource,
  Selected,
  textField,
  utc,
  type Field,
  type Values,
} from "./ui";
import { Appointments } from "./patientDoctor";
const clinicalFields = (content?: Content): Field[] =>
  [
    textField("summary", "Summary"),
    textField("assessment", "Assessment"),
    textField("plan", "Plan"),
  ].map((field) => ({
    ...field,
    initial: content?.[field.name as keyof Content],
  }));
function content(values: Values): Content {
  return buildFields(clinicalFields(), values) as unknown as Content;
}
function PrescriptionItems({
  items,
  setItems,
}: {
  items: Values[];
  setItems: (items: Values[]) => void;
}) {
  return (
    <fieldset>
      <legend>Prescription items (optional, maximum 50)</legend>
      {items.map((item, index) => (
        <fieldset key={index}>
          <legend>Medicine {index + 1}</legend>
          {["medicine_id", "quantity", "dosage", "instructions"].map((key) => (
            <label key={key}>
              {
                (
                  {
                    medicine_id: "Medicine ID",
                    quantity: "Quantity",
                    dosage: "Dosage",
                    instructions: "Instructions",
                  } as Record<string, string>
                )[key]
              }{" "}
              {index + 1}
              <input
                value={item[key] ?? ""}
                onChange={(e) =>
                  setItems(
                    items.map((v, i) =>
                      i === index ? { ...v, [key]: e.target.value } : v,
                    ),
                  )
                }
              />
            </label>
          ))}
          <button
            type="button"
            onClick={() => setItems(items.filter((_, i) => i !== index))}
          >
            Remove medicine {index + 1}
          </button>
        </fieldset>
      ))}
      <button
        type="button"
        disabled={items.length >= 50}
        onClick={() => setItems([...items, {}])}
      >
        Add prescribed medicine
      </button>
    </fieldset>
  );
}
function prescriptionItems(items: Values[]): PrescriptionItemInput[] {
  const normalized = items.map((item) => ({
    medicine_id: id((item.medicine_id ?? "").trim()),
    quantity: integer(item.quantity ?? "", 1, 1000000),
    dosage: (item.dosage ?? "").trim(),
    instructions: (item.instructions ?? "").trim(),
  }));
  if (new Set(normalized.map((i) => i.medicine_id)).size !== normalized.length)
    throw new Error("Prescribe each medicine only once.");
  if (
    normalized.some(
      (i) =>
        !i.dosage ||
        !i.instructions ||
        i.dosage.length > 4000 ||
        i.instructions.length > 4000,
    )
  )
    throw new Error(
      "Dosage and instructions must contain 1 to 4000 characters.",
    );
  return normalized;
}
export function ClinicalFacts({ value }: { value: Content }) {
  return (
    <div className="clinical-content"><Facts
      values={{
        Summary: value.summary,
        Assessment: value.assessment,
        Plan: value.plan,
      }}
    /></div>
  );
}
function ConsultationEditor({
  item,
  etag,
  refresh,
}: {
  item: Consultation;
  etag: string | null;
  refresh: () => void;
}) {
  const [items, setItems] = useState<Values[]>([]);
  const [finalized, setFinalized] = useState<FinalizeResult | null>(null);
  return (
    <>
      <Facts
        values={{
          "Consultation ID": item.id,
          "Appointment ID": item.appointment_id,
          "Patient ID": item.patient_id,
          Status: item.status,
          Revision: item.revision,
        }}
      />
      <ClinicalFacts value={item.clinical_content} />
      {item.status === "draft" && !finalized && (
        <>
          <CommandForm
            title="Save consultation draft"
            path={`/api/v1/records/consultations/${item.id}`}
            method="PATCH"
            conditional
            etag={etag}
            fields={clinicalFields(item.clinical_content)}
            build={(values) => ({ clinical_content: content(values) })}
            onSuccess={refresh}
          />
          <CommandForm<FinalizeResult>
            title="Finalize consultation"
            path={`/api/v1/records/consultations/${item.id}/finalize`}
            conditional
            etag={etag}
            build={() => ({ prescription_items: prescriptionItems(items) })}
            onSuccess={(result) => setFinalized(result)}
            notice="Finalization freezes the draft and creates an immutable medical record and optional prescription. Clinical work blocks appointment cancellation and rescheduling."
          >
            <PrescriptionItems items={items} setItems={setItems} />
          </CommandForm>
        </>
      )}
      {finalized && (
        <div role="status">
          <p>
            Finalized consultation {finalized.consultation.id}. Medical record
            ID: {finalized.record.id}. Prescription ID:{" "}
            {finalized.prescription?.id ?? "None"}.
          </p>
          <button onClick={refresh}>Reload finalized consultation</button>
        </div>
      )}
    </>
  );
}
export function Consultations({ doctor = false }: { doctor?: boolean }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  return (
    <div className="consultation-clinical">
      {doctor && (
        <>
          <div className="clinical-tools"><details className="assigned-appointments"><summary>Assigned appointments</summary><Appointments doctor /></details>
          <details className="new-consultation" open={!selected}><summary>New consultation</summary><Panel title="Create assigned consultation">
            <CommandForm<Consultation>
              title="Create consultation"
              path="/api/v1/records/consultations"
              fields={[
                idField("appointment_id", "Assigned appointment ID"),
                ...clinicalFields(),
              ]}
              build={(values) => ({
                appointment_id: id(values.appointment_id.trim()),
                clinical_content: content(values),
              })}
              onSuccess={(item) => {
                setSelected(item.id);
                setRevision((v) => v + 1);
              }}
            />
          </Panel></details></div>
        </>
      )}
      <section className="consultation-register">
      <Collection<Consultation>
        title="Consultations"
        path="/api/v1/records/consultations"
        revision={revision}
        renderItem={(item) => (
          <>
            <p>
              Consultation {item.id} • Appointment {item.appointment_id} •{" "}
              {item.status}
            </p>
            <button aria-label={`View consultation ${item.id}`} onClick={() => setSelected(item.id)}>
              View consultation {item.id}
            </button>
          </>
        )}
      />
      <Lookup label="Consultation ID" onSelect={setSelected} />
      </section><section className="clinical-editor">{!selected && <Panel title="Consultation room"><div className="resource-empty"><DepartmentIcon department="consultation"/><strong>Open a consultation</strong><p>Select an authorized consultation or create one for an assigned appointment.</p></div></Panel>}
      <Selected<Consultation>
        path={selected ? `/api/v1/records/consultations/${selected}` : null}
      >
        {(item, etag, refresh) =>
          doctor ? (
            <ConsultationEditor
              item={item}
              etag={etag}
              refresh={() => {
                refresh();
                setRevision((v) => v + 1);
              }}
            />
          ) : (
            <>
              <Facts
                values={{
                  "Consultation ID": item.id,
                  "Appointment ID": item.appointment_id,
                  Status: item.status,
                }}
              />
              <ClinicalFacts value={item.clinical_content} />
            </>
          )
        }
      </Selected>
    </section></div>
  );
}
function History({
  patientId,
  doctor,
}: {
  patientId: string;
  doctor: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  return (
    <div className="record-history"><aside className="visit-timeline">
      <Collection<RecordSummary>
        title="Medical history"
        path={`/api/v1/records/patients/${patientId}`}
        revision={revision}
        onFirstItem={item=>{if(!selected)setSelected(item.id);}}
        renderItem={(item) => (
          <>
            <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('en',{timeZone:'UTC',dateStyle:'medium',timeStyle:'short'})} UTC</time><strong>Clinical record</strong><p>Revision {item.revision}</p>
            <button aria-label={`View record ${item.id}`} onClick={() => setSelected(item.id)}>
              Open clinical document →
            </button>
          </>
        )}
      />
      <Lookup label="Medical record ID" onSelect={setSelected} />
      </aside><section className="active-dossier">{!selected && <Panel title="Clinical dossier"><div className="resource-empty"><DepartmentIcon department="records"/><strong>Choose a visit</strong><p>Open a record from your timeline to read its authorized summary, assessment and plan.</p></div></Panel>}
      <Selected<MedicalRecord>
        path={selected ? `/api/v1/records/${selected}` : null}
      >
        {(record, etag, refresh) => (
          <>
            <header className="record-document-heading"><DepartmentIcon department="records"/><div><h3>Clinical record …{record.id.slice(-4)}</h3><p>Revision {record.revision} · Records service</p></div></header>
            <div className="clinical-dossier-body"><ClinicalFacts value={record.content}/><aside className="record-document-index"><h3>Document history</h3><Facts values={{Revision:record.revision,Supersedes:record.supersedes_id?`Record …${record.supersedes_id.slice(-4)}`:"Original document"}}/><details className="owner-identifiers"><summary>Owner references</summary><Facts values={{"Record ID":record.id,"Consultation ID":record.consultation_id}}/></details>{!doctor&&<nav aria-label="Related care"><h3>Related care</h3><a href="/patient/prescriptions">Prescriptions →</a><a href="/patient/journey">Patient journey →</a></nav>}</aside></div>
            {doctor && (
              <CommandForm<MedicalRecord>
                title="Amend medical record"
                path={`/api/v1/records/${record.id}/amendments`}
                conditional
                etag={etag}
                fields={[...clinicalFields(record.content), reasonField]}
                build={(values) => ({
                  content: content(values),
                  reason:
                    values.reason.trim() ||
                    (() => {
                      throw new Error("Reason is required.");
                    })(),
                })}
                onSuccess={(item) => {
                  setSelected(item.id);
                  setRevision((v) => v + 1);
                  refresh();
                }}
                notice="Historical amendments require an active clinical hold or an unexpired patient records grant. Original text is preserved."
              />
            )}
          </>
        )}
      </Selected>
    </section></div>
  );
}
function Grants({ patientId }: { patientId: string }) {
  const [grant, setGrant] = useState<Grant | null>(null);
  const [grantEtag, setGrantEtag] = useState<string | null>(null);
  return (
    <Panel title="Historical access grants">
      <CommandForm<Grant>
        title="Grant historical access"
        path="/api/v1/records/access-grants"
        fields={[
          idField("grantee_user_id", "Doctor user ID"),
          {
            name: "scope",
            label: "Access scope",
            kind: "select",
            required: true,
            options: ["records:read", "prescriptions:read"],
          },
          { name: "expires_at", label: "Expiry (UTC)", required: true },
        ]}
        build={(values) => {
          const expiry = utc(values.expires_at);
          const duration = Date.parse(expiry) - Date.now();
          if (duration <= 0 || duration > 30 * 86400000)
            throw new Error("Expiry must be in the future and within 30 days.");
          if (!["records:read", "prescriptions:read"].includes(values.scope))
            throw new Error("Select an access scope.");
          return {
            patient_id: patientId,
            grantee_user_id: id(values.grantee_user_id.trim()),
            scope: values.scope,
            expires_at: expiry,
          };
        }}
        onSuccess={(item, etag) => {
          setGrant(item);
          setGrantEtag(etag);
        }}
      />
      {grant && (
        <>
          <p>
            Grant {grant.id}: {grant.scope} until {grant.expires_at}. This page retains its version for revocation while open.
          </p>
          <CommandForm
            title="Revoke access grant"
            path={`/api/v1/records/access-grants/${grant.id}`}
            method="DELETE"
            conditional
            etag={grantEtag}
            onSuccess={() => setGrant(null)}
          />
        </>
      )}
      <p>
        There is no grant list or lookup endpoint in the frozen API. Older
        grants cannot be reloaded here.
      </p>
    </Panel>
  );
}
export function RecordsPage({ doctor = false }: { doctor?: boolean }) {
  const [patientId, setPatientId] = useState<string | null>(null);
  return (
    <>
      {doctor ? (
        <>
          <Lookup
            label="Patient ID for authorized history"
            onSelect={setPatientId}
          />
          {patientId && (
            <History key={patientId} patientId={patientId} doctor />
          )}
        </>
      ) : (
        <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>
          {(profile) => (
            <>
              <div className="record-patient-strip"><DepartmentIcon department="reception"/><strong>{profile.display_name.startsWith("Synthetic")?"Your clinical dossier":profile.display_name}</strong><span>Authorized medical history</span><small>Synthetic hospital data</small></div>
              <nav className="record-document-tabs" aria-label="Clinical documents"><span>Visit History</span><a href="/patient/prescriptions">Prescriptions</a><a href="/patient/journey">Care Journey</a></nav>
              <History patientId={profile.id} doctor={false} />
              <details className="record-grants"><summary>Record access permissions</summary><Grants patientId={profile.id} /></details>
            </>
          )}
        </Resource>
      )}
      <details className="record-consultations"><summary>Consultation register</summary><Consultations doctor={false} /></details>
    </>
  );
}
export function PrescriptionDetail({
  prescription,
}: {
  prescription: Prescription;
}) {
  return (
    <>
      <Facts
        values={{
          "Prescription ID": prescription.id,
          "Consultation ID": prescription.consultation_id,
          "Patient ID": prescription.patient_id,
          State: prescription.state,
          Revision: prescription.revision,
        }}
      />
      {prescription.items.map((item) => (
        <Facts
          key={item.id}
          values={{
            "Item ID": item.id,
            "Medicine ID": item.medicine_id,
            Quantity: item.quantity,
            Dosage: item.dosage,
            Instructions: item.instructions,
          }}
        />
      ))}
    </>
  );
}
export function Prescriptions({
  doctor = false,
  pharmacist = false,
  onSelect,
}: {
  doctor?: boolean;
  pharmacist?: boolean;
  onSelect?: (prescription: Prescription) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  return (
    <div className="prescription-workspace">
      {!pharmacist && (
        <Collection<Prescription>
          title="Prescriptions"
          revision={revision}
          path={query("/api/v1/records/prescriptions", {})}
          renderItem={(item) => (
            <>
              <p>
                Prescription {item.id} • {item.state} • Consultation{" "}
                {item.consultation_id}
              </p>
              <button aria-label={`View prescription ${item.id}`} onClick={() => setSelected(item.id)}>
                View prescription {item.id}
              </button>
            </>
          )}
        />
      )}
      <Lookup label="Prescription ID" onSelect={setSelected} />
      <Selected<Prescription>
        path={selected ? `/api/v1/records/prescriptions/${selected}` : null}
      >
        {(prescription, etag, refresh) => (
          <>
            <PrescriptionDetail prescription={prescription} />
            {onSelect && prescription.state === "issued" && (
              <button onClick={() => onSelect(prescription)}>
                Request medicines from prescription {prescription.id}
              </button>
            )}
            {doctor && prescription.state === "issued" && (
              <CommandForm
                title="Revoke prescription"
                path={`/api/v1/records/prescriptions/${prescription.id}/revoke`}
                conditional
                etag={etag}
                fields={[reasonField]}
                onSuccess={() => {
                  refresh();
                  setRevision((v) => v + 1);
                }}
                notice="Revocation stops new validated fulfillment. Existing reservations require Pharmacy revalidation or release; no automatic event delivery is assumed."
              />
            )}
          </>
        )}
      </Selected>
      {doctor && <RecordsPage doctor />}
    </div>
  );
}
