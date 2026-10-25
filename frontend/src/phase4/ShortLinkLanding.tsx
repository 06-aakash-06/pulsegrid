import { formatDateTime } from "../hospital/ui";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AdmissionFeedback } from "./AdmissionFeedback";
import { isCanonicalId } from "./api";
import type {
  ShortLinkLandingProps,
  ShortLinkResolution,
} from "./contracts";

let pendingAlias: string | null = null;

function validAlias(value: string): boolean {
  return /^[A-Za-z0-9]{22}$/.test(value);
}

function isAbort(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function validateResolution(
  resolution: ShortLinkResolution,
  canPatient: boolean,
  canReceptionist: boolean,
): boolean {
  if (
    !isCanonicalId(resolution.appointment_id)
    || !["appointment", "check_in"].includes(resolution.purpose)
    || !Number.isFinite(Date.parse(resolution.expires_at))
  ) return false;

  const id = resolution.appointment_id;
  const patientAppointments = "/patient/appointments";
  const patientCheckin = "/patient/check-in#appointment_id=" + id;
  const receptionistAppointments = "/receptionist/appointments#appointment_id=" + id;
  if (resolution.purpose === "appointment" && resolution.landing_path === patientAppointments) {
    return canPatient;
  }
  if (resolution.purpose === "check_in" && resolution.landing_path === patientCheckin) {
    return canPatient;
  }
  if (resolution.landing_path === receptionistAppointments) {
    return canReceptionist;
  }
  return false;
}

export function ShortLinkLanding({
  api,
  roleHints,
  authState,
  onNavigate,
}: ShortLinkLandingProps) {
  const navigate = useNavigate();
  const [alias, setAlias] = useState<string | null>(pendingAlias);
  const [invalid, setInvalid] = useState(false);
  const [resolution, setResolution] = useState<ShortLinkResolution | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [retryCount, setRetryCount] = useState(0);

  useLayoutEffect(() => {
    const hash = window.location.hash;
    let captured: string | null = null;
    let malformed = false;
    if (hash) {
      const params = new URLSearchParams(hash.slice(1));
      const values = params.getAll("alias");
      captured = params.size === 1 && values.length === 1 ? values[0] : null;
      malformed = !captured || !validAlias(captured);
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname + window.location.search,
      );
    }

    if (malformed) {
      pendingAlias = null;
      setAlias(null);
      setInvalid(true);
      return;
    }
    if (captured && validAlias(captured)) {
      pendingAlias = captured;
      setAlias(captured);
      setInvalid(false);
    } else if (pendingAlias && validAlias(pendingAlias)) {
      setAlias(pendingAlias);
    }
  }, []);

  const canPatient = roleHints.includes("patient");
  const canReceptionist = roleHints.includes("receptionist");
  const allowed = canPatient || canReceptionist;
  const refreshResolution = useCallback(async (requestAlias: string, signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    setResolution(null);
    try {
      const response = await api.requestWithMetadata<ShortLinkResolution>(
        "/s/" + encodeURIComponent(requestAlias),
        {
          method: "GET",
          headers: { Accept: "application/json", "Cache-Control": "no-store" },
          signal,
          referrerPolicy: "no-referrer",
        },
      );
      if (!validateResolution(response.data, canPatient, canReceptionist)) {
        throw new Error("The Appointment service returned an unsupported or unauthorized link destination.");
      }
      setResolution(response.data);
    } catch (requestError) {
      if (!isAbort(requestError)) setError(requestError);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api, canPatient, canReceptionist]);

  useEffect(() => {
    if (!alias || authState !== "authenticated" || !allowed) return;
    const controller = new AbortController();
    void refreshResolution(alias, controller.signal);
    return () => controller.abort();
  }, [alias, authState, allowed, refreshResolution, retryCount]);

  function continueToWorkflow() {
    if (!resolution) return;
    pendingAlias = null;
    if (onNavigate) onNavigate(resolution.landing_path);
    else navigate(resolution.landing_path, { replace: true });
  }

  return (
    <main className="phase4-landing">
      <section className="phase4-panel phase4-landing__card" aria-labelledby="phase4-landing-title">
        <p className="phase4-eyebrow">Appointment service</p>
        <h1 id="phase4-landing-title">Secure appointment link</h1>
        {invalid && <p role="alert">This appointment link is malformed. It has been removed from the address bar. Reopen the original link.</p>}
        {!invalid && !alias && <p role="status">No appointment link is available. Reopen the original message to continue.</p>}
        {alias && authState === "checking" && <p role="status">Checking your sign-in status…</p>}
        {alias && authState === "anonymous" && (
          <div className="phase4-auth-note">
            <p>Sign in as the patient or a receptionist to resolve this link. The alias is held only in this tab’s memory.</p>
            <p>After sign-in, return to this page. If this tab reloads or closes, reopen the original link.</p>
            <Link className="button button--primary" to="/login" state={{ from: "/short-link" }}>Sign in</Link>
          </div>
        )}
        {alias && authState === "authenticated" && !allowed && (
          <p role="alert">This link is available to the patient or reception role. The Appointment service checks access again.</p>
        )}
        {loading && <p role="status">Resolving the appointment link…</p>}
        {error !== null && (
          <AdmissionFeedback
            error={error}
            operationLabel="Appointment link"
            retryLabel="Retry link"
            onRetry={() => setRetryCount((count) => count + 1)}
          />
        )}
        {resolution && (
          <div className="phase4-resolution">
            <p className="phase4-feature-indicator">Navigation only · no check-in credential is issued</p>
            <dl className="phase4-facts">
              <div><dt>Appointment</dt><dd>{resolution.appointment_id}</dd></div>
              <div><dt>Link type</dt><dd>{resolution.purpose === "check_in" ? "Check-in workflow" : "Appointment workflow"}</dd></div>
              <div><dt>Expires</dt><dd>{formatDateTime(resolution.expires_at, { utc: true })}</dd></div>
            </dl>
            <button className="button button--primary" type="button" onClick={continueToWorkflow}>
              Continue to appointment
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
