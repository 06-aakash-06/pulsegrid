import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../api/client";
import { AdmissionFeedback } from "./AdmissionFeedback";
import { createIdempotencyKey, isCanonicalId, quoteVersion } from "./api";
import type {
  AppointmentShortLinkPanelProps,
  AppointmentWorkflow,
  RevokedShortLink,
  ShortLink,
  ShortLinkPurpose,
} from "./contracts";

interface VisibleShortLink extends ShortLink {
  etag: string;
}

function isAbort(error: unknown): boolean {
  return typeof error === "object" && error !== null && "name" in error && error.name === "AbortError";
}

function validShortPath(path: string): boolean {
  return /^\/s\/[A-Za-z0-9]{22}$/.test(path);
}

function ShortLinkEntry({
  api,
  appointmentId,
  link,
  disabled,
  onRevoked,
}: {
  api: ApiClient;
  appointmentId: string;
  link: VisibleShortLink;
  disabled: boolean;
  onRevoked(): void;
}) {
  const [copyMessage, setCopyMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const url = window.location.origin + link.short_path;

  async function copyLink() {
    setCopyMessage("");
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable.");
      await navigator.clipboard.writeText(url);
      setCopyMessage("Link copied.");
    } catch {
      setCopyMessage("Copy is unavailable here. Select the link above and copy it.");
    }
  }

  async function revoke() {
    setPending(true);
    setError(null);
    try {
      const response = await api.requestWithMetadata<RevokedShortLink>(
        "/api/v1/appointments/" + encodeURIComponent(appointmentId)
          + "/short-links/" + encodeURIComponent(link.id) + "/revoke",
        {
          method: "POST",
          body: {},
          ifMatch: link.etag,
          idempotencyKey: createIdempotencyKey(),
          referrerPolicy: "no-referrer",
        },
      );
      if (response.data.revoked !== true) throw new Error("The appointment service did not confirm link revocation.");
      onRevoked();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setPending(false);
    }
  }

  return (
    <article className="phase4-short-link">
      <div className="phase4-short-link__heading">
        <div>
          <h4>{link.purpose === "check_in" ? "Secure check-in link" : "Appointment link"}</h4>
          <p>Expires {new Date(link.expires_at).toLocaleString()}</p>
        </div>
        <span className="phase4-feature-indicator">Navigation only</span>
      </div>
      <label className="phase4-sr-only" htmlFor={"short-link-" + link.id}>Short link</label>
      <input
        id={"short-link-" + link.id}
        className="phase4-copy-value"
        type="text"
        readOnly
        value={url}
        onFocus={(event) => event.currentTarget.select()}
        aria-describedby={"short-link-help-" + link.id}
      />
      <div className="phase4-action-row">
        <button className="button button--secondary button--small" type="button" disabled={disabled} onClick={() => void copyLink()}>
          Copy link
        </button>
        <button className="button button--secondary button--small" type="button" disabled={disabled || pending} onClick={() => void revoke()}>
          {pending ? "Revoking…" : "Revoke link"}
        </button>
      </div>
      <p className="phase4-inline-status" id={"short-link-help-" + link.id} aria-live="polite">
        {copyMessage || "Opening this link does not authorize check-in or issue a QR credential."}
      </p>
      {error !== null && <AdmissionFeedback error={error} operationLabel="Link revocation" retryLabel="Retry revocation" onRetry={() => void revoke()} />}
    </article>
  );
}

