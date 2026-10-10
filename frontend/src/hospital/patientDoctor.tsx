import { useState } from "react";
import { useAuth, roles } from "../auth/authContext";
import type {
  Appointment,
  Availability,
  Decision,
  Doctor,
  DoctorSelf,
  PatientProfile,
  Proposal,
  Specialty,
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
  return (
    <Panel title="Your profile">
      <Resource<PatientProfile> path="/api/v1/patients/me">
        {(profile, etag, refresh) => (
          <ProfileEditor
            key={profile.version}
            profile={profile}
            etag={etag}
            path="/api/v1/patients/me"
            refresh={refresh}
          />
        )}
      </Resource>
    </Panel>
  );
}
export function Demographics({ admin = false }: { admin?: boolean }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  return (
    <>
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
    </>
  );
}
export function StaffManagement() {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [filters, setFilters] = useState<Values>({});
  const [draft, setDraft] = useState<Values>({});
  const [error, setError] = useState("");
  return (
    <>
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
    </>
  );
}
export function AvailabilityPicker({
  doctorId,
  onSlot,
}: {
  doctorId: string;
  onSlot?: (slotId: string, revision: number) => void;
}) {
  const [values, setValues] = useState<Values>({});
  const [path, setPath] = useState<string | null>(null);
  const [error, setError] = useState("");
  return (
    <Panel title="Accepted availability">
      <p>
        Enter UTC timestamps explicitly. Availability is a hint; the service
        verifies the slot when booking.
      </p>
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
        <Inputs
          fields={[
            { name: "from", label: "From (UTC)" },
            { name: "to", label: "To (UTC)" },
          ]}
          values={values}
          change={(name, value) => setValues({ ...values, [name]: value })}
        />
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
            {data.slots.map((slot) => (
              <div key={slot.id}>
                <p>
                  {slot.starts_at} to {slot.ends_at}
                </p>
                {onSlot && (
                  <button
                    type="button"
                    onClick={() => onSlot(slot.id, slot.revision)}
                  >
                    Select slot {slot.id}
                  </button>
                )}
              </div>
            ))}
          </>
        )}
      </Resource>
    </Panel>
  );
}
export function Booking({
  patientId,
  doctorId,
  onSuccess,
}: {
  patientId?: string;
  doctorId?: string;
  onSuccess?: () => void;
}) {
  const [doctor, setDoctor] = useState(doctorId ?? "");
  const [slot, setSlot] = useState<{ id: string; revision: number } | null>(
    null,
  );
  return (
    <>
      <Lookup
        label="Doctor ID for availability"
        onSelect={(value) => {
          setDoctor(value);
          setSlot(null);
        }}
      />
      {doctor && (
        <AvailabilityPicker
          key={doctor}
          doctorId={doctor}
          onSlot={(id, revision) => setSlot({ id, revision })}
        />
      )}
      {slot && (
        <CommandForm
          key={slot.id}
          title="Book appointment"
          path="/api/v1/appointments"
          fields={patientId ? [] : [idField("patient_id", "Patient ID")]}
          build={(values) => ({
            patient_id: patientId ?? id(values.patient_id.trim()),
            slot_id: slot.id,
            expected_schedule_revision: slot.revision,
          })}
          onSuccess={onSuccess}
          notice={`Selected slot ${slot.id}, accepted revision ${slot.revision}.`}
        />
      )}
    </>
  );
}
export function DoctorDirectory({ admin = false }: { admin?: boolean }) {
  const [draft, setDraft] = useState<Values>({});
  const [filters, setFilters] = useState<Values>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const { state } = useAuth();
  const patient =
    state.status === "authenticated" && state.roleHints.includes("patient");
  const fields: Field[] = [
    { name: "q", label: "Doctor search", max: 100 },
    idField("specialty_id", "Specialty ID filter", false),
    ...(admin
      ? [
          {
            name: "active",
            label: "Active filter",
            kind: "select" as const,
            options: ["true", "false"],
          },
        ]
      : []),
  ];
  return (
    <>
      <Collection<Specialty>
        title="Specialties"
        revision={revision}
        path="/api/v1/doctors/specialties"
        renderItem={(item) => (
          <>
            <strong>{item.name}</strong>
            <p>ID: {item.id}</p>
            <button
              onClick={() => {
                setDraft({ ...draft, specialty_id: item.id });
                setFilters({ ...filters, specialty_id: item.id });
                setSelected(null);
              }}
            >
              Filter by {item.name}
            </button>
          </>
        )}
      />
      <Panel title="Directory filters">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            try {
              buildFields(fields, draft);
              if (
                draft.q &&
                (draft.q.trim().length < 2 || draft.q.trim().length > 100)
              )
                throw new Error("Search must contain 2 to 100 characters.");
              setFilters(
                Object.fromEntries(
                  Object.entries(draft).map(([k, v]) => [k, v.trim()]),
                ),
              );
              setSelected(null);
              setError("");
            } catch (err) {
              setError(err instanceof Error ? err.message : "Invalid filters.");
            }
          }}
        >
          <Inputs
            fields={fields}
            values={draft}
            change={(name, value) => setDraft({ ...draft, [name]: value })}
          />
          <button>Search doctors</button>
          {error && <p role="alert">{error}</p>}
        </form>
      </Panel>
      <Collection<Doctor>
        title="Doctors"
        revision={revision}
        path={query("/api/v1/doctors", filters)}
        renderItem={(doctor) => (
          <>
            <strong>{doctor.display_name}</strong>
            <p>
              {doctor.specialties.map((s) => s.name).join(", ")} •{" "}
              {doctor.active ? "Active" : "Inactive"}
            </p>
            <button onClick={() => setSelected(doctor.id)}>
              View doctor {doctor.id}
            </button>
          </>
        )}
      />
      <Selected<Doctor> path={selected ? `/api/v1/doctors/${selected}` : null}>
        {(doctor, etag, refresh) => (
          <>
            <Facts
              values={{
                "Doctor ID": doctor.id,
                Name: doctor.display_name,
                Specialties: doctor.specialties.map((s) => s.name).join(", "),
                Active: doctor.active ? "Yes" : "No",
              }}
            />
            {admin ? (
              <DoctorManagement
                doctor={doctor}
                etag={etag}
                refresh={() => {
                  refresh();
                  setRevision((v) => v + 1);
                }}
                admin
              />
            ) : patient ? (
              <Resource<PatientProfile> path="/api/v1/patients/me">
                {(profile) => (
                  <Booking patientId={profile.id} doctorId={doctor.id} />
                )}
              </Resource>
            ) : (
              <AvailabilityPicker doctorId={doctor.id} />
            )}
          </>
        )}
      </Selected>
      {admin && (
        <Panel title="Create directory entries">
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
        </Panel>
      )}
    </>
  );
}
export function Appointments({
  reception = false,
  doctor = false,
}: {
  reception?: boolean;
  doctor?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [targetDoctor, setTargetDoctor] = useState("");
  const [targetSlot, setTargetSlot] = useState<{
    id: string;
    revision: number;
  } | null>(null);
  return (
    <>
      {!doctor &&
        (reception ? (
          <Panel title="New booking">
            <Booking onSuccess={() => setRevision((v) => v + 1)} />
          </Panel>
        ) : (
          <Resource<PatientProfile> path="/api/v1/patients/me">
            {(profile) => (
              <Panel title="New booking">
                <Booking
                  patientId={profile.id}
                  onSuccess={() => setRevision((v) => v + 1)}
                />
              </Panel>
            )}
          </Resource>
        ))}
      <Collection<Appointment>
        title="Appointments"
        path="/api/v1/appointments"
        revision={revision}
        renderItem={(item) => (
          <>
            <Facts
              values={{
                "Appointment ID": item.id,
                "Patient ID": item.patient_id,
                "Doctor ID": item.doctor_id,
                "Starts (UTC)": item.starts_at,
                State: item.state,
              }}
            />
            <button
              onClick={() => {
                setSelected(item.id);
                setTargetSlot(null);
                setTargetDoctor("");
              }}
            >
              View appointment {item.id}
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
    </>
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
