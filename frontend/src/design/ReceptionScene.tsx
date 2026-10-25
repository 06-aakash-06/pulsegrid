import { AdvancedLookup } from "../components/PageTools";
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { gsap } from "gsap";
import { DepartmentIcon, type Department } from "./DepartmentIcon";
const slips: {
  label: string;
  description: string;
  path: string;
  department: Department;
}[] = [
  {
    label: "Book an Appointment",
    description: "Find a doctor and schedule your visit",
    path: "doctors",
    department: "appointments",
  },
  {
    label: "My Appointments",
    description: "View and manage your upcoming visits",
    path: "appointments?view=upcoming",
    department: "appointments",
  },
  {
    label: "Check In",
    description: "Use your secure QR code or check-in link",
    path: "check-in",
    department: "waiting",
  },
  {
    label: "View Records",
    description: "Access your authorized medical history",
    path: "records",
    department: "records",
  },
];
export function ReceptionScene({
  name,
  publicView = false,
  summary,
  children,
}: {
  name?: string;
  publicView?: boolean;
  summary?: ReactNode;
  children?: ReactNode;
}) {
  const scene = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.fromTo(
        scene.current?.querySelectorAll(".wayfinding-sign,.appointment-slip") ??
          [],
        { y: 10, opacity: 0.6 },
        { y: 0, opacity: 1, duration: 0.45, stagger: 0.045, clearProps: "all" },
      );
    });
    return () => media.revert();
  }, []);
  const href = (path: string) => `/patient/${path}`;
  return (
    <div
      className={`reception-scene${publicView ? " reception-scene--public" : ""}`}
      ref={scene}
    >
      <AdvancedLookup title="Department shortcuts"><nav className="wayfinding" aria-label="Hospital wayfinding">
        {[
          {
            title: "Consultation",
            path: "doctors",
            sub: "Find a doctor",
            dep: "consultation",
          },
          {
            title: "Waiting Room",
            path: "queue",
            sub: "Your live queue",
            dep: "waiting",
          },
          {
            title: "Pharmacy",
            path: "pharmacy",
            sub: "Your medicines",
            dep: "pharmacy",
          },
          {
            title: "Emergency",
            path: "emergency",
            sub: "Urgent help",
            dep: "emergency",
          },
        ].map((s) => (
          <Link
            key={s.path}
            className={`wayfinding-sign wayfinding-sign--${s.dep}`}
            to={href(s.path)}
          >
            <DepartmentIcon department={s.dep as Department} />
            <span>
              <strong>{s.title}</strong>
              <small>{s.sub}</small>
            </span>
            <b aria-hidden="true">→</b>
          </Link>
        ))}
      </nav></AdvancedLookup>
      <section className="welcome-wall">
        <div>
          <p className="welcome-intro">
            {publicView ? "Welcome to" : "Welcome back,"}
          </p>
          <h2>
            {publicView
              ? "PulseGrid."
              : name
                ? `${name.split(" ")[0]}.`
                : "Your hospital."}
          </h2>

        </div>
        {summary}
        {publicView && (
          <aside className="reception-guidance">
            <p className="eyebrow">YOUR VISIT, CONNECTED</p>
            <p>
              Find your doctor.
              <br />
              Plan your appointment.
              <br />
              Follow your care journey.
            </p>
            {publicView && (
              <Link className="button" to="/login">
                Sign in to PulseGrid <span aria-hidden="true">→</span>
              </Link>
            )}
          </aside>
        )}
      </section>
      {publicView && (
        <div className="robot-conversation">
          <p>
            Hello.<br />
            Find your way with the hospital directory.
          </p>
          <span aria-hidden="true">✦</span>
        </div>
      )}
      <div className="reception-counter">
        <h2 className="reception-counter-label">Start here</h2>
        <div className="appointment-slips">
          {slips.map((s) => (
            <Link
              className={`appointment-slip slip-object--${s.path.split("?")[0]}`}
              key={s.label}
              to={href(s.path)}
            >
              <span className="slip-object-backing" aria-hidden="true" />
              <span className="slip-object-binding" aria-hidden="true" />
              <DepartmentIcon department={s.department} />
              <strong>{s.label}</strong>
              <p>{s.description}</p>
              <span className="slip-arrow" aria-hidden="true">
                →
              </span>
            </Link>
          ))}
        </div>
      </div>
      {children}
    </div>
  );
}
