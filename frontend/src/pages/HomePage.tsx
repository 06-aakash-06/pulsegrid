import { Link } from "react-router-dom";

const audiences = [
  { title: "Patients", detail: "Appointments, records, billing, and care updates." },
  { title: "Care teams", detail: "Consultation, queue, and prescription workspaces." },
  { title: "Hospital staff", detail: "Pharmacy, billing, emergency, and administration." },
];

export function HomePage() {
  return (
    <main>
      <section className="hero-section">
          <div className="hero-copy">
            <p className="eyebrow">Hospital management foundation</p>
            <h1>One place for care and hospital operations.</h1>
            <p className="hero-description">
              PulseGrid is preparing connected workspaces for patients and hospital teams.
              Service connections are not configured yet, so this preview contains no live activity.
            </p>
            <div className="hero-actions">
              <Link className="button" to="/login">Sign in to PulseGrid <span aria-hidden="true">→</span></Link>
              <Link className="button button--secondary" to="/register">Patient registration</Link>
            </div>
            <div className="foundation-note">
              <span className="foundation-note-dot" aria-hidden="true" />
              <span>Prototype foundation · Synthetic data only</span>
            </div>
          </div>
          <div className="hero-panel" aria-label="PulseGrid workspace preview">
            <div className="hero-panel-top">
              <div>
                <p className="eyebrow">PulseGrid workspaces</p>
                <h2>Designed around clear ownership</h2>
              </div>
              <span className="panel-index" aria-hidden="true">01</span>
            </div>
            <div className="workspace-preview-list">
              {audiences.map((audience, index) => (
                <div className="workspace-preview" key={audience.title}>
                  <span className="preview-number">0{index + 1}</span>
                  <div>
                    <h3>{audience.title}</h3>
                    <p>{audience.detail}</p>
                  </div>
                  <span className="preview-arrow" aria-hidden="true">↗</span>
                </div>
              ))}
            </div>
            <p className="hero-panel-footnote">Each service will provide its own authorized information.</p>
          </div>
      </section>
    </main>
  );
}
