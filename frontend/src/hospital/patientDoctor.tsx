import { PageRefresh, AdvancedLookup, ItemDetails } from "../components/PageTools";
import { PageGrid } from "../components/PageGrid";
import { AppointmentDoctorRail } from "../design/AppointmentDoctorRail";
import { DoctorPortrait, useLocalDemo } from "../design/localDemo";
import { ReceptionVisit } from "../design/ReceptionVisit";
import { ReferenceConsultation } from "../design/ReferenceConsultation";
import { m } from "motion/react";
import { Link, useSearchParams } from "react-router-dom";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { DepartmentSign } from "../design/DepartmentSign";
import { useCursorPage } from "./pharmacyRoom";
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
  Page,
  Proposal,
  UserView,
} from "./models";
import {
  formatDateTime,
  buildFields,
  Collection,
  CommandForm,
  date,
  Facts,
  FlashArea,
  formatSlot,
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
  useResource,
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
    label: "Contact number or email",
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
          "Contact number or email": profile.synthetic_contact,
        }}
      />
      <CommandForm
        title="Save profile" reviewLabel="Review profile" confirmLabel="Save profile" successMessage="Profile saved."
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
  return <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>{(profile,_etag,refresh)=><>
    <ReceptionVisit patientId={profile.id} name={profile.display_name}/>
    <PageRefresh type="button" onClick={refresh}>Refresh profile</PageRefresh>
  </>}</Resource>;
}
export function Demographics({ admin = false }: { admin?: boolean }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  return (
    <PageGrid preset={selected ? "main+aside" : "main"} className="patient-register">
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
        columns={[
 {label:"Name",render:item=><strong>{item.display_name}</strong>},
 {label:"Contact",render:item=>item.synthetic_contact||"—"},
 {label:"Actions",render:item=><><button type="button" aria-label={`Open patient ${item.display_name}`} onClick={()=>setSelected(item.id)}>Open</button><ItemDetails>Patient {item.id}</ItemDetails></>},
 ]}
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
    </PageGrid>
  );
}
export function StaffManagement() {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [filters, setFilters] = useState<Values>({});
  const [draft, setDraft] = useState<Values>({});
  const [error, setError] = useState("");
  return (
    <PageGrid preset={selected ? "main+aside" : "main"} className="account-register">
      <Panel title="Filter accounts">
        <form
          className="filter-row"
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
          <button aria-label="Filter accounts">Apply</button>
          {error && <p role="alert">{error}</p>}
        </form>
      </Panel>
      <Collection<UserView>
        title="Accounts"
        path={query("/api/v1/patients/users", filters)}
        revision={revision}
        columns={[
 {label:"Name",render:item=><strong>{item.display_name}</strong>},
 {label:"Email",render:item=>item.email},
 {label:"Roles",render:item=>item.roles.join(", ").replaceAll("_"," ")},
 {label:"Status",render:item=>item.state},
 {label:"Actions",render:item=><><button type="button" aria-label={`Open account ${item.display_name}`} onClick={()=>setSelected(item.id)}>Open</button><ItemDetails>Account {item.id} · Version {item.version}</ItemDetails></>},
 ]}
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
                title="Replace roles" reviewLabel="Review roles" confirmLabel="Save roles" successMessage="Roles saved."
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
                title="Change account state" reviewLabel="Review account state" confirmLabel="Change account state" successMessage="Account state changed."
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
    </PageGrid>
  );
}
const dayMs = 86400000;
const isoDay = (value: Date | number) => new Date(value).toISOString().slice(0, 10);
const utcStart = (day: string) => `${day}T00:00:00Z`;
const nextUtcDay = (day: string) => new Date(Date.parse(utcStart(day)) + dayMs).toISOString();
function clock(value: string) {
  return new Date(value).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
}
function longDay(value: string) {
  return new Date(value).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
const slotGroups = [
  { label: "Morning", test: (hour: number) => hour < 12 },
  { label: "Afternoon", test: (hour: number) => hour >= 12 && hour < 17 },
  { label: "Evening", test: (hour: number) => hour >= 17 },
];
export function AvailabilityPicker({
  doctorId,
  onSlot,
  onClear,
  doctorName,
  day: chosenDay,
  showWeek = true,
  revision = 0,
  bookedAppointments = [],
}: {
  bookedAppointments?: Appointment[];
  revision?: number;
  doctorId: string;
  onClear?: () => void;
  onSlot?: (slotId: string, revision: number, startsAt: string, endsAt: string) => void;
  doctorName?: string;
  day?: string;
  showWeek?: boolean;
}) {
  const today = isoDay(Date.now());
  const [values, setValues] = useState<Values>(() => ({ from: utcStart(chosenDay ?? today), to: nextUtcDay(chosenDay ?? today) }));
  const [weekStart, setWeekStart] = useState(chosenDay ?? today);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const days = Array.from({ length: 7 }, (_, i) => new Date(Date.parse(utcStart(weekStart)) + i * dayMs));
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  const chooseDay = (value: string) => {
    setValues({ from: utcStart(value), to: nextUtcDay(value) });
    setSelectedSlot(null);
    onClear?.();
  };
  useEffect(() => {
    if (chosenDay) {
      setValues({ from: utcStart(chosenDay), to: nextUtcDay(chosenDay) });
      setSelectedSlot(null);
    }
  }, [chosenDay]);
  useEffect(() => setSelectedSlot(null), [revision]);
  useEffect(() => {
    setSelectedSlot(null);
    try {
      const from = utc(values.from ?? "");
      const to = utc(values.to ?? "");
      const span = Date.parse(to) - Date.parse(from);
      if (span <= 0 || span > 31 * dayMs) throw new Error("Choose a positive interval of at most 31 days.");
      if (Date.parse(to) <= Date.now()) throw new Error("That date has passed. Choose today or a later date.");
      setPath(query("/api/v1/appointments/availability", { doctor_id: id(doctorId), from, to }));
      setError("");
    } catch (err) {
      setPath(null);
      setError(err instanceof Error ? err.message : "Invalid interval.");
    }
  }, [doctorId, values.from, values.to]);
  const selectedDay = values.from?.slice(0, 10);
  return (
    <section className="availability-picker" aria-label="Accepted availability">
      <div className="availability-head">
        <h4>Available slots{doctorName ? <> — <span>{doctorName}</span></> : null}</h4>
        {onSlot && (
          <ul className="slot-legend" aria-label="Slot legend">
            <li data-kind="available">Available</li>
            <li data-kind="unavailable">Unavailable</li>
            <li data-kind="selected">Selected</li>
          </ul>
        )}
      </div>
      {showWeek && (
        <div className="week-strip">
          <button type="button" aria-label="Previous week" disabled={weekStart <= today} onClick={() => setWeekStart(isoDay(Math.max(Date.parse(utcStart(today)), Date.parse(utcStart(weekStart)) - 7 * dayMs)))}>‹</button>
          <div className="calendar-strip" aria-label="Available date selection">
            {days.map((d) => (
              <button type="button" key={d.toISOString()} aria-pressed={selectedDay === isoDay(d)} aria-label={d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" })} onClick={() => chooseDay(isoDay(d))}>
                <small>{d.toLocaleDateString("en", { weekday: "short", timeZone: "UTC" })}</small>
                <strong>{d.getUTCDate()}</strong>
                <small>{d.toLocaleDateString("en", { month: "short", timeZone: "UTC" })}</small>
              </button>
            ))}
          </div>
          <button type="button" aria-label="Next week" onClick={() => setWeekStart(isoDay(Date.parse(utcStart(weekStart)) + 7 * dayMs))}>›</button>
        </div>
      )}
      <Resource<Availability> path={path} revision={revision} showReload={false}>
        {(data) => (
          <div className="slot-board">
            {!data.slots.length && <p className="slot-empty">No available slots in this interval.</p>}
            {bookedAppointments.filter(visit => visit.doctor_id === doctorId && Date.parse(visit.starts_at) >= Date.parse(values.from ?? "") && Date.parse(visit.starts_at) < Date.parse(values.to ?? "")).map(visit => (
              <button key={visit.id} type="button" className="available-slot booked-slot" disabled aria-label={`Booked ${clock(visit.starts_at)} UTC`}>{clock(visit.starts_at)} · Booked</button>
            ))}
            {slotGroups.map(({ label, test }) => {
              const slots = data.slots.filter((slot) => test(new Date(slot.starts_at).getUTCHours()));
              if (!slots.length) return null;
              return (
                <div className="slot-group" key={label}>
                  <h5>{label}</h5>
                  <div className="available-slots">
                    {slots.map((slot) =>
                      onSlot ? (
                        <button
                          key={slot.id}
                          type="button"
                          className="available-slot"
                          data-state={slot.state}
                          disabled={slot.state !== "bookable"}
                          aria-label={`Select ${clock(slot.starts_at)}, ${new Date(slot.starts_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })} (UTC)${slot.state !== "bookable" ? ", unavailable" : ""}`}
                          aria-pressed={selectedSlot === slot.id}
                          onClick={() => {
                            setSelectedSlot(slot.id);
                            onSlot(slot.id, slot.revision, slot.starts_at, slot.ends_at);
                          }}
                        >
                          {clock(slot.starts_at)}
                        </button>
                      ) : (
                        <p className="available-slot" data-state={slot.state} key={slot.id}>{clock(slot.starts_at)} – {clock(slot.ends_at)}</p>
                      ),
                    )}
                  </div>
                </div>
              );
            })}
            <p className="availability-note">Times shown in UTC.</p>
          </div>
        )}
      </Resource>
      <form className="availability-range-form" noValidate onSubmit={(e) => e.preventDefault()}>
        <details className="availability-range">
          <summary>Another date or UTC range</summary>
          <label className="availability-date">Choose date (UTC)<input type="date" min={today} value={selectedDay ?? today} onChange={(e) => { if (e.target.value) { setWeekStart(e.target.value); chooseDay(e.target.value); } }} /></label>
          <Inputs
            fields={[
              { name: "from", label: "From (UTC)" },
              { name: "to", label: "To (UTC)" },
            ]}
            values={values}
            change={(name, value) => { setValues({ ...values, [name]: value }); onClear?.(); }}
          />
        </details>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  );
}
export function Booking({
  patientId,
  doctorId,
  doctorName,
  patientName,
  patientProfile,
  onSuccess,
  onLockChange,
}: {
  patientId?: string;
  doctorId?: string;
  doctorName?: string;
  patientName?: string;
  patientProfile?: PatientProfile;
  onSuccess?: () => void;
  onLockChange?: (locked:boolean)=>void;
}) {
  const {state,api}=useAuth();
  const demo = useLocalDemo();
  const [doctor, setDoctor] = useState(doctorId ?? "");
  const [doctorInfo, setDoctorInfo] = useState<Doctor | null>(null);
  const [slot, setSlot] = useState<{ id: string; revision: number; startsAt: string; endsAt: string } | null>(null);
  const [doctorLabel,setDoctorLabel] = useState(doctorName??"");
  const [locked,setLocked] = useState(false);
  const [confirmed,setConfirmed] = useState<{ appointment: Appointment; doctor: string } | null>(null);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const [bookedAppointments, setBookedAppointments] = useState<Appointment[]>([]);
  const chooseDoctor = (value: string, label: string, info: Doctor | null) => {
    setDoctor(value);
    setDoctorLabel(label);
    setDoctorInfo(info);
    setSlot(null);
    setConfirmed(null);
  };
  const specialty = doctorInfo?.specialties.map((item) => item.name).join(", ");
  return (
    <PageGrid preset="three" className="booking-composition">
      <section className="booking-doctor" aria-labelledby="booking-step-doctor"><fieldset disabled={locked}>
        <h3 id="booking-step-doctor"><span className="step-number">1</span>Select Doctor</h3>
        {!doctorId && <AppointmentDoctorRail selected={doctor} onSelect={(item) => { if (!locked) chooseDoctor(item.id, item.display_name, item); }} />}
        <AdvancedLookup title="Search the complete directory"><DoctorAutocomplete api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} onSelect={(item) => chooseDoctor(item.id, item.label, null)} /></AdvancedLookup>
        <AdvancedLookup title="Use a doctor ID"><Lookup label="Doctor ID for availability" onSelect={(value) => chooseDoctor(value, "", null)} /></AdvancedLookup>
      </fieldset></section>
      <section className="booking-schedule" aria-labelledby="booking-step-time"><fieldset disabled={locked}>
        <h3 id="booking-step-time"><span className="step-number">2</span>Choose Date &amp; Time</h3>
        {!doctor && <div className="resource-empty"><DepartmentIcon department="appointments"/><strong>Choose a doctor first</strong><p>Their accepted dates and slots will appear here.</p></div>}
        {doctor && (
          <AvailabilityPicker
            bookedAppointments={bookedAppointments}
            key={doctor}
            doctorId={doctor}
            doctorName={doctorLabel ? `${doctorLabel}${specialty ? ` (${specialty})` : ""}` : undefined}
            revision={availabilityRevision}
            onClear={() => setSlot(null)}
            onSlot={(id, revision, startsAt, endsAt) => { setConfirmed(null); setSlot({ id, revision, startsAt, endsAt }); }}
          />
        )}
      </fieldset>
      {patientProfile && (
        <section className="booking-patient-details" aria-labelledby="booking-patient-title">
          <h4 id="booking-patient-title">Patient details</h4>
          <dl className="booking-patient-facts">
            <div><dt>Full name</dt><dd>{patientProfile.display_name}</dd></div>
            <div><dt>Date of birth</dt><dd>{patientProfile.date_of_birth ?? "Not provided"}</dd></div>
            <div><dt>Contact</dt><dd>{patientProfile.synthetic_contact ?? "Not provided"}</dd></div>
          </dl>
          <small>From the patient profile. Edit it at Reception.</small>
        </section>
      )}
      </section>
      <aside className="booking-receipt" aria-labelledby="booking-step-summary">
        <h3 id="booking-step-summary"><span className="step-number">3</span>Appointment Summary</h3>
        <div className="booking-doctor-card">
          <DoctorPortrait name={doctorLabel || "Doctor"} index={doctor ? demo?.doctors[doctor]?.portrait : undefined} />
          <div><strong>{doctorLabel || (doctor ? `Doctor …${doctor.slice(-4)}` : "Choose a doctor")}</strong>{specialty && <small>{specialty}</small>}</div>
        </div>
        {confirmed ? (
          <m.div initial={{ opacity: 0.5, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="printed-receipt" role="status">
            <p className="printed-receipt__brand"><DepartmentIcon department="appointments" />PulseGrid · Appointment slip</p>
            <strong>Appointment booked</strong>
            <dl>
              <div><dt>Doctor</dt><dd>{confirmed.doctor || `Doctor …${confirmed.appointment.doctor_id.slice(-4)}`}</dd></div>
              <div><dt>Date</dt><dd>{longDay(confirmed.appointment.starts_at)}</dd></div>
              <div><dt>Time (UTC)</dt><dd>{clock(confirmed.appointment.starts_at)} – {clock(confirmed.appointment.ends_at)}</dd></div>
              <div><dt>Patient</dt><dd>{patientName || (patientId ? `Patient …${patientId.slice(-4)}` : "—")}</dd></div>
              <div><dt>Visit</dt><dd>…{confirmed.appointment.id.slice(-4)}</dd></div>
            </dl>
            <ItemDetails><Facts values={{ "Appointment ID": confirmed.appointment.id, "Doctor ID": confirmed.appointment.doctor_id, "Slot ID": confirmed.appointment.slot_id }} /></ItemDetails>
            <p>Confirmed by the Appointment service.</p>
            <button type="button" className="printed-receipt__again" onClick={() => setConfirmed(null)}>Book another appointment</button>
          </m.div>
        ) : (
          <>
            <dl className="booking-summary-facts">
              <div><dt>Date</dt><dd>{slot ? longDay(slot.startsAt) : "Choose a time"}</dd></div>
              <div><dt>Time (UTC)</dt><dd>{slot ? `${clock(slot.startsAt)} – ${clock(slot.endsAt)}` : "—"}</dd></div>
              <div><dt>Patient</dt><dd>{patientName || (patientId ? `Patient …${patientId.slice(-4)}` : "Enter the patient below")}</dd></div>
            </dl>
            {slot ? (
              <div data-check="appointments-primary">
                <CommandForm<Appointment>
                  key={slot.id}
                  onLockChange={value=>{setLocked(value);onLockChange?.(value);}}
                  title="Book appointment"
                  reviewLabel="Review booking"
                  confirmLabel="Confirm booking"
                  successMessage="Appointment booked."
                  path="/api/v1/appointments"
                  fields={patientId ? [] : [idField("patient_id", "Patient ID")]}
                  build={(values) => ({
                    patient_id: patientId ?? id(values.patient_id.trim()),
                    slot_id: slot.id,
                    expected_schedule_revision: slot.revision,
                  })}
                  onSuccess={(item) => {
                    setBookedAppointments(visits => [...visits, item]);
                    setConfirmed({ appointment: item, doctor: doctorLabel });
                    setSlot(null);
                    setAvailabilityRevision((value) => value + 1);
                    onSuccess?.();
                  }}
                  notice="Appointment rechecks this accepted time when you confirm."
                />
              </div>
            ) : <p className="booking-hint">Select a doctor and an available time to continue.</p>}
            <div className="printed-receipt printed-receipt--pending">
              <p className="printed-receipt__brand"><DepartmentIcon department="appointments" />PulseGrid · Appointment slip</p>
              <p>Your printed slip appears here after booking.</p>
            </div>
          </>
        )}
      </aside>
    </PageGrid>
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
            title="Create specialty" reviewLabel="Review specialty" confirmLabel="Create specialty" successMessage="Specialty created."
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
            title="Create doctor" reviewLabel="Review doctor" confirmLabel="Create doctor" successMessage="Doctor created."
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
function WalkinRegistration({onSuccess,onLockChange}:{onSuccess:()=>void;onLockChange:(locked:boolean)=>void}) {
  const [draft,setDraft]=useState("");
  const [search,setSearch]=useState("");
  const [patient,setPatient]=useState<PatientProfile|null>(null);
  const [locked,setLocked]=useState(false);
  const [booked,setBooked]=useState(false);
  const [error,setError]=useState("");
  const step = booked ? 3 : patient ? 2 : 1;
  const steps = ["Find patient", "Doctor & slot", "Confirm"];
  return <div className="walkin-workspace">
    <ol className="walkin-steps" aria-label="Walk-in steps">{steps.map((label, index) => <li key={label} aria-current={step === index + 1 ? "step" : undefined} data-done={step > index + 1}><span className="step-number">{index + 1}</span>{label}</li>)}</ol>
    <div className="walkin-entry">
      <section className="walkin-find" aria-labelledby="walkin-find-title">
        <h3 id="walkin-find-title"><span className="step-number">1</span>Find patient</h3>
        {patient ? (
          <div className="walkin-patient-strip"><div><strong>{patient.display_name}</strong><small>{patient.date_of_birth ? `Born ${patient.date_of_birth}` : "Date of birth not provided"}</small></div><button type="button" disabled={locked} onClick={()=>{setPatient(null);setBooked(false);}}>Change patient</button><ItemDetails>Patient ID {patient.id}</ItemDetails></div>
        ) : (
          <>
            <form className="walkin-patient-search" onSubmit={e=>{e.preventDefault();if(draft.trim().length<2||draft.trim().length>100){setError("Search must contain 2 to 100 characters.");return;}setSearch(draft.trim());setPatient(null);setError("");}}><label>Find existing patient<input disabled={locked} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Patient name…"/></label><button disabled={locked}>Search patients</button>{error&&<p role="alert">{error}</p>}</form>
            {search && <Collection<PatientProfile> title="Matching patients" path={query("/api/v1/patients",{q:search})} renderItem={item=><div className="walkin-match"><span><strong>{item.display_name}</strong><small>{item.date_of_birth ? `Born ${item.date_of_birth}` : "Date of birth not provided"}</small></span><button type="button" disabled={locked} onClick={()=>setPatient(item)}>Use this patient</button></div>}/>}
            <p className="walkin-intake-note">New patients register an account first. <Link to="/receptionist/dashboard">Open the Reception desk →</Link></p>
          </>
        )}
      </section>
      {patient && <Booking key={patient.id} patientId={patient.id} patientProfile={patient} patientName={patient.display_name} onSuccess={()=>{setBooked(true);onSuccess();}} onLockChange={value=>{setLocked(value);onLockChange(value);}}/>}
    </div>
    <aside className="walkin-guidance" aria-labelledby="walkin-guidance-title"><h3 id="walkin-guidance-title">Walk-in information</h3><ul><li>Registration uses an existing patient profile and an accepted appointment slot.</li><li>New patients create an account through patient registration before booking.</li><li>Availability and check-in eligibility are confirmed by the Appointment service.</li><li>Check-in and queue tokens are issued from the check-in and journey tools below.</li></ul></aside>
  </div>;
}
type AppointmentView = "book" | "manage" | "reschedule" | "walk-in";
const appointmentViews: { key: AppointmentView; label: string; param: string }[] = [
  { key: "book", label: "Book Appointment", param: "" },
  { key: "manage", label: "My Appointments", param: "upcoming" },
  { key: "reschedule", label: "Reschedule / Cancel", param: "reschedule" },
  { key: "walk-in", label: "Walk-in Registration", param: "walk-in" },
];
function MonthCalendar({ value, onChange, disabled }: { value: string; onChange: (day: string) => void; disabled?: boolean }) {
  const today = isoDay(Date.now());
  const [month, setMonth] = useState(value.slice(0, 7));
  const [year, monthIndex] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, monthIndex - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const length = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate();
  const shift = (delta: number) => setMonth(isoDay(Date.UTC(year, monthIndex - 1 + delta, 1)).slice(0, 7));
  return (
    <div className="month-calendar">
      <div className="month-calendar__head">
        <button type="button" aria-label="Previous month" disabled={disabled || month <= today.slice(0, 7)} onClick={() => shift(-1)}>‹</button>
        <strong>{first.toLocaleDateString("en-IN", { month: "long", year: "numeric", timeZone: "UTC" })}</strong>
        <button type="button" aria-label="Next month" disabled={disabled} onClick={() => shift(1)}>›</button>
      </div>
      <div className="month-calendar__grid">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((name) => <span key={name} aria-hidden="true">{name}</span>)}
        {Array.from({ length: offset }, (_, index) => <span key={`blank-${index}`} aria-hidden="true" />)}
        {Array.from({ length }, (_, index) => {
          const day = `${month}-${String(index + 1).padStart(2, "0")}`;
          return (
            <button key={day} type="button" disabled={disabled || day < today} aria-pressed={day === value} aria-label={new Date(utcStart(day)).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })} onClick={() => onChange(day)}>
              {index + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}
export function Appointments({
  reception = false,
  doctor = false,
  title,
  subtitle,
}: {
  reception?: boolean;
  doctor?: boolean;
  title?: string;
  subtitle?: string;
}) {
  const {state,api}=useAuth();
  const demo=useLocalDemo();
  const ownProfile=useResource<PatientProfile>(!reception&&!doctor?"/api/v1/patients/me":null);
  const doctorRoster=useResource<Page<Doctor>>("/api/v1/doctors?limit=20");
  const [params,setParams]=useSearchParams();
  const requested = appointmentViews.find((item) => item.param && item.param === params.get("view"))?.key ?? "book";
  const view: AppointmentView = doctor ? "manage" : requested === "walk-in" && !reception ? "book" : requested;
  const setView=(value: AppointmentView)=>{const param = appointmentViews.find((item) => item.key === value)!.param; setParams(param ? { view: param } : {}, { replace: true });};
  const [managementLocked,setManagementLocked] = useState(false);
  const [bookingLocked,setBookingLocked] = useState(false);
  const [walkinLocked,setWalkinLocked] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [listTab, setListTab] = useState<"upcoming" | "past" | "cancelled">("upcoming");
  const [revision, setRevision] = useState(0);
  const [targetDoctor, setTargetDoctor] = useState("");
  const [targetDay, setTargetDay] = useState(isoDay(Date.now()));
  const [targetSlot, setTargetSlot] = useState<{
    id: string;
    revision: number;
    startsAt: string;
  } | null>(null);
  const listPath = reception || doctor ? "/api/v1/appointments" : ownProfile.response ? query("/api/v1/appointments", { patient_id: ownProfile.response.data.id }) : null;
  const list = useCursorPage<Appointment>(listPath, revision);
  const current = useResource<Appointment>(selected ? `/api/v1/appointments/${selected}` : null, revision);
  const now = Date.now();
  const doctorFor = (doctorId: string) => doctorRoster.response?.data.items.find((item) => item.id === doctorId);
  const doctorName = (doctorId: string) => doctorFor(doctorId)?.display_name ?? `Clinician …${doctorId.slice(-4)}`;
  const category = (item: Appointment) => item.state === "cancelled" ? "cancelled" : Date.parse(item.ends_at) < now ? "past" : "upcoming";
  const counts = { upcoming: 0, past: 0, cancelled: 0 };
  list.items.forEach((item) => { counts[category(item)] += 1; });
  const anyLocked = managementLocked || bookingLocked || walkinLocked;
  const openChange = (item: Appointment) => {
    setSelected(item.id);
    setTargetDoctor(item.doctor_id);
    setTargetDay(isoDay(Math.max(Date.parse(item.starts_at), now)));
    setTargetSlot(null);
    if (!doctor) setView("reschedule");
  };
  const paged = list.hasNext || list.hasPrevious;
  const item = current.response?.data;
  const rows = list.items.filter((entry) => category(entry) === listTab).sort((a, b) => (listTab === "past" ? -1 : 1) * a.starts_at.localeCompare(b.starts_at));
  const tabs = appointmentViews.filter((entry) => entry.key !== "walk-in" || reception);
  return (
    <div className="appointment-workspace">
      {title && <DepartmentSign department="appointments" title={title} subtitle={subtitle ?? ""} />}
      {ownProfile.error&&<p role="alert">{ownProfile.error}</p>}
      {!doctor && <nav className="department-tabs" aria-label="Appointment views">{tabs.map((entry) => <button type="button" key={entry.key} disabled={anyLocked} aria-pressed={view===entry.key} onClick={()=>setView(entry.key)}><DepartmentIcon department={entry.key === "walk-in" ? "reception" : "appointments"} />{reception && entry.key === "manage" ? "Appointments" : entry.label}</button>)}</nav>}
      {reception && view === "walk-in" && <section className="appointment-walkin"><WalkinRegistration onSuccess={()=>setRevision(v=>v+1)} onLockChange={setWalkinLocked}/></section>}
      {!doctor && view === "book" && (
        <section className="appointment-booking" aria-label="Book an appointment">
          {reception ? (
            <Booking onLockChange={setBookingLocked} onSuccess={() => setRevision((v) => v + 1)} />
          ) : (
            <Resource<PatientProfile> path="/api/v1/patients/me" showReload={false}>
              {(profile) => <Booking onLockChange={setBookingLocked} patientId={profile.id} patientName={profile.display_name} patientProfile={profile} onSuccess={() => setRevision((v) => v + 1)} />}
            </Resource>
          )}
        </section>
      )}
      {(doctor || view === "manage") && (
        <div className="appointment-manage">
          <section className="appointment-list-desk" aria-label={reception ? "Appointments" : doctor ? "Assigned appointments" : "My appointments"}>
            <div className="appointment-subtabs" role="tablist" aria-label="Appointment lists">
              {(["upcoming", "past", "cancelled"] as const).map((key) => <button key={key} type="button" role="tab" aria-selected={listTab === key} onClick={() => setListTab(key)}>{key === "upcoming" ? "Upcoming" : key === "past" ? "Past" : "Cancelled"} ({counts[key]})</button>)}
              <PageRefresh type="button" className="appointment-refresh" disabled={list.loading} onClick={list.refresh}>Refresh</PageRefresh>
            </div>
            {list.loading && <p role="status">Loading appointments…</p>}
            {list.error && <p role="alert">{list.error}</p>}
            {list.loaded && !list.loading && rows.length === 0 && <p className="appointment-empty">No {listTab} appointments in this list.</p>}
            <ol className="appointment-rows">
              {rows.map((entry) => {
                const kind = category(entry);
                const clinician = doctorFor(entry.doctor_id);
                return (
                  <li key={entry.id} className="appointment-row" data-kind={kind}>
                    <div className="appointment-row__when"><strong>{formatSlot(entry.starts_at)}</strong><span>{new Date(entry.starts_at).toLocaleDateString("en", { weekday: "short", timeZone: "UTC" })} · {Math.round((Date.parse(entry.ends_at) - Date.parse(entry.starts_at)) / 60000)} min · UTC</span></div>
                    <div className="appointment-row__doctor"><DoctorPortrait name={clinician?.display_name ?? "Clinician"} index={demo?.doctors[entry.doctor_id]?.portrait}/><div><strong>{doctorName(entry.doctor_id)}</strong><small>{clinician?.specialties.map(s=>s.name).join(", ") ?? "Specialty not returned"}</small>{(reception||doctor)&&<small>{demo?.patients[entry.patient_id]?.name??`Patient …${entry.patient_id.slice(-4)}`}</small>}</div></div>
                    <span className="owner-state" data-state={kind}>{kind === "upcoming" ? "Confirmed" : kind === "past" ? "Past visit" : "Cancelled"}</span>
                    <div className="appointment-row__actions">
                      <button type="button" aria-label={`View appointment ${entry.id}`} aria-expanded={expanded === entry.id} onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}>View</button>
                      {!doctor && kind === "upcoming" && <>
                        <button type="button" disabled={managementLocked} aria-label={`Reschedule appointment ${entry.id}`} onClick={() => openChange(entry)}>Reschedule</button>
                        <button type="button" className="button-danger-outline" disabled={managementLocked} aria-label={`Cancel appointment ${entry.id}`} onClick={() => openChange(entry)}>Cancel</button>
                      </>}
                    </div>
                    {expanded === entry.id && (
                      <div className="appointment-row__detail">
                        <Facts values={{ Visit: `…${entry.id.slice(-4)}`, State: entry.state, "Starts (UTC)": entry.starts_at, "Ends (UTC)": entry.ends_at }} />
                        {!doctor && entry.state === "confirmed" && <details className="appointment-share"><summary>Secure appointment links</summary><AppointmentShortLinkPanel api={api} roleHints={state.status === "authenticated" ? state.roleHints : []} appointmentId={entry.id}/></details>}
                        <ItemDetails><Facts values={{ "Appointment ID": entry.id, "Patient ID": entry.patient_id, "Doctor ID": entry.doctor_id, Version: entry.version }} /></ItemDetails>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
            {paged && <div className="appointment-pages"><button type="button" disabled={!list.hasPrevious} onClick={list.previous}>Previous page</button><button type="button" disabled={!list.hasNext} onClick={list.next}>Next page</button></div>}
          </section>
          {!doctor && (
            <aside className="appointment-overview" aria-labelledby="appointment-overview-title">
              <h3 id="appointment-overview-title">Appointment overview</h3>
{paged && <p className="appointment-overview__scope">Based on this page of appointments.</p>}
              <dl>
                <div data-kind="upcoming"><dt>Upcoming</dt><dd>{counts.upcoming}</dd></div>
                <div data-kind="past"><dt>Past</dt><dd>{counts.past}</dd></div>
                <div data-kind="cancelled"><dt>Cancelled</dt><dd>{counts.cancelled}</dd></div>
              </dl>
              <button type="button" disabled={anyLocked} onClick={() => setView("book")}>Book a new appointment</button>
            </aside>
          )}
        </div>
      )}
      {!doctor && view === "reschedule" && (
        <section className="reschedule-desk" aria-label="Reschedule or cancel an appointment">
          {!selected && (
            <div className="reschedule-pick">
              <h3>Choose an appointment to change</h3>
              {list.loading && <p role="status">Loading appointments…</p>}
              {list.items.filter((entry) => category(entry) === "upcoming").map((entry) => (
                <button key={entry.id} type="button" className="reschedule-pick__row" aria-label={`Reschedule appointment ${entry.id}`} onClick={() => openChange(entry)}>
                  <strong>{formatSlot(entry.starts_at)} UTC</strong><span>{doctorName(entry.doctor_id)}</span>
                </button>
              ))}
              {list.loaded && counts.upcoming === 0 && <p>No upcoming appointments can be changed.</p>}
            </div>
          )}
          {selected && current.loading && !item && <p role="status">Loading appointment…</p>}
          {current.error && <p role="alert">{current.error}</p>}
          {item && (
            <FlashArea resetKey={item.id}>
            <div key={item.id}>
              <div className="reschedule-columns">
                <section className="reschedule-current" aria-labelledby="reschedule-current-title">
                  <h3 id="reschedule-current-title">Current appointment</h3>
                  <div className="booking-doctor-card"><DoctorPortrait name={doctorFor(item.doctor_id)?.display_name ?? "Clinician"} index={demo?.doctors[item.doctor_id]?.portrait}/><div><strong>{doctorName(item.doctor_id)}</strong><small>{doctorFor(item.doctor_id)?.specialties.map((entry) => entry.name).join(", ")}</small></div></div>
                  <dl className="booking-summary-facts">
                    <div><dt>Date</dt><dd>{longDay(item.starts_at)}</dd></div>
                    <div><dt>Time (UTC)</dt><dd>{clock(item.starts_at)} – {clock(item.ends_at)}</dd></div>
                    <div><dt>Status</dt><dd><span className="owner-state" data-state={category(item)}>{item.state === "cancelled" ? "Cancelled" : "Confirmed"}</span></dd></div>
                  </dl>
                  {item.state === "confirmed" && <fieldset className="reschedule-doctor" disabled={managementLocked}><details><summary>Choose a different doctor</summary><Lookup label="Target doctor ID" onSelect={(value) => { setTargetDoctor(value); setTargetSlot(null); }} /></details></fieldset>}
                  <button type="button" disabled={managementLocked} onClick={() => { setSelected(null); setTargetSlot(null); }}>Choose another appointment</button>
                </section>
                {item.state === "confirmed" ? (
                  <>
                    <section className="reschedule-month" aria-labelledby="reschedule-month-title">
                      <h3 id="reschedule-month-title">Select new date</h3>
                      <MonthCalendar value={targetDay} disabled={managementLocked} onChange={(day) => { setTargetDay(day); setTargetSlot(null); }} />
                    </section>
                    <section className="reschedule-slots" aria-labelledby="reschedule-slots-title">
                      <h3 id="reschedule-slots-title">Available time slots</h3>
                      <fieldset className="reschedule-calendar" disabled={managementLocked}>
                        {targetDoctor && <AvailabilityPicker key={targetDoctor} doctorId={targetDoctor} doctorName={targetDoctor === item.doctor_id ? undefined : doctorName(targetDoctor)} day={targetDay} showWeek={false} onClear={() => setTargetSlot(null)} onSlot={(id, revision, startsAt) => setTargetSlot({ id, revision, startsAt })} />}
                      </fieldset>
                    </section>
                  </>
                ) : <p className="reschedule-closed">This appointment is cancelled and cannot be changed.</p>}
              </div>
              {item.state === "confirmed" && (
                <div className="reschedule-actions">
                  <div className="reschedule-actions__cancel">
                    <CommandForm
                      onLockChange={setManagementLocked}
                      title="Cancel appointment"
                      reviewLabel="Review cancellation"
                      confirmLabel="Cancel appointment"
                      successMessage="Appointment cancelled."
                      path={`/api/v1/appointments/${item.id}/cancel`}
                      fields={[{ ...reasonField, label: "Reason for cancelling" }]}
                      conditional
                      etag={current.response?.etag ?? null}
                      onReload={() => { current.refresh(); list.refresh(); }}
                      reloadLabel="Reload appointment"
                      onSuccess={() => { setTargetSlot(null); setRevision((v) => v + 1); }}
                    />
                  </div>
                  <div className="reschedule-actions__confirm" data-check="appointments-reschedule">
                    {targetSlot ? (
                      <CommandForm
                        key={targetSlot.id}
                        onLockChange={setManagementLocked}
                        title="Reschedule appointment"
                        reviewLabel="Review new time"
                        confirmLabel="Confirm new time"
                        successMessage={(moved: Appointment) => `Appointment moved to ${visitTime(moved.starts_at)}.`}
                        path={`/api/v1/appointments/${item.id}/reschedule`}
                        conditional
                        etag={current.response?.etag ?? null}
                        onReload={() => { current.refresh(); list.refresh(); setTargetSlot(null); }}
                        reloadLabel="Reload appointment"
                        build={() => ({
                          target_slot_id: targetSlot.id,
                          expected_schedule_revision: targetSlot.revision,
                        })}
                        notice={`Move your visit with ${doctorName(item.doctor_id)} on ${visitTime(item.starts_at)} to ${targetDoctor === item.doctor_id ? "the same doctor" : doctorName(targetDoctor)} on ${visitTime(targetSlot.startsAt)}.`}
                        onSuccess={() => { setTargetSlot(null); setRevision((v) => v + 1); }}
                      />
                    ) : <p className="reschedule-hint">Choose a new date and time to review the change.</p>}
                  </div>
                </div>
              )}
            </div>
            </FlashArea>
          )}
        </section>
      )}
    </div>
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
      label: "Time zone",
      required: true,
      max: 128,
      initial: "Asia/Kolkata",
    },
    {
      name: "slot_minutes",
      label: "Slot length (minutes)",
      kind: "number",
      required: true,
      min: 5,
      max: 120,
    },
    {
      name: "expected_revision",
      label: "Current schedule reference",
      kind: "number",
      required: true,
      min: 0,
    },
  ];
  return (
    <Panel title="Propose schedule changes">
      <p>
        Choose your new appointment times in UTC. Leave the intervals empty to propose closing your schedule. Rejected changes keep your current slots.
      </p>

      <CommandForm<Proposal>
        title="Submit schedule proposal" reviewLabel="Review proposal" confirmLabel="Submit proposal" successMessage="Schedule proposal submitted."
        path={`/api/v1/doctors/${doctor.id}/schedules`}
        fields={fields}
        conditional
        etag={etag}
        build={(values) => {
          const body = buildFields(fields, values);
          try {
            new Intl.DateTimeFormat("en", { timeZone: values.timezone.trim() });
          } catch {
            throw new Error("Enter a valid Time zone.");
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
  dashboard = false,
}: {
  doctor: Doctor;
  etag: string | null;
  refresh: () => void;
  admin?: boolean;
  dashboard?: boolean;
}) {
  const [tab,setTab]=useState("Today");
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
      {dashboard && <div className="task-tabs" role="tablist" aria-label="Doctor dashboard">{["Today","Profile","Schedule changes"].map(name=><button key={name} role="tab" aria-selected={tab===name} type="button" onClick={()=>setTab(name)}>{name}</button>)}</div>}
      <section hidden={dashboard && tab!=="Profile"}>
      <CommandForm
        title="Save doctor profile" reviewLabel="Review profile" confirmLabel="Save profile" successMessage="Profile saved."
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
      </section>
      <section hidden={dashboard && tab!=="Today"}>
      {dashboard && <><h2>Today's slots</h2><Link className="button" to="/doctor/queue">Open patient queue</Link></>}
      <AvailabilityPicker doctorId={doctor.id} />
      </section>
      <section hidden={dashboard && tab!=="Schedule changes"}>
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
        columns={[
 {label:"Starts",render:proposal=>proposal.intervals[0]?formatDateTime(proposal.intervals[0].starts_at):"Closure"},
 {label:"Time zone",render:proposal=>proposal.timezone},
 {label:"Status",render:proposal=>proposal.status},
 {label:"Actions",render:proposal=><><button type="button" onClick={()=>{setSelected(proposal.id);setDecision(null);}}>Open</button><ItemDetails>Proposal {proposal.id} · Revision {proposal.revision}</ItemDetails></>},
 ]}
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
              title="Request schedule decision" reviewLabel="Review decision" confirmLabel="Send decision" successMessage="Decision sent."
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
              title="Apply accepted schedule" reviewLabel="Review schedule update" confirmLabel="Apply schedule" successMessage="Schedule updated."
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
      </section>
    </>
  );
}
export function DoctorDashboard() {
  return (
    <Panel title="Your day">
      <Resource<DoctorSelf> path="/api/v1/doctors/me">
        {(data, etag, refresh) => (
          <DoctorManagement dashboard
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
function visitTime(value: string) {
  return formatDateTime(value, { utc: true });
}
