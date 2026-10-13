import { Link } from "react-router-dom";
import type { Appointment, Page } from "../hospital/models";
import type { OwnQueue } from "../advanced/patient/contracts";
import { useResource } from "../hospital/ui";
import { useLocalDemo } from "./localDemo";
import { DepartmentIcon } from "./DepartmentIcon";
export function ReceptionVisit({ patientId }: { patientId: string }) {
  const demo = useLocalDemo();
  const visits = useResource<Page<Appointment>>(
    `/api/v1/appointments?patient_id=${patientId}&limit=20`,
  );
  const rows = (visits.response?.data.items ?? []).filter(
    (a) => a.state === "confirmed",
  );
  rows.sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const first =
    rows.find(
      (a) => a.starts_at.slice(0, 10) === new Date().toISOString().slice(0, 10),
    ) ?? rows[0];
  const queue = useResource<OwnQueue>(
    first ? `/api/v1/appointments/${first.id}/queue` : null,
  );
  return (
    <>
      <aside className="reception-hospital-today">
        <p className="eyebrow">
          {demo ? "YOUR VISIT TODAY" : "YOUR VISIT TODAY"}
        </p>
        <div>
          <DepartmentIcon department="appointments" />
          <strong>{visits.loading ? "—" : rows.length}</strong>
          <span>Confirmed visits</span>
        </div>
        <div>
          <DepartmentIcon department="consultation" />
          <strong>
            {visits.loading ? "—" : new Set(rows.map((a) => a.doctor_id)).size}
          </strong>
          <span>Consulting doctors</span>
        </div>
        <div>
          <DepartmentIcon department="waiting" />
          <strong>{queue.response?.data.waiting_count ?? "—"}</strong>
          <span>
            {queue.response ? "In this queue" : "Queue after check-in"}
          </span>
        </div>
        {visits.error && (
          <p className="reception-live-error" role="alert">
            Visit information unavailable.
          </p>
        )}
        <small>
          {demo
            ? "Fictional demo · Owner service data"
            : "Your authorized appointments"}
        </small>
      </aside>
      {queue.response && (
        <Link to="/patient/queue" className="counter-token-stand">
          <small>YOUR TOKEN</small>
          <strong>{`A${String(queue.response.data.entry.token_number).padStart(3, "0")}`}</strong>
          <span>Consultation</span>
          <span>{queue.response.data.entry.state.replaceAll("_", " ")}</span>
          <b aria-hidden="true">→</b>
        </Link>
      )}
      <div className="reception-information-rail">
        <section className="reception-today">
          <div className="reception-info-title">
            <h3>Today at PulseGrid</h3>
            <span>
              {new Date().toLocaleDateString("en", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>
          </div>
          {first ? (
            <>
              <p className="reception-next-time">
                <time dateTime={first.starts_at}>
                  {new Date(first.starts_at).toLocaleTimeString("en", {
                    hour: "2-digit",
                    minute: "2-digit",
                    timeZone: "UTC",
                  })}{" "}
                  UTC
                </time>
                <span>
                  {Date.parse(first.starts_at) > Date.now()
                    ? "Your next consultation"
                    : "Scheduled consultation"}
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
        <Link className="reception-queue-display" to="/patient/queue">
          <span>{queue.response ? "YOUR QUEUE TOKEN" : "LIVE QUEUE"}</span>
          <div className="queue-flaps">
            {(queue.response
              ? `A${String(queue.response.data.entry.token_number).padStart(3, "0")}`
              : "—"
            )
              .split("")
              .map((letter, i) => (
                <strong key={i}>{letter}</strong>
              ))}
          </div>
          <div>
            <strong>
              {queue.response?.data.entry.state.replaceAll("_", " ") ??
                "Check in for your token"}
            </strong>
            <small>
              {queue.response
                ? `${queue.response.data.waiting_count} waiting in this queue`
                : "Your place appears after check-in"}
            </small>
          </div>
          <b aria-hidden="true">→</b>
        </Link>
        <section className="reception-announcements">
          <h3>
            Announcements <span aria-hidden="true">◖</span>
          </h3>
          <p>
            <i aria-hidden="true" />
            View the latest status of your visit in{" "}
            <Link to="/patient/journey">Patient journey</Link>.
          </p>
          <p>
            <i aria-hidden="true" />
            Use <Link to="/patient/check-in">Check In</Link> for your secure
            appointment token.
          </p>
          <small>Hospital announcements feed is not connected.</small>
        </section>
      </div>
    </>
  );
}