export function AppointmentShortLinkPanel({
  api,
  roleHints,
  appointmentId,
  onWorkflowChanged,
}: AppointmentShortLinkPanelProps) {
  const authorizedHint = roleHints.includes("patient") || roleHints.includes("receptionist");
  const [workflow, setWorkflow] = useState<AppointmentWorkflow | null>(null);
  const [workflowEtag, setWorkflowEtag] = useState<string | null>(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState<unknown>(null);
  const [createError, setCreateError] = useState<unknown>(null);
  const [creating, setCreating] = useState<ShortLinkPurpose | null>(null);
  const [links, setLinks] = useState<VisibleShortLink[]>([]);
  const [statusMessage, setStatusMessage] = useState("");
  const workflowChangedRef = useRef(onWorkflowChanged);
  workflowChangedRef.current = onWorkflowChanged;

  const refreshWorkflow = useCallback(async (signal?: AbortSignal) => {
    if (!isCanonicalId(appointmentId)) {
      setWorkflow(null);
      setWorkflowEtag(null);
      setWorkflowError(new Error("Enter a valid appointment ID to load its current workflow."));
      return;
    }
    setWorkflowLoading(true);
    setWorkflowError(null);
    try {
      const response = await api.requestWithMetadata<AppointmentWorkflow>(
        "/api/v1/appointments/" + encodeURIComponent(appointmentId) + "/workflow",
        { method: "GET", signal, referrerPolicy: "no-referrer" },
      );
      if (
        response.data.appointment_id !== appointmentId
        || !Number.isSafeInteger(response.data.version)
        || typeof response.data.state !== "string"
      ) {
        throw new Error("The appointment service returned an unsupported workflow response.");
      }
      setWorkflow(response.data);
      setWorkflowEtag(response.etag || quoteVersion(response.data.version));
      workflowChangedRef.current?.(response.data);
    } catch (requestError) {
      if (!isAbort(requestError)) setWorkflowError(requestError);
    } finally {
      if (!signal?.aborted) setWorkflowLoading(false);
    }
  }, [api, appointmentId]);

  useEffect(() => {
    if (!authorizedHint) return;
    const controller = new AbortController();
    void refreshWorkflow(controller.signal);
    return () => controller.abort();
  }, [authorizedHint, refreshWorkflow]);

  if (!authorizedHint) {
    return (
      <section className="phase4-panel" aria-label="Appointment links">
        <p role="status">Appointment links are available to the patient and reception roles. The Appointment service verifies current access.</p>
      </section>
    );
  }

  async function createLink(purpose: ShortLinkPurpose) {
    if (!workflowEtag || !workflow) {
      await refreshWorkflow();
      return;
    }
    setCreating(purpose);
    setCreateError(null);
    setStatusMessage("");
    try {
      const response = await api.requestWithMetadata<ShortLink>(
        "/api/v1/appointments/" + encodeURIComponent(appointmentId) + "/short-links",
        {
          method: "POST",
          body: { purpose },
          ifMatch: workflowEtag,
          idempotencyKey: createIdempotencyKey(),
          referrerPolicy: "no-referrer",
        },
      );
      if (
        response.data.appointment_id !== appointmentId
        || response.data.purpose !== purpose
        || !isCanonicalId(response.data.id)
        || !validShortPath(response.data.short_path)
        || !Number.isSafeInteger(response.data.version)
        || !Number.isFinite(Date.parse(response.data.expires_at))
      ) {
        throw new Error("The appointment service returned an unsupported short-link response.");
      }
      const next: VisibleShortLink = {
        ...response.data,
        etag: response.etag || quoteVersion(response.data.version),
      };
      setLinks((current) => [next, ...current.filter((link) => link.purpose !== purpose)]);
      setStatusMessage(purpose === "check_in" ? "Secure check-in link created." : "Appointment link created.");
    } catch (requestError) {
      setCreateError(requestError);
    } finally {
      setCreating(null);
    }
  }

  return (
    <section className="phase4-panel" aria-labelledby="phase4-short-links-heading">
      <div className="phase4-panel__heading">
        <div>
          <p className="phase4-eyebrow">Appointment service</p>
          <h3 id="phase4-short-links-heading">Share a short link</h3>
        </div>
        <span className="phase4-feature-indicator">Secure navigation</span>
      </div>
      <p className="phase4-panel__description">
        These links open the authorized appointment workflow. A check-in link never checks a patient in or issues a QR credential.
      </p>
      {workflowLoading && <p role="status">Loading the current appointment workflow…</p>}
      {workflowError !== null && (
        <AdmissionFeedback
          error={workflowError}
          operationLabel="Appointment status"
          retryLabel="Retry appointment status"
          onRetry={() => void refreshWorkflow()}
        />
      )}
      {workflow && <p className="phase4-muted">Current workflow status: <strong>{workflow.state.replaceAll("_", " ")}</strong></p>}
      {createError !== null && (
        <AdmissionFeedback
          error={createError}
          operationLabel="Short-link request"
          retryLabel="Refresh appointment status"
          onRetry={() => void refreshWorkflow()}
        />
      )}
      {statusMessage && <p className="phase4-success" role="status">{statusMessage}</p>}
      <div className="phase4-action-row">
        <button
          className="button button--secondary"
          type="button"
          disabled={workflowLoading || creating !== null || !workflow || !workflowEtag || !isCanonicalId(appointmentId)}
          onClick={() => void createLink("appointment")}
        >
          {creating === "appointment" ? "Creating…" : "Create appointment link"}
        </button>
        <button
          className="button button--secondary"
          type="button"
          disabled={workflowLoading || creating !== null || !workflow || !workflowEtag || !isCanonicalId(appointmentId) || workflow.state !== "booked"}
          onClick={() => void createLink("check_in")}
        >
          {creating === "check_in" ? "Creating…" : "Create secure check-in link"}
        </button>
        <button
          className="phase4-text-button"
          type="button"
          disabled={workflowLoading || creating !== null}
          onClick={() => void refreshWorkflow()}
        >
          Refresh status
        </button>
      </div>
      {!workflowLoading && workflow && workflow.state !== "booked" && (
        <p className="phase4-inline-status">A check-in link is available after Appointment reports the workflow as booked.</p>
      )}
      {!workflowLoading && workflow && links.length === 0 && (
        <p className="phase4-empty">No short links have been created in this view yet.</p>
      )}
      {links.length > 0 && (
        <div className="phase4-short-links">
          {links.map((link) => (
            <ShortLinkEntry
              api={api}
              appointmentId={appointmentId}
              disabled={creating !== null}
              key={link.id}
              link={link}
              onRevoked={() => {
                setLinks((current) => current.filter((item) => item.id !== link.id));
                setStatusMessage("Link revoked.");
              }}
            />
          ))}
        </div>
      )}
    </section>
  );
}
