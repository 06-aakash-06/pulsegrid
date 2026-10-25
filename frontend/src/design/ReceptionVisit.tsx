import { Link } from "react-router-dom";
import type { Appointment, Page } from "../hospital/models";
import type { OwnQueue } from "../advanced/patient/contracts";
import { formatDateTime, useResource } from "../hospital/ui";
import { DepartmentIcon } from "./DepartmentIcon";
import { ReceptionScene } from "./ReceptionScene";
const finishedStates = ["completed", "cancelled", "no_show"];
export function ReceptionVisit({ patientId, name }: { patientId: string; name?: string }) {
  const visits = useResource<Page<Appointment>>(
    `/api/v1/appointments?patient_id=${patientId}&limit=20`,
  );
  const rows = (visits.response?.data.items ?? []).filter(
    (a) => a.state === "confirmed",
  );
  rows.sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const todayUtc = new Date().toISOString().slice(0, 10);
  const today = rows.filter((a) => a.starts_at.slice(0, 10) === todayUtc);
  const upcoming = rows.find((a) => Date.parse(a.ends_at) > Date.now());
  const first = today.find((a) => Date.parse(a.ends_at) > Date.now()) ?? today[0] ?? upcoming;
  const queue = useResource<OwnQueue>(
    first ? `/api/v1/appointments/${first.id}/queue` : null,
  );
  const entry = queue.response?.data.entry;
  const finished = !!entry && finishedStates.includes(entry.state);
  const doctors = new Set(today.map((a) => a.doctor_id)).size;
  const stats = (
    <aside className="reception-hospital-today" aria-label="Your visit today">
      <p className="eyebrow">Your visit today</p>
      <div className="reception-stats">
        <div>
          <DepartmentIcon department="appointments" />
          <strong>{visits.loading ? "—" : today.length}</strong>
          <span>{today.length === 1 ? "visit today" : "visits today"}</span>
        </div>
        <div>
          <DepartmentIcon department="consultation" />
          <strong>{visits.loading ? "—" : doctors}</strong>
          <span>{doctors === 1 ? "doctor today" : "doctors today"}</span>
        </div>
        <div>
          <DepartmentIcon department="waiting" />
          <strong>{entry && !finished ? queue.response?.data.waiting_count : "—"}</strong>
          <span>{entry && !finished ? "in this queue" : finished ? "visit completed" : "after check-in"}</span>
        </div>
      </div>
      {visits.error && (
        <p className="reception-live-error" role="alert">
          Visit information unavailable.
        </p>
      )}
      {!visits.loading && today.length === 0 && (
        <small>
          {upcoming ? `Next visit ${formatDateTime(upcoming.starts_at)}` : "No visits booked"}
        </small>
      )}
    </aside>
  );
  return (
    <ReceptionScene name={name} summary={stats}>
      <div className="reception-information-rail">
        <section className="reception-today">
          <div className="reception-info-title">
            <h3>Today at PulseGrid</h3>
            <span>
              {formatDateTime(new Date(), { time: false })}
            </span>
          </div>
          {first ? (
            <>
              <p className="reception-next-time">
                <time dateTime={first.starts_at}>
                  {first.starts_at.slice(0, 10) === todayUtc
                    ? `${first.starts_at.slice(11, 16)} UTC`
                    : formatDateTime(first.starts_at)}
                </time>
                <span>
                  {first.starts_at.slice(0, 10) === todayUtc && Date.parse(first.starts_at) <= Date.now()
                    ? "Scheduled consultation"
                    : "Your next consultation"}
                </span>
              </p>
              <Link to="/patient/appointments?view=upcoming">
                View your appointment →
              </Link>
            </>
          ) : (
            <p>Plan your next visit with the doctor directory.</p>
          )}
        </section>
        {finished ? (
          <section className="reception-queue-display reception-queue-display--done">
            <span>Your visit</span>
            <strong>Visit completed</strong>
            <Link className="button" to="/patient/journey">View visit summary</Link>
          </section>
        ) : entry ? (
          <Link className="reception-queue-display" to="/patient/queue">
            <span>Your queue token</span>
            <div className="queue-flaps" aria-label={`Token A${String(entry.token_number).padStart(3, "0")}`}>
              {`A${String(entry.token_number).padStart(3, "0")}`
                .split("")
                .map((letter, i) => (
                  <strong key={i} aria-hidden="true">{letter}</strong>
                ))}
            </div>
            <div>
              <strong>{entry.state.replaceAll("_", " ")}</strong>
              <small>{`${queue.response?.data.waiting_count} waiting in this queue`}</small>
            </div>
            <b aria-hidden="true">→</b>
          </Link>
        ) : (
          <section className="reception-queue-display reception-queue-display--empty">
            <span>Your queue token</span>
            <strong>Not checked in yet</strong>
            <small>Your token appears after check-in.</small>
            <Link className="button" to="/patient/check-in">Check in</Link>
          </section>
        )}
        <section className="reception-announcements">
          <h3>Announcements</h3>
          <ul>
            <li>
              Follow your visit in <Link to="/patient/journey">Patient journey</Link>.
            </li>
            <li>
              Use <Link to="/patient/check-in">Check In</Link> for your secure appointment token.
            </li>
          </ul>
          <small>Hospital announcements feed is not connected.</small>
        </section>
      </div>
    </ReceptionScene>
  );
}
