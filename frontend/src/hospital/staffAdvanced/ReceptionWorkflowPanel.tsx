import { useState } from "react";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/authContext";
import { Facts, Panel, Resource } from "../ui";
import type { CheckinResult, Workflow } from "./contracts";
import { CheckinScanner } from "./CheckinScanner";
import { StaffJourneyTools } from "./JourneyTools";
import { StaffRoleGate } from "./StaffRoleGate";
import {
  errorMessage,
  id,
  idempotencyKey,
  isAmbiguousCommandFailure,
  isConflict,
  scheduleLocalTime,
  validateCheckinToken,
  type ScannedCheckin,
} from "./utils";
import "./staffAdvanced.css";

interface PendingCheckin {
  kind: "token" | "staff";
  appointmentId: string;
  body: { token: string } | { reason: string };
  ifMatch: string;
  key: string;
}

function CheckinPanel() {
  const { api } = useAuth();
  const [appointmentDraft, setAppointmentDraft] = useState("");
  const [appointmentId, setAppointmentId] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [reason, setReason] = useState("");
  const [pendingCommand, setPendingCommand] = useState<PendingCheckin | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [busy, setBusy] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [commandError, setCommandError] = useState("");
  const [receipt, setReceipt] = useState<CheckinResult | null>(null);
  const [reload, setReload] = useState(0);

  function loadAppointment(value = appointmentDraft) {
    try {
      const nextId = id(value);
      setAppointmentId(nextId);
      setAppointmentDraft(nextId);
      setToken("");
      setReason("");
      setReceipt(null);
      setPendingCommand(null);
      setAmbiguous(false);
      setValidationError("");
      setCommandError("");
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : "Enter a valid appointment ID.");
    }
  }

  function acceptScan(scanned: ScannedCheckin) {
    setAppointmentDraft(scanned.appointmentId);
    setToken(scanned.token);
    setAppointmentId(scanned.appointmentId);
    setReason("");
    setReceipt(null);
    setPendingCommand(null);
    setAmbiguous(false);
    setValidationError("");
    setCommandError("");
  }

  function review(kind: PendingCheckin["kind"], workflow: Workflow, etag: string | null) {
    if (workflow.state !== "booked") {
      setValidationError(`This appointment is ${workflow.state}; only a booked workflow can be checked in.`);
      return;
    }
    if (!etag || !/^"[1-9][0-9]*"$/.test(etag)) {
      setValidationError("Reload this workflow to obtain its current version before checking in.");
      return;
    }
    try {
      const body = kind === "token"
        ? { token: validateCheckinToken(token) }
        : (() => {
            const cleanReason = reason.trim();
            if (cleanReason.length < 1 || cleanReason.length > 500) {
              throw new Error("Enter a reason from 1 to 500 characters for the audited staff fallback.");
            }
            return { reason: cleanReason };
          })();
      setPendingCommand({
        kind,
        appointmentId: workflow.appointment_id,
        body,
        ifMatch: etag,
        key: idempotencyKey(),
      });
      setAmbiguous(false);
      setValidationError("");
      setCommandError("");
    } catch (error) {
      setValidationError(error instanceof Error ? error.message : "Check-in details are invalid.");
    }
  }

  async function send(command: PendingCheckin) {
    if (busy) return;
    setBusy(true);
    setCommandError("");
    try {
      const path = command.kind === "token"
        ? `/api/v1/appointments/${command.appointmentId}/check-in`
        : `/api/v1/appointments/${command.appointmentId}/staff-check-in`;
      const result = await api.requestWithMetadata<CheckinResult>(path, {
        method: "POST",
        body: command.body,
        ifMatch: command.ifMatch,
        idempotencyKey: command.key,
      });
      setReceipt(result.data);
      setPendingCommand(null);
      setAmbiguous(false);
      setToken("");
      setReason("");
      setCommandError("");
      setReload((value) => value + 1);
    } catch (error) {
      setCommandError(errorMessage(error));
      if (isConflict(error)) {
        setPendingCommand(null);
        setAmbiguous(false);
        setToken("");
        setReload((value) => value + 1);
      } else if (isAmbiguousCommandFailure(error)) {
        setAmbiguous(true);
      } else {
        setPendingCommand(null);
        setAmbiguous(false);
        setToken("");
      }
      if (error instanceof ApiError && error.status === 403) {
        setPendingCommand(null);
        setAmbiguous(false);
        setToken("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Reception check-in">
      <p>
        Scan the patient's same-origin QR link where browser support is available, or enter the appointment ID and token manually. The Appointment service validates the patient, active appointment window, token and current workflow version.
      </p>
      <CheckinScanner disabled={busy || !!pendingCommand} onScan={acceptScan} />
      <form className="hospital-form" noValidate onSubmit={(event) => { event.preventDefault(); loadAppointment(); }}>
        <label>
          Appointment ID
          <input
            value={appointmentDraft}
            onChange={(event) => {
              const value = event.target.value;
              setAppointmentDraft(value);
              if (appointmentId && value !== appointmentId) {
                setAppointmentId(null);
                setToken("");
                setReason("");
                setReceipt(null);
                setPendingCommand(null);
                setAmbiguous(false);
              }
              setValidationError("");
              setCommandError("");
            }}
            inputMode="numeric"
            autoComplete="off"
            disabled={busy || !!pendingCommand}
          />
        </label>
        <button type="submit" disabled={busy || !!pendingCommand}>Load workflow</button>
      </form>
      {validationError && <p role="alert">{validationError}</p>}
      {appointmentId && (
        <Resource<Workflow>
          path={`/api/v1/appointments/${appointmentId}/workflow`}
          revision={reload}
        >
          {(workflow, etag, refresh) => (
            <div className="staff-advanced-workflow">
              <Facts values={{
                "Appointment ID": workflow.appointment_id,
                "Workflow state": workflow.state,
                "Check-in opens (UTC)": scheduleLocalTime(workflow.checkin_window.starts_at),
                "Check-in closes (UTC)": scheduleLocalTime(workflow.checkin_window.ends_at),
                "Queue entry": workflow.queue_entry_id ?? "Not allocated",
              }} />
              <form className="hospital-form" noValidate onSubmit={(event) => { event.preventDefault(); review("token", workflow, etag); }}>
                <label>
                  Check-in token
                  <input
                    value={token}
                    onChange={(event) => setToken(event.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    maxLength={22}
                    disabled={busy || !!pendingCommand || workflow.state !== "booked"}
                  />
                </label>
                <button type="submit" disabled={busy || !!pendingCommand || workflow.state !== "booked"}>Review token check-in</button>
              </form>
              <form className="hospital-form" noValidate onSubmit={(event) => { event.preventDefault(); review("staff", workflow, etag); }}>
                <label>
                  Audited manual check-in reason
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    maxLength={500}
                    disabled={busy || !!pendingCommand || workflow.state !== "booked"}
                  />
                </label>
                <button type="submit" disabled={busy || !!pendingCommand || workflow.state !== "booked"}>Review staff check-in fallback</button>
              </form>
              {pendingCommand && (
                <div className="hospital-confirm" role="group" aria-label="Confirm check-in">
                  <p>
                    {ambiguous
                      ? "The service outcome is uncertain. Retry this original command with the same key before starting another check-in."
                      : pendingCommand.kind === "token"
                        ? `Confirm token check-in for appointment ${pendingCommand.appointmentId}? The token will not be shown here.`
                        : `Confirm audited staff check-in for appointment ${pendingCommand.appointmentId}?`}
                  </p>
                  <button type="button" disabled={busy} onClick={() => void send(pendingCommand)}>
                    {busy ? "Submitting check-in…" : ambiguous ? "Retry original check-in" : "Confirm check-in"}
                  </button>
                  {!ambiguous && (
                    <button type="button" disabled={busy} onClick={() => { setPendingCommand(null); setValidationError(""); }}>
                      Keep editing
                    </button>
                  )}
                </div>
              )}
              {commandError && <p role="alert">{commandError}</p>}
              {receipt && (
                <div role="status" className="staff-advanced-summary">
                  Check-in confirmed by Appointment. Queue token {receipt.queue_entry.token_number}; queue state {receipt.queue_entry.state}.
                </div>
              )}
              {workflow.state !== "booked" && <p className="staff-advanced-muted">This workflow is not eligible for another check-in. Reload it after any concurrent state change.</p>}
              <button type="button" onClick={() => { refresh(); setReload((value) => value + 1); }} disabled={busy}>Reload workflow</button>
            </div>
          )}
        </Resource>
      )}
    </Panel>
  );
}

export function ReceptionWorkflowPanel() {
  return (
    <StaffRoleGate role="receptionist">
      <div className="staff-advanced-page">
        <CheckinPanel />
        <StaffJourneyTools />
      </div>
    </StaffRoleGate>
  );
}
