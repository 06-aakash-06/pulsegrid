import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import type {
  Appointment,
  Availability,
  Doctor,
  Page,
  Specialty,
  PatientProfile,
} from "../hospital/models";
import { useResource, query } from "../hospital/ui";
import { DoctorAutocomplete } from "../phase4";
import { DepartmentIcon } from "./DepartmentIcon";
import { DoctorPortrait, useLocalDemo, type DemoHospital } from "./localDemo";
const clock = (value: string) =>
  new Date(value).toLocaleTimeString("en", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
function bounds() {
  const from = new Date();
  from.setUTCHours(0, 0, 0, 0);
  return {
    from: from.toISOString(),
    to: new Date(from.getTime() + 2 * 86400000).toISOString(),
  };
}
function DoctorAvailability({
  doctor,
  selected = false,
}: {
  doctor: Doctor;
  selected?: boolean;
}) {
  const [range] = useState(bounds);
  const resource = useResource<Availability>(
    query("/api/v1/appointments/availability", {
      doctor_id: doctor.id,
      ...range,
    }),
  );
  const first = resource.response?.data.slots[0];
  return (
    <div
      className={`doctor-availability${selected ? " doctor-availability--profile" : ""}`}
    >
      <span
        className={
          first
            ? "availability-dot"
            : "availability-dot availability-dot--quiet"
        }
        aria-hidden="true"
      />
      <strong>
        {resource.loading
          ? "Checking schedule"
          : resource.error
            ? "Schedule unavailable"
            : first
              ? "Next available"
              : "No open slots"}
      </strong>
      <small>
        {first
          ? `${clock(first.starts_at)} · ${new Date(first.starts_at).toLocaleDateString("en", { day: "numeric", month: "short", timeZone: "UTC" })} UTC`
          : resource.error
            ? "Try again in Schedule"
            : "Next 48 hours"}
      </small>
      {selected && resource.response && (
        <div className="profile-schedule-metrics">
          <span>
            <strong>{resource.response.data.slots.length}</strong>
            <small>Open times</small>
          </span>
          <span>
            <strong>
              {
                new Set(
                  resource.response.data.slots.map((s) =>
                    s.starts_at.slice(0, 10),
                  ),
                ).size
              }
            </strong>
            <small>Schedule days</small>
          </span>
          <span>
            <strong>{resource.response.data.accepted_revision}</strong>
            <small>Accepted revision</small>
          </span>
        </div>
      )}
      {selected && resource.response && (
        <div className="profile-slot-strip">
          {resource.response.data.slots.slice(0, 4).map((slot) => (
            <span key={slot.id}>{clock(slot.starts_at)}</span>
          ))}
        </div>
      )}
    </div>
  );
}
function ProfileSchedule({ doctor }: { doctor: Doctor }) {
  const [range] = useState(bounds);
  const resource = useResource<Availability>(
    query("/api/v1/appointments/availability", {
      doctor_id: doctor.id,
      ...range,
    }),
  );
  return (
    <div className="profile-accepted-schedule">
      {resource.loading ? (
        <p role="status">Loading accepted schedule…</p>
      ) : resource.error ? (
        <p role="alert">{resource.error}</p>
      ) : resource.response ? (
        <>
          <p>Accepted times · next 48 hours · UTC</p>
          <div>
            {resource.response.data.slots.slice(0, 12).map((slot) => (
              <span key={slot.id}>
                <small>
                  {new Date(slot.starts_at).toLocaleDateString("en", {
                    day: "numeric",
                    month: "short",
                    timeZone: "UTC",
                  })}
                </small>
                {clock(slot.starts_at)}
              </span>
            ))}
          </div>
          {!resource.response.data.slots.length && (
            <p>No available times in this range.</p>
          )}
          <small>
            Revision {resource.response.data.accepted_revision}. Booking
            rechecks the selected time.
          </small>
        </>
      ) : null}
    </div>
  );
}
function ScheduleRail({ demo }: { demo: DemoHospital | null }) {
  const { state } = useAuth();
  const roleHints = state.status === "authenticated" ? state.roleHints : [];
  const destination = roleHints.includes("receptionist")
    ? "/receptionist/appointments"
    : roleHints.includes("patient")
      ? "/patient/appointments"
      : roleHints.includes("doctor")
        ? "/doctor/consultations"
        : null;
  const list = useResource<Page<Appointment>>(
    destination ? "/api/v1/appointments?limit=100" : null,
  );
  const doctors = useResource<Page<Doctor>>(
    demo ? "/api/v1/doctors?q=Dr.&limit=100" : "/api/v1/doctors?limit=100",
  );
  const visible = (list.response?.data.items ?? [])
    .filter(
      (a) =>
        a.state === "confirmed" && (!demo || !!demo.patients[a.patient_id]),
    )
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
    .slice(0, 6);
  return (
    <section className="consultation-schedule">
      <div className="schedule-title">
        <h2>Consultation schedule</h2>
        <span>
          {new Date().toLocaleDateString("en", {
            weekday: "short",
            day: "numeric",
            month: "short",
            timeZone: "UTC",
          })}{" "}
          · UTC
        </span>
      </div>
      {!destination ? (
        <p>Appointment access is not available for this account.</p>
      ) : list.error ? (
        <p role="alert">{list.error}</p>
      ) : list.loading ? (
        <p role="status">Loading authorized appointments…</p>
      ) : visible.length ? (
        <div className="schedule-visits">
          {visible.map((a, i) => (
            <Link
              key={a.id}
              to={destination!}
              className="schedule-visit"
              style={
                {
                  "--visit-color": [
                    "#3586b7",
                    "#38967b",
                    "#283c43",
                    "#ca7d37",
                    "#886399",
                  ][i % 5],
                } as React.CSSProperties
              }
            >
              <time dateTime={a.starts_at}>{clock(a.starts_at)}</time>
              <strong>
                {demo?.appointments[a.id]?.label ?? `Visit ${i + 1}`}
              </strong>
              <span>
                {demo?.patients[a.patient_id]?.name ?? "Authorized patient"}
              </span>
              <small>
                {doctors.response?.data.items.find((d) => d.id === a.doctor_id)
                  ?.display_name ?? "Consultation"}{" "}
                ↗
              </small>
            </Link>
          ))}
        </div>
      ) : (
        <p>
          No authorized appointments in this page.{" "}
          <Link to={destination!}>Find an appointment →</Link>
        </p>
      )}
    </section>
  );
}
export function ReferenceConsultation({
  admin = false,
  revision = 0,
  renderManagement,
  createEntries,
  booking,
}: {
  admin?: boolean;
  revision?: number;
  renderManagement: (
    doctor: Doctor,
    etag: string | null,
    refresh: () => void,
  ) => ReactNode;
  createEntries: ReactNode;
  booking: (
    doctor: Doctor,
    onLockChange?: (locked: boolean) => void,
  ) => ReactNode;
}) {
  const { state, api } = useAuth();
  // Resolve only this signed-in patient's owner profile for direct-link identity.
  useResource<PatientProfile>(
    state.status === "authenticated" && state.roleHints.includes("patient")
      ? "/api/v1/patients/me"
      : null,
  );
  const demo = useLocalDemo();
  const [allRecords,setAllRecords]=useState(false);
  useEffect(()=>{if(revision>0&&demo)setAllRecords(true);},[revision,demo]);
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState<string>();
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("About");
  const [bookOpen, setBookOpen] = useState(false);
  const [bookingLocked, setBookingLocked] = useState(false);
  const [manual, setManual] = useState({ q: "", specialty_id: "", active: "" });
  const specialties = useResource<Page<Specialty>>(
    "/api/v1/doctors/specialties?limit=20",
    revision,
  );
  const path = query("/api/v1/doctors", {
    ...(demo && !allRecords ? { q: "Dr." } : {}),
    ...filters,
  });
  const roster = useResource<Page<Doctor>>(
    `${path}${path.includes("?") ? "&" : "?"}limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    revision,
  );
  const rows = (roster.response?.data.items ?? []).filter(
    (d) => !demo || allRecords || !!demo.doctors[d.id],
  );
  useEffect(() => {
    if (rows.length && !rows.some((d) => d.id === selected))
      setSelected(rows[0].id);
  }, [roster.response, demo]);
  const profile = useResource<Doctor>(
    selected ? `/api/v1/doctors/${selected}` : null,
  );
  const doctor = profile.response?.data ?? null;
  function apply(next: Record<string, string>) {
    if (bookingLocked) return;
    setFilters(next);
    setSelected(null);
    setBookOpen(false);
    setCursor(undefined);
    setHistory([]);
    setError("");
  }
  function submit(
    q: string,
    specialty_id = filters.specialty_id ?? "",
    active = filters.active ?? "",
  ) {
    if (bookingLocked) return;
    if (q.trim() && (q.trim().length < 2 || q.trim().length > 100)) {
      setError("Search must contain 2 to 100 characters.");
      return;
    }
    if (specialty_id && !/^[1-9][0-9]{0,18}$/.test(specialty_id)) {
      setError("Enter a valid positive decimal ID.");
      return;
    }
    apply(
      Object.fromEntries(
        Object.entries({ q: q.trim(), specialty_id, active }).filter(
          ([, v]) => v,
        ),
      ),
    );
  }
  const patient =
    state.status === "authenticated" && state.roleHints.includes("patient");
  const canCoordinate =
    state.status === "authenticated" &&
    state.roleHints.some((r) => r === "patient" || r === "receptionist");
  const appointmentDestination =
    state.status === "authenticated" && state.roleHints.includes("receptionist")
      ? "/receptionist/appointments"
      : "/patient/appointments";
  return (
    <div className="reference-consultation">
      <div className="consultation-wall-heading">
        <div>
          <h1>Consultation</h1>
          <p>Expert care across specialties.</p>
        </div>
        <div className="consultation-wall-mark">
          <DepartmentIcon department="consultation" />
          <span>
            CONSULT
            <br />
            DIAGNOSE
            <br />
            TREAT
            <br />
            TOGETHER
          </span>
        </div>
      </div>
      <nav className="consultation-tabs" aria-label="Consultation department">
        <span aria-current="page">
          <DepartmentIcon department="consultation" />
          Doctors
        </span>
        {canCoordinate && (
          <Link to={appointmentDestination}>
            <DepartmentIcon department="appointments" />
            Appointments
          </Link>
        )}
        {patient && (
          <>
            <Link to="/patient/records">
              <DepartmentIcon department="records" />
              Medical Records
            </Link>
            <Link to="/patient/prescriptions">
              <DepartmentIcon department="pharmacy" />
              Prescriptions
            </Link>
          </>
        )}
      </nav>
      <div className="consultation-board">
        <aside className="reference-specialties">
          <h2>
            Specialties <span aria-hidden="true">⌕</span>
          </h2>
          <button
            className={!filters.specialty_id ? "is-selected" : ""}
            onClick={() => apply({ ...filters, specialty_id: "" })}
          >
            All Specialties{" "}
            <span>
              {rows.length}
              {roster.response?.data.next_cursor ? "+" : ""}
            </span>
          </button>
          {specialties.error && <p role="alert">{specialties.error}</p>}
          {specialties.loading && <p role="status">Loading specialties…</p>}
          {(specialties.response?.data.items ?? [])
            .filter((s) => !demo || allRecords || demo.specialties.includes(s.id))
            .map((s) => (
              <button
                key={s.id}
                className={filters.specialty_id === s.id ? "is-selected" : ""}
                onClick={() => {
                  setManual({ ...manual, specialty_id: s.id });
                  apply({ ...filters, specialty_id: s.id });
                }}
              >
                {s.name}
                <span>›</span>
              </button>
            ))}
          <details className="specialty-tools">
            <summary>Find a specialty</summary>
            <DoctorAutocomplete
              kind="specialty"
              api={api}
              roleHints={
                state.status === "authenticated" ? state.roleHints : []
              }
              onSelect={(s) => apply({ ...filters, specialty_id: s.id })}
            />
          </details>
          {demo && <p className="demo-footnote">Fictional demo hospital</p>}
        </aside>
        <section className="reference-roster">
          <h2 className="sr-only">Doctors</h2>
          <form
            className="doctor-search-bar"
            onSubmit={(e) => {
              e.preventDefault();
              submit(
                demo && !allRecords &&
                  search.trim() &&
                  !search.trim().toLowerCase().startsWith("dr.")
                  ? `Dr. ${search.trim()}`
                  : search,
              );
            }}
          >
            <label className="sr-only" htmlFor="reference-doctor-search">
              Search doctor by name
            </label>
            <span aria-hidden="true">⌕</span>
            <input
              id="reference-doctor-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search doctor by name…"
            />
            <button type="submit">Search</button>
          </form>
          <div className="roster-caption">
            <span>{rows.length} doctors on this page</span>
            <button
              disabled={bookingLocked || roster.loading}
              onClick={roster.refresh}
            >
              Refresh
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
          {roster.error && <p role="alert">{roster.error}</p>}
          {roster.loading && <p role="status">Loading doctors…</p>}
          {!roster.loading && !rows.length && (
            <p>No doctors match this search.</p>
          )}
          <div className="reference-doctor-list">
            {rows.map((d) => (
              <button
                key={d.id}
                aria-label={`View doctor ${d.id}`}
                aria-pressed={selected === d.id}
                disabled={bookingLocked}
                className="reference-doctor-row"
                onClick={() => {
                  setSelected(d.id);
                  setTab("About");
                  setBookOpen(false);
                }}
              >
                <DoctorPortrait
                  name={d.display_name}
                  index={demo?.doctors[d.id]?.portrait}
                />
                <span className="doctor-row-name">
                  <strong>{d.display_name}</strong>
                  <span>{d.specialties.map((s) => s.name).join(", ")}</span>
                  <small>
                    {d.active ? "Active clinician" : "Inactive directory entry"}
                  </small>
                </span>
                <DoctorAvailability doctor={d} />
                <span className="roster-arrow" aria-hidden="true">
                  →
                </span>
              </button>
            ))}
          </div>
          <div className="roster-pagination">
            <button
              disabled={bookingLocked || !history.length || roster.loading}
              onClick={() => {
                setCursor(history.at(-1));
                setHistory(history.slice(0, -1));
              }}
            >
              Previous page
            </button>
            <button
              disabled={bookingLocked || !roster.response?.data.next_cursor || roster.loading}
              onClick={() => {
                setHistory([...history, cursor]);
                setCursor(roster.response!.data.next_cursor!);
              }}
            >
              Next page
            </button>
          </div>
        </section>
        <aside className="reference-doctor-profile">
          {profile.loading ? (
            <p role="status">Loading doctor profile…</p>
          ) : profile.error ? (
            <p role="alert">{profile.error}</p>
          ) : doctor ? (
            <>
              <div className="reference-profile-top">
                <DoctorPortrait
                  name={doctor.display_name}
                  index={demo?.doctors[doctor.id]?.portrait}
                  large
                />
                <div>
                  <span className="profile-active">
                    ● {doctor.active ? "Active clinician" : "Inactive"}
                  </span>
                  <h2>{doctor.display_name}</h2>
                  <p>{doctor.specialties.map((s) => s.name).join(", ")}</p>
                  {demo && <small>Fictional demo clinician</small>}
                </div>
              </div>
              <div className="reference-profile-status">
                <DoctorAvailability doctor={doctor} selected />
              </div>
              <nav className="profile-tabs" aria-label="Doctor profile">
                <button
                  aria-pressed={tab === "About"}
                  disabled={bookingLocked}
                  onClick={() => setTab("About")}
                >
                  About
                </button>
                <button
                  aria-pressed={tab === "Schedule"}
                  disabled={bookingLocked}
                  onClick={() => setTab("Schedule")}
                >
                  Schedule
                </button>
                <button
                  aria-pressed={tab === "Details"}
                  disabled={bookingLocked}
                  onClick={() => setTab("Details")}
                >
                  Details
                </button>
              </nav>
              {tab === "About" ? (
                <div className="profile-about">
                  <p>
                    Consultation and appointment coordination in{" "}
                    {doctor.specialties.map((s) => s.name).join(", ")}.
                  </p>
                  <h3>Specialties</h3>
                  <div className="specialty-chips">
                    {doctor.specialties.map((s) => (
                      <span key={s.id}>{s.name}</span>
                    ))}
                  </div>
                </div>
              ) : tab === "Schedule" ? (
                <ProfileSchedule doctor={doctor} />
              ) : (
                <div className="profile-technical-details">
                  <dl>
                    <dt>Directory reference</dt>
                    <dd>
                      {demo?.doctors[doctor.id]?.label ?? "Doctor profile"}
                    </dd>
                    <dt>Internal Doctor ID</dt>
                    <dd>{doctor.id}</dd>
                    <dt>Revision</dt>
                    <dd>{doctor.version}</dd>
                  </dl>
                  <button onClick={profile.refresh}>
                    Reload doctor profile
                  </button>
                </div>
              )}
              {patient && (
                <button
                  className="reference-book-button"
                  disabled={bookingLocked}
                  onClick={() => setBookOpen(!bookOpen)}
                  aria-expanded={bookOpen}
                >
                  Book Appointment <span aria-hidden="true">→</span>
                </button>
              )}
              {admin && (
                <details
                  id="directory-management"
                  className="profile-management"
                >
                  <summary>Manage doctor profile</summary>
                  {renderManagement(
                    doctor,
                    profile.response?.etag ?? null,
                    () => {
                      profile.refresh();
                      roster.refresh();
                    },
                  )}
                </details>
              )}
            </>
          ) : (
            <div className="profile-placeholder">
              <DepartmentIcon department="consultation" />
              <h2>Doctor profile</h2>
              <p>The first available profile opens with the directory.</p>
            </div>
          )}
        </aside>
      </div>
      {bookOpen && doctor && (
        <section className="reference-booking-desk">
          <h2>Book with {doctor.display_name}</h2>
          {booking(doctor, setBookingLocked)}
        </section>
      )}
      <div className="consultation-desk">
        <ScheduleRail demo={demo} />
        <aside className="consultation-quick">
          <h2>Quick Actions</h2>
          {canCoordinate && (
            <Link to={appointmentDestination}>
              <DepartmentIcon department="appointments" />
              <span>
                <strong>Manage appointments</strong>
                <small>Review and coordinate visits</small>
              </span>
            </Link>
          )}
          {patient && (
            <>
              <Link to="/patient/records">
                <DepartmentIcon department="records" />
                <span>
                  <strong>View medical records</strong>
                  <small>Open your authorized history</small>
                </span>
              </Link>
              <Link to="/patient/prescriptions">
                <DepartmentIcon department="pharmacy" />
                <span>
                  <strong>View prescriptions</strong>
                  <small>Review issued prescriptions</small>
                </span>
              </Link>
            </>
          )}
          {admin && (
            <Link to="/admin/staff">
              <DepartmentIcon department="reception" />
              <span>
                <strong>Staff directory</strong>
                <small>Manage authorized accounts</small>
              </span>
            </Link>
          )}
        </aside>
      </div>
      <details className="reference-advanced">
        <summary>Advanced directory search & autocomplete</summary>
        {demo&&<label><input type="checkbox" checked={allRecords} disabled={bookingLocked} onChange={e=>{setAllRecords(e.target.checked);setFilters({});setSearch('');setCursor(undefined);setHistory([]);setSelected(null);}}/>Show all owner records, including integration fixtures</label>}
        <DoctorAutocomplete
          api={api}
          roleHints={state.status === "authenticated" ? state.roleHints : []}
          onSelect={(d) => {if(!bookingLocked)setSelected(d.id);}}
        />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(manual.q, manual.specialty_id, manual.active);
          }}
        >
          <label>
            Doctor search
            <input
              value={manual.q}
              onChange={(e) => setManual({ ...manual, q: e.target.value })}
            />
          </label>
          <label>
            Specialty ID filter
            <input
              value={manual.specialty_id}
              onChange={(e) =>
                setManual({ ...manual, specialty_id: e.target.value })
              }
            />
          </label>
          {admin && (
            <label>
              Active filter
              <select
                value={manual.active}
                onChange={(e) =>
                  setManual({ ...manual, active: e.target.value })
                }
              >
                <option value="">All</option>
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </label>
          )}
          <button>Search doctors</button>
        </form>
      </details>
      {admin && (
        <details className="reference-advanced">
          <summary>Create directory entries</summary>
          {createEntries}
        </details>
      )}
    </div>
  );
}
