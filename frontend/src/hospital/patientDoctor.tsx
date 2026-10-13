import { AppointmentDoctorRail } from "../design/AppointmentDoctorRail";
import { useLocalDemo } from "../design/localDemo";
import { ReceptionVisit } from "../design/ReceptionVisit";
import { ReferenceConsultation } from "../design/ReferenceConsultation";
import { m } from "motion/react";
import { ReceptionScene } from "../design/ReceptionScene";
import { useSearchParams } from "react-router-dom";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { useEffect, useState } from "react";
import { DoctorAutocomplete, AppointmentShortLinkPanel } from "../phase4";
import { useAuth, roles } from "../auth/authContext";
import type {
  Appointment,
  Availability,
  Decision,
  Doctor,
  DoctorSelf,
  PatientProfile,
  Proposal,
  UserView,
} from "./models";
import {
  buildFields,
  Collection,
  CommandForm,
  date,
  Facts,
  id,
  idField,
  ids,
  Inputs,
  integer,
  Lookup,
  Panel,
  query,
  reasonField,
  Resource,
  Selected,
  utc,
  type Field,
  type Values,
} from "./ui";

const profileFields = (profile: PatientProfile): Field[] => [
  {
    name: "display_name",
    label: "Display name",
    required: true,
    max: 200,
    initial: profile.display_name,
  },
  {
    name: "date_of_birth",
    label: "Date of birth",
    kind: "date",
    nullable: true,
    initial: profile.date_of_birth,
  },
  {
    name: "synthetic_contact",
    label: "Synthetic contact",
    max: 256,
    nullable: true,
    initial: profile.synthetic_contact,
  },
];
export function ProfileEditor({
  profile,
  etag,
  path,
  refresh,
}: {
  profile: PatientProfile;
  etag: string | null;
  path: string;
  refresh: () => void;
}) {
  const fields = profileFields(profile);
  return (
    <>
      <Facts
        values={{
          "Patient ID": profile.id,
          "User ID": profile.user_id,
          Name: profile.display_name,
          "Date of birth": profile.date_of_birth,
          "Synthetic contact": profile.synthetic_contact,
        }}
      />
      <CommandForm
        title="Save profile"
        path={path}
        method="PATCH"
        conditional
        etag={etag}
        fields={fields}
        build={(values) => {
          const body = buildFields(fields, values);
          if (
            values.date_of_birth &&
            date(values.date_of_birth) > new Date().toISOString().slice(0, 10)
          )
            throw new Error("Date of birth cannot be in the future.");
          const changed = Object.fromEntries(
            Object.entries(body).filter(
              ([key, value]) =>
                value !== (profile[key as keyof PatientProfile] ?? null),
            ),
          );
          if (!Object.keys(changed).length)
            throw new Error("Change at least one profile field before saving.");
          return changed;
        }}
        onSuccess={refresh}
      />
    </>
  );
}
export function PatientDashboard() {
  return <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>{(profile,etag,refresh)=><>
    <ReceptionScene name={profile.display_name}><ReceptionVisit patientId={profile.id}/></ReceptionScene>
    <details className="profile-desk"><summary>Your profile</summary><button type="button" onClick={refresh}>Refresh profile</button><ProfileEditor key={profile.version} profile={profile} etag={etag} path="/api/v1/patients/me" refresh={refresh}/></details>
  </>}</Resource>;
}
export function Demographics({ admin = false }: { admin?: boolean }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  return (
    <div className="patient-register">
      <Panel title="Patient demographics">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (
              search.trim() &&
              (search.trim().length < 2 || search.trim().length > 100)
            ) {
              setError("Search must contain 2 to 100 characters.");
              return;
            }
            setFilter(search.trim());
            setSelected(null);
            setError("");
          }}
        >
          <label>
            Patient search
            <input value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
          <button>Search patients</button>
          {error && <p role="alert">{error}</p>}
        </form>
      </Panel>
      <Collection<PatientProfile>
        title="Patients"
        revision={revision}
        path={query("/api/v1/patients", { q: filter })}
        renderItem={(item) => (
          <>
            <strong>{item.display_name}</strong>
            <p>Patient ID: {item.id}</p>
            <button onClick={() => setSelected(item.id)}>
              View patient {item.id}
            </button>
          </>
        )}
      />
      <Selected<PatientProfile>
        path={selected ? `/api/v1/patients/${selected}` : null}
      >
        {(profile, etag, refresh) => (
          <ProfileEditor
            profile={profile}
            etag={etag}
            path={`/api/v1/patients/${profile.id}`}
            refresh={() => {
              refresh();
              setRevision((v) => v + 1);
            }}
          />
        )}
      </Selected>
      {admin && (
        <p>
          Role and account management is available in Staff and roles.
          Demographic edits do not change permissions.
        </p>
      )}
    </div>
  );
}
export function StaffManagement() {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [filters, setFilters] = useState<Values>({});
  const [draft, setDraft] = useState<Values>({});
  const [error, setError] = useState("");
  return (
    <div className="account-register">
      <Panel title="Filter accounts">
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
            setError("");
            setFilters(draft);
            setSelected(null);
          }}
        >
          <Inputs
            fields={[
              { name: "q", label: "Account search", max: 100 },
              {
                name: "role",
                label: "Role filter",
                kind: "select",
                options: [...roles],
              },
              {
                name: "state",
                label: "Account state filter",
                kind: "select",
                options: ["active", "disabled"],
              },
            ]}
            values={draft}
            change={(name, value) => setDraft({ ...draft, [name]: value })}
          />
          <button>Filter accounts</button>
          {error && <p role="alert">{error}</p>}
        </form>
      </Panel>
      <Collection<UserView>
        title="Accounts"
        path={query("/api/v1/patients/users", filters)}
        revision={revision}
        renderItem={(item) => (
          <>
            <strong>{item.display_name}</strong>
            <p>
              {item.email} • {item.state} • {item.roles.join(", ")}
            </p>
            <button onClick={() => setSelected(item.id)}>
              Manage account {item.id}
            </button>
          </>
        )}
      />
      <Selected<UserView>
        path={selected ? `/api/v1/patients/users/${selected}` : null}
      >
        {(user, etag, refresh) => {
          const changed = () => {
            refresh();
            setRevision((v) => v + 1);
          };
          return (
            <>
              <Facts
                values={{
                  "User ID": user.id,
                  Name: user.display_name,
                  State: user.state,
                  Roles: user.roles.join(", "),
                }}
              />
              <CommandForm
                title="Replace roles"
                path={`/api/v1/patients/users/${user.id}/roles`}
                method="PATCH"
                conditional
                etag={etag}
                fields={[
                  {
                    name: "roles",
                    label: "Roles (comma separated)",
                    required: true,
                    initial: user.roles.join(", "),
                  },
                ]}
                build={(values) => {
                  const list = values.roles.split(",").map((v) => v.trim());
                  if (
                    !list.length ||
                    list.length > 8 ||
                    new Set(list).size !== list.length ||
                    list.some(
                      (v) => !roles.includes(v as (typeof roles)[number]),
                    )
                  )
                    throw new Error(
                      `Choose distinct roles from: ${roles.join(", ")}.`,
                    );
                  return { roles: list };
                }}
                onSuccess={changed}
                notice="Role changes revoke sessions. The service protects your administrator role and the last active administrator."
              />
              <CommandForm
                title="Change account state"
                path={`/api/v1/patients/users/${user.id}/account-state`}
                method="PATCH"
                conditional
                etag={etag}
                fields={[
                  {
                    name: "state",
                    label: "Account state",
                    kind: "select",
                    required: true,
                    options: ["active", "disabled"],
                    initial: user.state,
                  },
                  reasonField,
                ]}
                onSuccess={changed}
              />
            </>
          );
        }}
      </Selected>
    </div>
  );
}
export function AvailabilityPicker({
  doctorId,
  onSlot,
  autoLoad = false,
  onClear,
}: {
  doctorId: string;
  autoLoad?: boolean;
  onClear?: () => void;
  onSlot?: (slotId: string, revision: number, startsAt: string, endsAt: string) => void;
}) {
  const [values, setValues] = useState<Values>(()=>{const start=new Date().toISOString().slice(0,10)+"T00:00:00Z";return {from:start,to:new Date(Date.parse(start)+86400000).toISOString()};});
  const [day, setDay] = useState(new Date().toISOString().slice(0,10));
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const days = Array.from({length:7},(_,i)=>new Date(Date.parse(`${day}T00:00:00Z`)+i*86400000));
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setSelectedSlot(null);
    const span = Date.parse(values.to ?? "") - Date.parse(values.from ?? "");
    const valid = values.from?.endsWith("Z") && values.to?.endsWith("Z") && span > 0 && span <= 31 * 86400000;
    setPath(autoLoad && valid ? query("/api/v1/appointments/availability", {doctor_id:doctorId,from:values.from,to:values.to}) : null);
  }, [doctorId, values.from, values.to, autoLoad]);
  return (
    <Panel title="Accepted availability">
      <p className="availability-note">Choose a date, then load the accepted schedule. Times are in UTC; the service confirms availability when booking.</p>
      <label className="availability-date">Choose date (UTC)<input type="date" value={values.from?.slice(0,10)??day} onChange={e=>{if(e.target.value){setDay(e.target.value);setValues({from:`${e.target.value}T00:00:00Z`,to:new Date(Date.parse(`${e.target.value}T00:00:00Z`)+86400000).toISOString()});setSelectedSlot(null);onClear?.();}}}/></label>
      <div className="calendar-strip" aria-label="Available date selection">{days.map(d=><button type="button" key={d.toISOString()} aria-pressed={values.from?.slice(0,10)===d.toISOString().slice(0,10)} onClick={()=>{setValues({from:d.toISOString(),to:new Date(d.getTime()+86400000).toISOString()});setSelectedSlot(null);onClear?.();}}><small>{d.toLocaleDateString('en',{weekday:'short',timeZone:'UTC'})}</small><strong>{d.getUTCDate()}</strong><small>{d.toLocaleDateString('en',{month:'short',timeZone:'UTC'})}</small></button>)}</div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          try {
            const from = utc(values.from ?? "");
            const to = utc(values.to ?? "");
            const span = Date.parse(to) - Date.parse(from);
            if (span <= 0 || span > 31 * 86400000)
              throw new Error("Choose a positive interval of at most 31 days.");
            setPath(
              query("/api/v1/appointments/availability", {
                doctor_id: id(doctorId),
                from,
                to,
              }),
            );
            setError("");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Invalid interval.");
          }
        }}
      >
        <details className="availability-range"><summary>Custom UTC range</summary><Inputs
          fields={[
            { name: "from", label: "From (UTC)" },
            { name: "to", label: "To (UTC)" },
          ]}
          values={values}
          change={(name, value) => setValues({ ...values, [name]: value })}
        /></details>
        <button>Load availability</button>
        {error && <p role="alert">{error}</p>}
      </form>
      <Resource<Availability> path={path}>
        {(data) => (
          <>
            <p>
              Accepted revision: {data.accepted_revision}. Observed:{" "}
              {data.observed_at}
            </p>
            {!data.slots.length && <p>No available slots in this interval.</p>}
            <div className="available-slots">{data.slots.map((slot) => (
              <div className="available-slot" key={slot.id}>
                <time dateTime={slot.starts_at}>{new Date(slot.starts_at).toLocaleDateString('en',{day:'numeric',month:'short',timeZone:'UTC'})}</time>
                {onSlot && (
                  <button
                    type="button"
                    aria-label={`Select slot ${slot.id}`}
                    aria-pressed={selectedSlot===slot.id}
                    onClick={() => {setSelectedSlot(slot.id);onSlot(slot.id, slot.revision, slot.starts_at, slot.ends_at);}}
                  >
                    {new Date(slot.starts_at).toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})}
                  </button>
                )}
                {!onSlot && <p>{new Date(slot.starts_at).toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})} – {new Date(slot.ends_at).toLocaleTimeString('en',{hour:'2-digit',minute:'2-digit',timeZone:'UTC'})}</p>}
              </div>
            ))}</div>
          </>
        )}
      </Resource>
    </Panel>
  );
}
export function Booking({
  patientId,
  doctorId,
  doctorName,
  patientName,
  onSuccess,
  onLockChange,
}: {
  patientId?: string;
  doctorId?: string;
  doctorName?: string;
  patientName?: string;
  onSuccess?: () => void;
  onLockChange?: (locked:boolean)=>void;
}) {
  const {state,api}=useAuth();
  const [doctor, setDoctor] = useState(doctorId ?? "");
  const [slot, setSlot] = useState<{ id: string; revision: number; startsAt: string; endsAt: string } | null>(
    null,
  );
  const [doctorLabel,setDoctorLabel] = useState(doctorName??"");
  const [locked,setLocked] = useState(false);
  const [confirmed,setConfirmed] = useState<Appointment|null>(null);
  return (
    <div className="booking-composition"><section className="booking-doctor"><fieldset disabled={locked}><h3><span className="step-number">1</span>Select Doctor</h3>
      <details className="advanced-doctor-search"><summary>Search the complete directory</summary><DoctorAutocomplete api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} onSelect={item => {setDoctor(item.id);setDoctorLabel(item.label);setSlot(null);}} /></details>
      {!doctorId && <AppointmentDoctorRail selected={doctor} onSelect={item=>{if(!locked){setDoctor(item.id);setDoctorLabel(item.display_name);setSlot(null);}}}/>}
      <details className="manual-doctor-lookup"><summary>Use a doctor ID</summary><Lookup
        label="Doctor ID for availability"
        onSelect={(value) => {
          setDoctor(value);
          setDoctorLabel("");
          setSlot(null);
        }}
      /></details>
      </fieldset></section><section className="booking-schedule"><fieldset disabled={locked}><h3><span className="step-number">2</span>Choose Date & Time</h3>
      {!doctor && <div className="resource-empty"><DepartmentIcon department="appointments"/><strong>Choose a doctor first</strong><p>Their accepted dates and slots will appear here.</p></div>}
      {doctor && (
        <AvailabilityPicker
          key={doctor}
          doctorId={doctor}
          autoLoad={!doctorId}
          onClear={()=>setSlot(null)}
          onSlot={(id, revision, startsAt, endsAt) => setSlot({ id, revision, startsAt, endsAt })}
        />
      )}
      </fieldset></section><aside className="booking-receipt"><h3>Appointment Summary</h3><div className="receipt-rule"/><Facts values={{"Doctor":doctorLabel||doctor||"Select doctor","Patient":patientName||patientId||"Enter patient below","Starts (UTC)":slot?.startsAt??"Choose a time","Ends (UTC)":slot?.endsAt??"—"}}/>
      {slot && (
        <CommandForm<Appointment>
          key={slot.id}
          onLockChange={value=>{setLocked(value);onLockChange?.(value);}}
          title="Book appointment"
          path="/api/v1/appointments"
          fields={patientId ? [] : [idField("patient_id", "Patient ID")]}
          build={(values) => ({
            patient_id: patientId ?? id(values.patient_id.trim()),
            slot_id: slot.id,
            expected_schedule_revision: slot.revision,
          })}
          onSuccess={item=>{setConfirmed(item);onSuccess?.();}}
          notice={`Selected slot ${slot.id}, accepted revision ${slot.revision}.`}
        />
      )}
      {confirmed && <m.div initial={{opacity:.5,y:6}} animate={{opacity:1,y:0}} transition={{duration:.3}} className="printed-receipt" role="status"><DepartmentIcon department="appointments"/><strong>APPOINTMENT {confirmed.state.toUpperCase()}</strong><Facts values={{"Appointment ID":confirmed.id,"Starts (UTC)":confirmed.starts_at,"Ends (UTC)":confirmed.ends_at,"Doctor ID":confirmed.doctor_id}}/><p>Confirmed by Appointment Service.</p></m.div>}
      </aside></div>
  );
}
export function DoctorDirectory({admin=false}:{admin?:boolean}) {
  const {state}=useAuth();const patient=state.status==='authenticated'&&state.roleHints.includes('patient');
  const [revision,setRevision]=useState(0);
  return <ReferenceConsultation admin={admin} revision={revision}
    renderManagement={(doctor,etag,refresh)=><DoctorManagement doctor={doctor} etag={etag} refresh={refresh} admin/>}
    booking={(doctor,onLockChange)=>patient?<Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>{profile=><Booking patientId={profile.id} patientName={profile.display_name} doctorId={doctor.id} doctorName={doctor.display_name} onLockChange={onLockChange}/>}</Resource>:<AvailabilityPicker doctorId={doctor.id}/>}
    createEntries={admin?<Panel title="Create directory entries">
          <CommandForm
            title="Create specialty"
            path="/api/v1/doctors/specialties"
            fields={[
              {
                name: "slug",
                label: "Specialty slug",
                required: true,
                max: 128,
              },
              {
                name: "name",
                label: "Specialty name",
                required: true,
                max: 200,
              },
            ]}
            build={(values) => {
              const body = buildFields(
                [
                  { name: "slug", label: "Slug", required: true, max: 128 },
                  { name: "name", label: "Name", required: true, max: 200 },
                ],
                values,
              );
              if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(values.slug))
                throw new Error(
                  "Use lowercase letters, digits and single hyphens for the slug.",
                );
              return body;
            }}
            onSuccess={() => setRevision((v) => v + 1)}
          />
          <CommandForm
            title="Create doctor"
            path="/api/v1/doctors"
            fields={[
              idField("staff_user_id", "Doctor-role user ID"),
              {
                name: "display_name",
                label: "Doctor display name",
                required: true,
                max: 200,
              },
              {
                name: "specialty_ids",
                label: "Specialty IDs (comma separated)",
                required: true,
              },
            ]}
            build={(values) => ({
              staff_user_id: id(values.staff_user_id.trim()),
              display_name:
                values.display_name.trim() ||
                (() => {
                  throw new Error("Display name is required.");
                })(),
              specialty_ids: ids(values.specialty_ids, 1, 20),
            })}
            onSuccess={() => setRevision((v) => v + 1)}
          />
        </Panel>:null}/>
}
export function Appointments({
  reception = false,
  doctor = false,
}: {
  reception?: boolean;
  doctor?: boolean;
}) {
  const {state,api}=useAuth();
  const demo=useLocalDemo();
  const [params,setParams]=useSearchParams();
  const view=params.get('view')==='upcoming'?'manage':params.get('view')==='walk-in'?'walk-in':'book';
  const setView=(value:string)=>setParams(value==='book'?{}:{view:value==='manage'?'upcoming':'walk-in'},{replace:true});
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [targetDoctor, setTargetDoctor] = useState("");
  const [targetSlot, setTargetSlot] = useState<{
    id: string;
    revision: number;
  } | null>(null);
  return (
    <div className="appointment-workspace">
      {!doctor && <nav className="department-tabs" aria-label="Appointment views"><button type="button" aria-pressed={view==='book'} onClick={()=>setView('book')}>Book Appointment</button><button type="button" aria-pressed={view==='manage'} onClick={()=>setView('manage')}>My Appointments / Reschedule / Cancel</button>{reception && <button type="button" aria-pressed={view==='walk-in'} onClick={()=>setView('walk-in')}>Walk-in Registration</button>}</nav>}
      {reception && <section className="walkin-workspace" hidden={view!=='walk-in'}><div className="walkin-steps"><p><span className="step-number">1</span>Find existing patient</p><p><span className="step-number">2</span>Choose doctor & accepted slot</p><p><span className="step-number">3</span>Review & confirm booking</p></div><div><h2>Walk-in Registration</h2><p>Find the patient below, then use their Patient ID in the booking form. Walk-in care uses an accepted appointment slot.</p><Demographics/><Booking onSuccess={()=>setRevision(v=>v+1)}/></div><aside className="walkin-guidance"><h3>Before booking</h3><p>Use an existing synthetic patient profile. New patients can create an account through patient registration.</p><p>The service determines slot availability. No separate walk-in queue or estimated waiting time is available.</p></aside></section>}
      <section hidden={view!=='book'} className="appointment-booking">
      {!doctor &&
        (reception ? (
          <Panel title="New booking">
            <Booking onSuccess={() => setRevision((v) => v + 1)} />
          </Panel>
        ) : (
          <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>
            {(profile) => (
              <Panel title="New booking">
                <Booking
                  patientId={profile.id}
                  patientName={profile.display_name}
                  onSuccess={() => setRevision((v) => v + 1)}
                />
              </Panel>
            )}
          </Resource>
        ))}
      </section><div className="appointment-management" hidden={!doctor&&view!=='manage'}>
      <Collection<Appointment>
        title="Appointments"
        path="/api/v1/appointments"
        revision={revision}
        renderItem={(item) => (
          <>
            <div className="appointment-slip-entry"><time>{new Date(item.starts_at).toLocaleString('en',{timeZone:'UTC',dateStyle:'medium',timeStyle:'short'})} UTC</time><strong>{demo?.appointments[item.id]?.label??`Visit …${item.id.slice(-4)}`}</strong><span>{demo?.patients[item.patient_id]?.name??'Authorized patient'}</span><span className="owner-state">{item.state}</span></div>
            <details className="owner-identifiers"><summary>Reference identifiers</summary><Facts values={{"Appointment ID":item.id,"Patient ID":item.patient_id,"Doctor ID":item.doctor_id}}/></details>
            <button
              aria-label={`View appointment ${item.id}`}
              onClick={() => {
                setSelected(item.id);
                if(!doctor)setView('manage');
                setTargetSlot(null);
                setTargetDoctor("");
              }}
            >
              Review appointment →
            </button>
          </>
        )}
      />
      <Selected<Appointment>
        path={selected ? `/api/v1/appointments/${selected}` : null}
      >
        {(item, etag, refresh) => (
          <>
            <Facts
              values={{
                "Appointment ID": item.id,
                State: item.state,
                "Starts (UTC)": item.starts_at,
                "Ends (UTC)": item.ends_at,
              }}
            />
            {!doctor && <AppointmentShortLinkPanel api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} appointmentId={item.id} />}
            {!doctor && item.state === "confirmed" && (
              <>
                <CommandForm
                  title="Cancel appointment"
                  path={`/api/v1/appointments/${item.id}/cancel`}
                  fields={[reasonField]}
                  conditional
                  etag={etag}
                  onSuccess={() => {
                    refresh();
                    setRevision((v) => v + 1);
                  }}
                />
                <Lookup
                  label="Target doctor ID"
                  onSelect={(value) => {
                    setTargetDoctor(value);
                    setTargetSlot(null);
                  }}
                />
                {targetDoctor && (
                  <AvailabilityPicker
                    key={targetDoctor}
                    doctorId={targetDoctor}
                    onSlot={(id, revision) => setTargetSlot({ id, revision })}
                  />
                )}
                {targetSlot && (
                  <CommandForm
                    key={targetSlot.id}
                    title="Reschedule appointment"
                    path={`/api/v1/appointments/${item.id}/reschedule`}
                    conditional
                    etag={etag}
                    build={() => ({
                      target_slot_id: targetSlot.id,
                      expected_schedule_revision: targetSlot.revision,
                    })}
                    notice={`Move appointment ${item.id} to slot ${targetSlot.id}.`}
                    onSuccess={() => {
                      refresh();
                      setRevision((v) => v + 1);
                      setTargetSlot(null);
                    }}
                  />
                )}
              </>
            )}
          </>
        )}
      </Selected>
      {!selected && <aside className="appointment-details-empty"><Panel title="Appointment details"><div className="resource-empty"><DepartmentIcon department="appointments"/><strong>Your appointment slip</strong><p>Open an appointment to review its schedule, create a secure short link, or reschedule/cancel where permitted.</p></div></Panel></aside>}
      </div></div>
  );
}
function ScheduleForm({
  doctor,
  etag,
  refresh,
}: {
  doctor: Doctor;
  etag: string | null;
  refresh: () => void;
}) {
  const [intervals, setIntervals] = useState<
    { starts_at: string; ends_at: string }[]
  >([]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const fields: Field[] = [
    {
      name: "timezone",
      label: "IANA timezone",
      required: true,
      max: 128,
      initial: "Asia/Kolkata",
    },
    {
      name: "slot_minutes",
      label: "Slot minutes",
      kind: "number",
      required: true,
      min: 5,
      max: 120,
    },
    {
      name: "expected_revision",
      label: "Latest proposal revision (0 initially)",
      kind: "number",
      required: true,
      min: 0,
    },
  ];
  return (
    <Panel title="Schedule proposals">
      <p>
        Submit a proposal, request an Appointment decision, then reconcile
        Doctor. Empty intervals propose closure. A rejected decision preserves
        accepted slots. Enter all interval times in UTC.
      </p>

      <CommandForm<Proposal>
        title="Submit schedule proposal"
        path={`/api/v1/doctors/${doctor.id}/schedules`}
        fields={fields}
        conditional
        etag={etag}
        build={(values) => {
          const body = buildFields(fields, values);
          try {
            new Intl.DateTimeFormat("en", { timeZone: values.timezone.trim() });
          } catch {
            throw new Error("Enter a valid IANA timezone.");
          }
          const slotMinutes = integer(values.slot_minutes, 5, 120);
          let previousEnd = 0;
          let count = 0;
          const normalized = intervals.map((interval) => {
            const start = Date.parse(utc(interval.starts_at));
            const end = Date.parse(utc(interval.ends_at));
            if (
              start <= Date.now() ||
              end <= start ||
              start < previousEnd ||
              end > Date.now() + 366 * 86400000 ||
              (end - start) % (slotMinutes * 60000) !== 0
            )
              throw new Error(
                "Intervals must be future, ordered, nonoverlapping and aligned to slot minutes within the next 366 days.",
              );
            previousEnd = end;
            count += (end - start) / (slotMinutes * 60000);
            return interval;
          });
          if (
            count > 1000 ||
            (intervals.length &&
              Date.parse(intervals.at(-1)!.ends_at) -
                Date.parse(intervals[0].starts_at) >
                31 * 86400000)
          )
            throw new Error("Limit schedules to 31 days and 1000 slots.");
          return { ...body, intervals: normalized };
        }}
        onSuccess={(item) => {
          setProposal(item);
          refresh();
        }}
      >
        <div>
          {intervals.map((interval, index) => (
            <fieldset key={index}>
              <legend>Interval {index + 1}</legend>
              <label>
                Start UTC
                <input
                  value={interval.starts_at}
                  onChange={(e) =>
                    setIntervals(
                      intervals.map((v, i) =>
                        i === index ? { ...v, starts_at: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <label>
                End UTC
                <input
                  value={interval.ends_at}
                  onChange={(e) =>
                    setIntervals(
                      intervals.map((v, i) =>
                        i === index ? { ...v, ends_at: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <button
                type="button"
                onClick={() =>
                  setIntervals(intervals.filter((_, i) => i !== index))
                }
              >
                Remove interval {index + 1}
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            disabled={intervals.length >= 64}
            onClick={() =>
              setIntervals([...intervals, { starts_at: "", ends_at: "" }])
            }
          >
            Add interval
          </button>
        </div>
      </CommandForm>
      {proposal && (
        <p role="status">
          Created proposal {proposal.id}, revision {proposal.revision}. Open it
          below to request its decision and reconcile.
        </p>
      )}
    </Panel>
  );
}
export function DoctorManagement({
  doctor,
  etag,
  refresh,
  admin = false,
}: {
  doctor: Doctor;
  etag: string | null;
  refresh: () => void;
  admin?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [revision, setRevision] = useState(0);
  const fields: Field[] = [
    {
      name: "display_name",
      label: "Doctor display name",
      required: true,
      max: 200,
      initial: doctor.display_name,
    },
    ...(admin
      ? [
          {
            name: "specialty_ids",
            label: "Specialty IDs (comma separated)",
            required: true,
            initial: doctor.specialties.map((s) => s.id).join(","),
          },
          {
            name: "active",
            label: "Doctor active",
            kind: "select" as const,
            options: ["true", "false"],
            required: true,
            initial: String(doctor.active),
          },
        ]
      : []),
  ];
  return (
    <>
      <CommandForm
        title="Save doctor profile"
        path={`/api/v1/doctors/${doctor.id}`}
        method="PATCH"
        fields={fields}
        conditional
        etag={etag}
        build={(values) => {
          const body = buildFields(fields, values);
          return {
            ...body,
            ...(admin
              ? {
                  specialty_ids: ids(values.specialty_ids, 1, 20),
                  active: values.active === "true",
                }
              : {}),
          };
        }}
        onSuccess={refresh}
        notice={
          admin
            ? "Before deactivation, submit an empty closure, accept it and reconcile it. Confirmed bookings must be resolved before closure."
            : undefined
        }
      />
      <AvailabilityPicker doctorId={doctor.id} />
      {doctor.active && (
        <ScheduleForm
          doctor={doctor}
          etag={etag}
          refresh={() => {
            refresh();
            setRevision((v) => v + 1);
          }}
        />
      )}
      <Collection<Proposal>
        title="Schedule proposals"
        path={`/api/v1/doctors/${doctor.id}/schedules`}
        revision={revision}
        renderItem={(proposal) => (
          <>
            <p>
              Proposal {proposal.id} • revision {proposal.revision} •{" "}
              {proposal.status}
            </p>
            <button
              onClick={() => {
                setSelected(proposal.id);
                setDecision(null);
              }}
            >
              Open proposal {proposal.id}
            </button>
          </>
        )}
      />
      <Selected<Proposal>
        path={
          selected ? `/api/v1/doctors/${doctor.id}/schedules/${selected}` : null
        }
      >
        {(proposal, proposalEtag, reload) => (
          <>
            <Facts
              values={{
                "Proposal ID": proposal.id,
                Revision: proposal.revision,
                Status: proposal.status,
                Conflicts: proposal.conflicts.join(", ") || "None",
                Intervals:
                  proposal.intervals
                    .map((i) => `${i.starts_at} to ${i.ends_at}`)
                    .join("; ") || "Closure",
              }}
            />
            <CommandForm<Decision>
              title="Request schedule decision"
              path="/api/v1/appointments/schedule-decisions"
              fields={[
                {
                  name: "expected_accepted_revision",
                  label: "Current accepted revision",
                  kind: "number",
                  min: 0,
                  required: true,
                },
              ]}
              build={(values) => ({
                doctor_id: doctor.id,
                proposal_id: proposal.id,
                expected_accepted_revision: integer(
                  values.expected_accepted_revision,
                ),
              })}
              onSuccess={setDecision}
            />
            {decision && (
              <p role="status">
                Decision {decision.state}:{" "}
                {decision.reason_code ?? "No rejection reason"}. Conflicting
                appointments:{" "}
                {decision.conflicting_appointment_ids.join(", ") || "None"}
              </p>
            )}
            <Resource<Decision>
              path={`/api/v1/appointments/schedule-decisions/${proposal.id}`}
            >
              {(item) => (
                <Facts
                  values={{
                    "Persisted decision": item.state,
                    Reason: item.reason_code,
                    "Conflicting appointment IDs":
                      item.conflicting_appointment_ids.join(", ") || "None",
                  }}
                />
              )}
            </Resource>
            <CommandForm
              title="Reconcile schedule"
              path={`/api/v1/doctors/${doctor.id}/schedules/${proposal.id}/reconcile`}
              conditional
              etag={proposalEtag}
              onSuccess={() => {
                reload();
                refresh();
                setRevision((v) => v + 1);
              }}
            />
          </>
        )}
      </Selected>
    </>
  );
}
export function DoctorDashboard() {
  return (
    <Panel title="Your doctor profile">
      <Resource<DoctorSelf> path="/api/v1/doctors/me">
        {(data, etag, refresh) => (
          <DoctorManagement
            key={data.doctor.id}
            doctor={data.doctor}
            etag={etag}
            refresh={refresh}
          />
        )}
      </Resource>
    </Panel>
  );
}
