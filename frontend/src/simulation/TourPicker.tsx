import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "../auth/authContext";
import { runnableSteps } from "./engine";
import { useSimulation } from "./SimulationProvider";
import type { Tour } from "./types";

export function TourPicker() {
  const simulation = useSimulation();
  const { state: auth } = useAuth();
  const roles = auth.status === "authenticated" ? auth.roleHints : [];
  const available = simulation ? simulation.tours.filter((tour) => simulation.sampleBackend || !tour.role || roles.includes(tour.role)) : [];
  const own = available.find((tour) => tour.role && roles.includes(tour.role));
  const [chosen, setChosen] = useState<Tour | undefined>(own ?? available[0]);
  const [allowActions, setAllowActions] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  useLayoutEffect(() => heading.current?.focus(), []);
  if (!simulation) return null;
  const live = !simulation.sampleBackend;
  const stepCount = (tour: Tour) => runnableSteps(tour, simulation.sampleBackend, allowActions).length;
  return createPortal(
    <div className="simulation-backdrop" data-simulation-picker>
      <div className="simulation-picker" role="dialog" aria-modal="true" aria-labelledby="simulation-picker-title">
        <h2 id="simulation-picker-title" ref={heading} tabIndex={-1}>Walk me through the app as…</h2>
        {live && <p className="simulation-picker__banner" role="note">Simulation uses real actions on this server. Use demo data only.</p>}
        <div className="simulation-picker__list" role="radiogroup" aria-label="Walkthroughs">
          {available.map((tour) => (
            <button
              key={tour.id}
              type="button"
              role="radio"
              aria-checked={chosen?.id === tour.id}
              className="simulation-picker__tour"
              data-tour={`simulation-tour-${tour.id}`}
              onClick={() => setChosen(tour)}
            >
              <strong>{tour.roleLabel}</strong>
              <span>{tour.goal}</span>
              <small>About {stepCount(tour)} steps · 2 min{tour.role && roles.includes(tour.role) ? " · your role" : ""}</small>
            </button>
          ))}

        </div>
        {live && (
          <label className="simulation-picker__allow">
            <input type="checkbox" checked={allowActions} onChange={(event) => setAllowActions(event.target.checked)} />
            Allow demo actions (booking, check-in, payments)
          </label>
        )}
        <div className="simulation-card__actions">
          <button type="button" onClick={simulation.exit}>Cancel</button>
          <button type="button" className="simulation-card__primary" disabled={!chosen} data-tour="simulation-start" onClick={() => chosen && simulation.start(chosen, allowActions)}>
            Start walkthrough
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** Header switch; off by default. Turning it on opens the picker, turning it off ends the walkthrough. */
export function SimulationSwitch() {
  const simulation = useSimulation();
  if (!simulation) return null;
  const on = simulation.state.status !== "idle";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className="simulation-switch"
      data-tour="simulation-switch"
      onClick={on ? simulation.exit : simulation.openPicker}
    >
      <span className="simulation-switch__track" aria-hidden="true"><span /></span>
      <span>Simulation mode</span>
    </button>
  );
}
