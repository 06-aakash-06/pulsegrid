import { DepartmentIcon } from "../design/DepartmentIcon";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { DepartmentSign } from "../design/DepartmentSign";
import { useCursorPage } from "./pharmacyRoom";
import type {
  Consultation,
  Content,
  Doctor,
  FinalizeResult,
  Grant,
  MedicalRecord,
  Medicine,
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
  useResource,
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
export function ClinicalSheet({ value }: { value: Content }) {
  return (
    <div className="dossier-clinical">
      {(["summary", "assessment", "plan"] as const).map((key) => (
        <section key={key}>
          <h3>{key === "summary" ? "Summary" : key === "assessment" ? "Assessment" : "Plan"}</h3>
          <p>{value[key]}</p>
        </section>
      ))}
    </div>
  );
}
function MedicineName({ medicineId }: { medicineId: string }) {
  const medicine = useResource<Medicine>(`/api/v1/pharmacy/medicines/${medicineId}`);
  const name = medicine.response?.data.name;
  return <>{name && !name.startsWith("Synthetic") ? name : `Medicine …${medicineId.slice(-4)}`}</>;
}
function longDate(value: string) {
  return new Date(value).toLocaleDateString("en-IN", { timeZone: "UTC", day: "numeric", month: "long", year: "numeric" });
}
function shortDateTime(value: string) {
  return `${new Date(value).toLocaleString("en-IN", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC`;
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
      <header className="dossier-header" data-check="records-dossier-header">
        <div><p className="dossier-eyebrow">{item.status === "draft" ? "Draft consultation" : "Finalized consultation"}</p><h2>Consultation for visit …{item.appointment_id.slice(-4)}</h2><p>Revision {item.revision}</p></div>
        <span className="owner-state" data-state={item.status}>{item.status === "draft" ? "Draft" : "Finalized"}</span>
        <button type="button" onClick={refresh}>Refresh</button>
      </header>
      <details className="owner-identifiers"><summary>Details</summary>      <Facts
        values={{
          "Consultation ID": item.id,
          "Appointment ID": item.appointment_id,
          "Patient ID": item.patient_id,
          Status: item.status,
          Revision: item.revision,
        }}
      />
</details>
      <ClinicalSheet value={item.clinical_content} />
      {item.status === "draft" && !finalized && (
        <>
          <CommandForm
            title="Save consultation draft"
            reviewLabel="Review draft"
            confirmLabel="Save draft"
            successMessage="Draft saved."
            path={`/api/v1/records/consultations/${item.id}`}
            method="PATCH"
            conditional
            etag={etag}
            onReload={refresh}
            reloadLabel="Reload consultation"
            fields={clinicalFields(item.clinical_content)}
            build={(values) => ({ clinical_content: content(values) })}
            onSuccess={refresh}
          />
          <div className="consultation-finalize">
          <CommandForm<FinalizeResult>
            title="Finalize consultation"
            reviewLabel="Review finalization"
            confirmLabel="Finalize consultation"
            successMessage="Consultation finalized."
            path={`/api/v1/records/consultations/${item.id}/finalize`}
            conditional
            etag={etag}
            onReload={refresh}
            reloadLabel="Reload consultation"
            build={() => ({ prescription_items: prescriptionItems(items) })}
            onSuccess={(result) => {
              setFinalized(result);
              refresh();
            }}
            notice="Finalization freezes the draft and creates an immutable medical record and optional prescription. Clinical work blocks appointment cancellation and rescheduling."
          >
            <PrescriptionItems items={items} setItems={setItems} />
          </CommandForm>
          </div>
        </>
      )}
      {finalized && (
        <p role="status" className="command-receipt">
          Consultation finalized. Medical record …{finalized.record.id.slice(-4)}
          {finalized.prescription ? ` and prescription …${finalized.prescription.id.slice(-4)} were` : " was"} created.
        </p>
      )}
    </>
  );
}
export function Consultations({ doctor = false, title, subtitle }: { doctor?: boolean; title?: string; subtitle?: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const register = useCursorPage<Consultation>("/api/v1/records/consultations", revision);
  const firstId = register.items[0]?.id;
  useEffect(() => {
    if (!selected && firstId) setSelected(firstId);
  }, [selected, firstId]);
  const current = useResource<Consultation>(selected ? `/api/v1/records/consultations/${selected}` : null, revision);
  const item = current.response?.data;
  return (
    <div className={`dossier-room dossier-room--consultations${doctor ? " dossier-room--doctor" : ""}`}>
      {title && <DepartmentSign department="records" title={title} subtitle={subtitle ?? ""} />}
      <section className="dossier-timeline" aria-labelledby="consultation-register-title">
        <div className="dossier-panel-heading"><h2 id="consultation-register-title">{doctor ? "Your consultations" : "Consultations"}</h2><button type="button" disabled={register.loading} onClick={register.refresh}>Refresh</button></div>
        {register.loading && <p role="status">Loading consultations…</p>}
        {register.error && <p role="alert">{register.error}</p>}
        {register.loaded && !register.loading && register.items.length === 0 && <p>No consultations found.</p>}
        <ol className="visit-list">
          {register.items.map((entry) => (
            <li key={entry.id}>
              <button type="button" className="visit-entry" aria-pressed={selected === entry.id} aria-label={`View consultation ${entry.id}`} onClick={() => setSelected(entry.id)}>
                <strong>Visit …{entry.appointment_id.slice(-4)}</strong>
                <span className="owner-state" data-state={entry.status}>{entry.status === "draft" ? "Draft" : "Finalized"}</span>
                <small>Consultation …{entry.id.slice(-4)}</small>
              </button>
            </li>
          ))}
        </ol>
        {(register.hasPrevious || register.hasNext) && <div className="dossier-pages"><button type="button" disabled={!register.hasPrevious} onClick={register.previous}>Previous page</button><button type="button" disabled={!register.hasNext} onClick={register.next}>Next page</button></div>}
        <details className="dossier-more"><summary>Open a consultation by ID</summary><Lookup label="Consultation ID" onSelect={setSelected} /></details>
      </section>
      <article className="dossier-sheet" aria-label="Consultation document">
        {!selected && !register.loading && <div className="dossier-empty"><DepartmentIcon department="consultation" /><p>Select a consultation{doctor ? " or create one for an assigned appointment" : ""}.</p></div>}
        {current.loading && !item && <p role="status">Loading consultation…</p>}
        {current.error && <p role="alert">{current.error}</p>}
        {item && (
          <div key={item.id}>
            {doctor ? (
              <ConsultationEditor item={item} etag={current.response?.etag ?? null} refresh={() => { current.refresh(); setRevision((v) => v + 1); }} />
            ) : (
              <>
                <header className="dossier-header"><div><p className="dossier-eyebrow">Consultation</p><h2>Visit …{item.appointment_id.slice(-4)}</h2></div><span className="owner-state" data-state={item.status}>{item.status === "draft" ? "Draft" : "Finalized"}</span></header>
                <ClinicalSheet value={item.clinical_content} />
                <details className="owner-identifiers"><summary>Details</summary><Facts values={{ "Consultation ID": item.id, "Appointment ID": item.appointment_id, Version: item.version }} /></details>
              </>
            )}
          </div>
        )}
      </article>
      {doctor && (
        <aside className="dossier-side" aria-label="Consultation tools">
          <details className="dossier-more" open={!selected}><summary>New consultation</summary>
            <CommandForm<Consultation>
              title="Create consultation" reviewLabel="Review consultation" confirmLabel="Create consultation" successMessage="Consultation created."
              path="/api/v1/records/consultations"
              fields={[idField("appointment_id", "Assigned appointment ID"), ...clinicalFields()]}
              build={(values) => ({ appointment_id: id(values.appointment_id.trim()), clinical_content: content(values) })}
              onSuccess={(created) => {
                setSelected(created.id);
                setRevision((v) => v + 1);
              }}
            />
          </details>
          <details className="dossier-more assigned-appointments"><summary>Assigned appointments</summary><Appointments doctor /></details>
        </aside>
      )}
    </div>
  );
}
type Visit = { consultationId: string; versions: RecordSummary[]; first: RecordSummary; latest: RecordSummary };
function groupVisits(items: RecordSummary[]): Visit[] {
  const byConsultation = new Map<string, RecordSummary[]>();
  items.forEach((item) => byConsultation.set(item.consultation_id, [...(byConsultation.get(item.consultation_id) ?? []), item]));
  return [...byConsultation.entries()]
    .map(([consultationId, versions]) => {
      const sorted = [...versions].sort((a, b) => a.revision - b.revision);
      return { consultationId, versions: sorted, first: sorted[0], latest: sorted[sorted.length - 1] };
    })
    .sort((a, b) => b.first.created_at.localeCompare(a.first.created_at));
}
function VisitPrescriptions({ patientId, consultationId }: { patientId: string; consultationId: string }) {
  const prescriptions = useCursorPage<Prescription>(query("/api/v1/records/prescriptions", { patient_id: patientId, consultation_id: consultationId }));
  return (
    <section className="dossier-prescriptions" aria-labelledby={`visit-rx-${consultationId}`}>
      <h3 id={`visit-rx-${consultationId}`}>Prescribed medicines</h3>
      {prescriptions.loading && <p role="status">Loading prescriptions from this visit…</p>}
      {prescriptions.error && <p role="alert">{prescriptions.error}</p>}
      {prescriptions.loaded && !prescriptions.loading && prescriptions.items.length === 0 && <p>No prescriptions were issued at this visit.</p>}
      {prescriptions.items.map((prescription) => (
        <div className="dossier-rx" key={prescription.id} data-state={prescription.state} tabIndex={0} role="region" aria-label={`${prescription.state === "revoked" ? "Revoked" : "Issued"} prescription …${prescription.id.slice(-4)}`}>
          <p className="dossier-rx__status"><span className="owner-state" data-state={prescription.state}>{prescription.state === "revoked" ? "Revoked" : "Issued"}</span>{prescription.state === "revoked" ? "Revoked prescription. These instructions are retained as history and are not valid for new fulfilment." : `Prescription …${prescription.id.slice(-4)}`}</p>
          <table>
            <caption className="sr-only">Medicines on prescription …{prescription.id.slice(-4)}</caption>
            <thead><tr><th scope="col">Medicine</th><th scope="col">Quantity</th><th scope="col">Dosage</th><th scope="col">Instructions</th></tr></thead>
            <tbody>{prescription.items.map((line) => <tr key={line.id}><th scope="row"><MedicineName medicineId={line.medicine_id} /></th><td>{line.quantity}</td><td>{line.dosage}</td><td>{line.instructions}</td></tr>)}</tbody>
          </table>
        </div>
      ))}
    </section>
  );
}
function History({
  patientId,
  doctor,
  patientName,
  extra,
}: {
  patientId: string;
  doctor: boolean;
  patientName?: string;
  extra?: ReactNode;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const history = useCursorPage<RecordSummary>(`/api/v1/records/patients/${patientId}`, revision);
  const visits = groupVisits(history.items);
  const firstLatest = visits[0]?.latest.id;
  useEffect(() => {
    if (!selected && firstLatest) setSelected(firstLatest);
  }, [selected, firstLatest]);
  const record = useResource<MedicalRecord>(selected ? `/api/v1/records/${selected}` : null, revision);
  const item = record.response?.data;
  const visit = visits.find((entry) => entry.versions.some((version) => version.id === selected));
  const consultation = useResource<Consultation>(item ? `/api/v1/records/consultations/${item.consultation_id}` : null);
  const doctorId = consultation.response?.data.doctor_id;
  const clinician = useResource<Doctor>(doctorId ? `/api/v1/doctors/${doctorId}` : null);
  const paged = history.hasNext || history.hasPrevious;
  const isLatest = !!visit && visit.latest.id === selected;
  return (
    <>
      <section className="dossier-band" aria-label="Patient">
        <DepartmentIcon department="reception" />
        <div className="dossier-band__name"><strong>{patientName ?? "Patient"}</strong><small>Patient ID …{patientId.slice(-4)}</small></div>
        <dl>
          <div><dt>Last visit</dt><dd>{visits[0] ? longDate(visits[0].first.created_at) : history.loading ? "Loading…" : "None recorded"}</dd></div>
          <div><dt>Visits</dt><dd>{visits.length}{paged ? " in this list" : ""}</dd></div>
        </dl>
      </section>
      <div className={`dossier-room__body${doctor ? " dossier-room__body--doctor" : ""}`}>
        <section className="dossier-timeline" aria-labelledby={`timeline-${patientId}`}>
          <div className="dossier-panel-heading"><h2 id={`timeline-${patientId}`}>Visit timeline</h2><button type="button" disabled={history.loading} onClick={history.refresh}>Refresh</button></div>
          {history.loading && <p role="status">Loading medical history…</p>}
          {history.error && <p role="alert">{history.error}</p>}
          {history.loaded && !history.loading && visits.length === 0 && <p>No medical records found.</p>}
          <ol className="visit-list">
            {visits.map((entry) => (
              <li key={entry.consultationId}>
                <button type="button" className="visit-entry" aria-pressed={entry.versions.some((version) => version.id === selected)} aria-label={`View record ${entry.latest.id}`} onClick={() => setSelected(entry.latest.id)}>
                  <time dateTime={entry.first.created_at}>{shortDateTime(entry.first.created_at)}</time>
                  <strong>Visit record</strong>
                  <small>{entry.versions.length > 1 ? `Amended · revision ${entry.latest.revision}` : "Original record"}</small>
                </button>
              </li>
            ))}
          </ol>
          {paged && <div className="dossier-pages"><button type="button" disabled={!history.hasPrevious} onClick={history.previous}>Previous page</button><button type="button" disabled={!history.hasNext} onClick={history.next}>Next page</button></div>}
          <details className="dossier-more"><summary>Open a record by ID</summary><Lookup label="Medical record ID" onSelect={setSelected} /></details>
        </section>
        <article className="dossier-sheet" aria-labelledby="dossier-title">
          {!selected && !history.loading && <div className="dossier-empty"><DepartmentIcon department="records" /><p>Choose a visit to read its summary, assessment and plan.</p></div>}
          {record.loading && !item && <p role="status">Loading clinical document…</p>}
          {record.error && <p role="alert">{record.error}</p>}
          {item && (
            <div key={item.id}>
              <header className="dossier-header" data-check="records-dossier-header">
                <div>
                  <p className="dossier-eyebrow">Visit record</p>
                  <h2 id="dossier-title">{visit ? longDate(visit.first.created_at) : "Clinical document"}</h2>
                  <p>{clinician.response ? `${clinician.response.data.display_name}${clinician.response.data.specialties[0] ? ` · ${clinician.response.data.specialties[0].name}` : ""}` : "Clinician not returned"}</p>
                </div>
                <span className="owner-state" data-state={isLatest ? "current" : "earlier"}>{!isLatest ? "Earlier version" : item.revision > 1 ? "Amended" : "Current"}</span>
                <button type="button" disabled={record.loading} onClick={record.refresh}>Refresh</button>
              </header>
              {!isLatest && visit && <p className="dossier-notice">You are reading an earlier version of this record. <button type="button" onClick={() => setSelected(visit.latest.id)}>Open the current version</button></p>}
              <ClinicalSheet value={item.content} />
              {!doctor && <VisitPrescriptions key={item.consultation_id} patientId={patientId} consultationId={item.consultation_id} />}
              {doctor && (
                <details className="dossier-more"><summary>Amend this record</summary>
                  <CommandForm<MedicalRecord>
                    title="Amend medical record" reviewLabel="Review amendment" confirmLabel="Save amendment" successMessage="Record amended."
                    path={`/api/v1/records/${item.id}/amendments`}
                    conditional
                    etag={record.response?.etag ?? null}
                    fields={[...clinicalFields(item.content), reasonField]}
                    build={(values) => ({
                      content: content(values),
                      reason: values.reason.trim() || (() => { throw new Error("Reason is required."); })(),
                    })}
                    onSuccess={(amended) => {
                      setSelected(amended.id);
                      setRevision((v) => v + 1);
                    }}
                    notice="Historical amendments require an active clinical hold or an unexpired patient records grant. Original text is preserved."
                  />
                </details>
              )}
            </div>
          )}
        </article>
        <aside className="dossier-side" aria-label="Record history and related care">
          <section aria-labelledby="record-versions-title">
            <h2 id="record-versions-title">Record history</h2>
            {visit ? (
              <ol className="record-versions">
                {[...visit.versions].reverse().map((version) => (
                  <li key={version.id}>
                    <button type="button" aria-pressed={version.id === selected} onClick={() => setSelected(version.id)}>
                      <strong>{version.revision === 1 ? "Original record" : `Amendment · revision ${version.revision}`}{version.id === visit.latest.id ? " (current)" : ""}</strong>
                      <time dateTime={version.created_at}>{shortDateTime(version.created_at)}</time>
                    </button>
                  </li>
                ))}
              </ol>
            ) : <p>Choose a visit to see its versions.</p>}
          </section>
          {!doctor && (
            <nav aria-labelledby="linked-care-title" className="dossier-links">
              <h2 id="linked-care-title">Linked prescriptions &amp; journey</h2>
              <Link to="/patient/prescriptions">All prescriptions →</Link>
              <Link to="/patient/pharmacy">Pharmacy reservations →</Link>
              <Link to="/patient/journey">Care journey →</Link>
            </nav>
          )}
          {extra}
          {item && <details className="owner-identifiers"><summary>Details</summary><Facts values={{ "Record ID": item.id, "Consultation ID": item.consultation_id, Revision: item.revision, Version: item.version, Supersedes: item.supersedes_id ?? "None (original)" }} /></details>}
        </aside>
      </div>
    </>
  );
}
function Grants({ patientId }: { patientId: string }) {
  const [grant, setGrant] = useState<Grant | null>(null);
  const [grantEtag, setGrantEtag] = useState<string | null>(null);
  return (
    <Panel title="Historical access grants">
      <CommandForm<Grant>
        title="Grant historical access" reviewLabel="Review access grant" confirmLabel="Grant access" successMessage="Access granted."
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
            title="Revoke access grant" reviewLabel="Review revocation" confirmLabel="Revoke access" successMessage="Access revoked."
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
export function RecordsPage({ doctor = false, title, subtitle }: { doctor?: boolean; title?: string; subtitle?: string }) {
  const [patientId, setPatientId] = useState<string | null>(null);
  return (
    <div className="dossier-room dossier-room--records">
      {title && <DepartmentSign department="records" title={title} subtitle={subtitle ?? ""} />}
      {doctor ? (
        <>
          <Lookup label="Patient ID for authorized history" onSelect={setPatientId} />
          {patientId && <History key={patientId} patientId={patientId} doctor />}
        </>
      ) : (
        <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>
          {(profile) => (
            <History
              patientId={profile.id}
              doctor={false}
              patientName={profile.display_name.startsWith("Synthetic") ? "Your clinical dossier" : profile.display_name}
              extra={<details className="dossier-more record-grants"><summary>Record access permissions</summary><Grants patientId={profile.id} /></details>}
            />
          )}
        </Resource>
      )}
      {!doctor && <details className="dossier-more record-consultations"><summary>Consultation register</summary><Consultations doctor={false} /></details>}
    </div>
  );
}
export function PrescriptionDetail({
  prescription,
  compact = false,
}: {
  prescription: Prescription;
  compact?: boolean;
}) {
  if (compact) return <div className="pharmacy-prescription-document"><h3>Prescription …{prescription.id.slice(-4)}</h3><p>Records · {prescription.state} · Revision {prescription.revision}</p>{prescription.state === "revoked" && <p className="prescription-revoked-note">Revoked prescription. Instructions are retained as history.</p>}{prescription.items.map(item=><article className="prescribed-document-line" key={item.id}><Resource<Medicine> path={`/api/v1/pharmacy/medicines/${item.medicine_id}`} showReload={false}>{medicine=><strong>{medicine.name.startsWith("Synthetic")?`Catalog item …${medicine.id.slice(-4)}`:medicine.name}</strong>}</Resource><Facts values={{Quantity:item.quantity,Dosage:item.dosage,Instructions:item.instructions}}/></article>)}<details className="owner-identifiers"><summary>Records references</summary><Facts values={{"Prescription ID":prescription.id,"Consultation ID":prescription.consultation_id,"Patient ID":prescription.patient_id}}/></details></div>;
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
            <PrescriptionDetail prescription={prescription} compact={pharmacist} />
            {onSelect && prescription.state === "issued" && (
              <button onClick={() => onSelect(prescription)}>
                Request medicines from prescription {prescription.id}
              </button>
            )}
            {doctor && prescription.state === "issued" && (
              <CommandForm
                title="Revoke prescription" reviewLabel="Review revocation" confirmLabel="Revoke prescription" successMessage="Prescription revoked."
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
