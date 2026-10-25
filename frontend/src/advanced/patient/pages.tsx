import { AdvancedLookup, ItemDetails, PageRefresh } from "../../components/PageTools";
import { useLocalDemo } from "../../design/localDemo";
import { lazy, Suspense } from "react";
import { DepartmentIcon } from "../../design/DepartmentIcon";
const PatientScanner = lazy(() => import("../../hospital/staffAdvanced/CheckinScanner").then(m=>({default:m.CheckinScanner})));
import { WorkflowHistory } from "../shared/WorkflowHistory";
import { CheckinQr } from "../shared/CheckinQr";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import {
  buildQuery,
  formatTime,
  getErrorMessage,
  idempotencyRecovery,
  isId,
  newIdempotencyKey,
  parseId,
  parseVersion,
  sendCommand,
} from "./api";
import {
  PatientGate,
  useLoad,
  usePagedItems,
  usePatientAccess,
  usePolling,
} from "./hooks";
import type {
  Appointment,
  CheckinResult,
  Journey,
  JourneyStage,
  OwnQueue,
  PatientProfile,
  TokenIssue,
  Waitlist,
  WaitlistSlot,
  Workflow,
} from "./contracts";
import "./patient.css";

const workflowLabels: Record<Workflow["state"], string> = {
  booked: "Waiting for check-in",
  checked_in: "Checked in",
  in_consultation: "In consultation",
  completed: "Visit completed",
  cancelled: "Cancelled",
  no_show: "Marked as no-show",
};
function RetryButton({ onClick, disabled = false }: { onClick: () => void; disabled?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled}>Retry</button>;
}
function WaitlistCount({
  api,
  slotId,
}: {
  api: ReturnType<typeof usePatientAccess>["api"];
  slotId: string;
}) {
  const count = useLoad<WaitlistSlot>(api, `/api/v1/appointments/waitlist-slots/${slotId}`, true);
  if (count.loading) return <p>Loading current slot count…</p>;
  if (count.error) return <p className="patient-workflow__muted">Current slot count is unavailable. <RetryButton onClick={count.reload} /></p>;
  if (!count.data) return null;
  return <p>
    {count.data.waiting_count} {count.data.waiting_count === 1 ? "patient is" : "patients are"} waiting on this slot.
    {count.data.promotion_pending ? " Promotion is pending service recovery." : ""}
    <span className="patient-workflow__meta"> Count observed {formatTime(count.data.observed_at)}.</span>
  </p>;
}

export function PatientWaitlistPage() {
  const { api, gate } = usePatientAccess();
  const profile = useLoad<PatientProfile>(api, gate === "ready" ? "/api/v1/patients/me" : null, gate === "ready");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [joinPending, setJoinPending] = useState(false);
  const [joinNotice, setJoinNotice] = useState<string | null>(null);
  const [slotId, setSlotId] = useState("");
  const [scheduleRevision, setScheduleRevision] = useState("");
  const [listActionError, setListActionError] = useState<string | null>(null);
  const [pageLoading, setPageLoading] = useState(false);
  const list = usePagedItems<Waitlist>(
    api,
    profile.data ? buildQuery("/api/v1/appointments/waitlists",{patient_id:profile.data.id,limit:"20"}) : null,
    gate === "ready" && !!profile.data,
  );

  async function join(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJoinError(null);
    setJoinNotice(null);
    let body: { patient_id: string; slot_id: string; expected_schedule_revision: number };
    try {
      const patientResponse = await api.requestWithMetadata<PatientProfile>("/api/v1/patients/me");
      body = {
        patient_id: parseId(patientResponse.data.id, "Patient ID"),
        slot_id: parseId(slotId, "Slot ID"),
        expected_schedule_revision: parseVersion(scheduleRevision, "Accepted schedule revision"),
      };
    } catch (error) {
      setJoinError(getErrorMessage(error));
      return;
    }
    setJoinPending(true);
    try {
      const result = await sendCommand<Waitlist>(api, "/api/v1/appointments/waitlists", body);
      setJoinNotice(`You joined the waitlist. Status: ${result.data.state}.`);
      setSlotId("");
      setScheduleRevision("");
      list.reload();
    } catch (error) {
      if (error instanceof ApiError && error.code === "slot_available") {
        setJoinError("This slot is available now. Book it from Appointments instead.");
      } else if (error instanceof ApiError && error.code === "already_waiting") {
        setJoinError("You already have an active waitlist entry for this slot. Reload your list to see it.");
      } else if (error instanceof ApiError && error.code === "schedule_changed") {
        setJoinError("The accepted schedule changed. Check the latest slot details before trying again.");
      } else {
        setJoinError(getErrorMessage(error));
      }
    } finally {
      setJoinPending(false);
    }
  }

  async function withdraw(entry: Waitlist, reason: string) {
    setListActionError(null);
    const normalizedReason = reason.trim();
    if (normalizedReason.length < 1 || normalizedReason.length > 500) {
      setListActionError("Withdrawal reason must contain 1 to 500 characters.");
      return;
    }
    setPageLoading(true);
    try {
      const current = await api.requestWithMetadata<Waitlist>(`/api/v1/appointments/waitlists/${entry.id}`);
      if (!current.etag) throw new Error("The waitlist entry did not include its required version. Reload before withdrawing.");
      await sendCommand<Waitlist>(
        api,
        `/api/v1/appointments/waitlists/${entry.id}/withdraw`,
        { reason: normalizedReason },
        { ifMatch: current.etag },
      );
      list.reload();
    } catch (error) {
      setListActionError(getErrorMessage(error));
    } finally {
      setPageLoading(false);
    }
  }

  if (gate !== "ready") return <PatientGate state={gate} />;
  return (
    <div className="patient-workflow waitlist-register">
      <p>Check <Link to="/patient/appointments">Appointments</Link> for an available slot first. For a booked-out slot, ask reception for a waitlist reference and use Advanced lookup.</p>
      <AdvancedLookup title="Join a waitlist using a slot reference">      <section className="patient-workflow__panel" aria-labelledby="waitlist-join-title">
        <h2 id="waitlist-join-title">Join a waitlist</h2>
        <p>Waitlists accept an occupied future slot. Free slots return an availability conflict; use <Link to="/patient/appointments">Appointments</Link> to book those.</p>
        <p>Enter the slot ID and accepted schedule revision supplied for the slot. The current patient ID is read from your authenticated profile.</p>
        <form onSubmit={(event) => void join(event)} noValidate>
          <label htmlFor="patient-waitlist-slot">Slot ID</label>
          <input id="patient-waitlist-slot" inputMode="numeric" value={slotId} onChange={(event) => setSlotId(event.target.value)} aria-describedby="patient-waitlist-slot-help" />
          <span id="patient-waitlist-slot-help" className="patient-workflow__hint">Enter the slot reference supplied by reception.</span>
          <label htmlFor="patient-waitlist-revision">Accepted schedule revision</label>
          <input id="patient-waitlist-revision" inputMode="numeric" value={scheduleRevision} onChange={(event) => setScheduleRevision(event.target.value)} />
          <button type="submit" disabled={joinPending}>{joinPending ? "Joining…" : "Join waitlist"}</button>
        </form>
        {joinError && <p role="alert">{joinError}</p>}
        {joinNotice && <p role="status">{joinNotice}</p>}
      </section>

</AdvancedLookup>
      <section className="patient-workflow__panel" aria-labelledby="waitlist-list-title">
        <h2 id="waitlist-list-title">Your waitlist entries</h2>
        {profile.loading&&<p role="status">Loading your patient profile…</p>}
        {profile.error&&<div role="alert">{profile.error}<RetryButton onClick={profile.reload}/></div>}
        {list.loading && <p role="status">Loading your waitlist entries…</p>}
        {list.error && <div role="alert"><p>{list.error}</p><RetryButton onClick={list.reload} /></div>}
        {!!profile.data && !list.loading && !list.error && list.items.length === 0 && <p>No waitlist entries were returned for this patient.</p>}
        {list.items.map((entry) => (
          <article className="patient-workflow__item" key={entry.id}>
            <h3>Waitlist request</h3><ItemDetails>Entry {entry.id} · Slot {entry.slot_id}</ItemDetails>
            <dl className="patient-workflow__facts">

              <div><dt>State</dt><dd>{entry.state}</dd></div>
              <div><dt>Joined</dt><dd><time dateTime={entry.joined_at}>{formatTime(entry.joined_at)}</time></dd></div>
              {entry.promoted_appointment_id && <div><dt>Appointment</dt><dd>Confirmed</dd></div>}
              {entry.skip_reason && <div><dt>Skip reason</dt><dd>{entry.skip_reason}</dd></div>}
            </dl>
            {entry.state === "waiting" && <>
              <WaitlistCount api={api} slotId={entry.slot_id} />
              <p className="patient-workflow__muted">Your exact position is not available.</p>
              <label htmlFor={`waitlist-reason-${entry.id}`}>Reason to withdraw</label>
              <input id={`waitlist-reason-${entry.id}`} maxLength={500} placeholder="I no longer need this waitlist entry." />
              <button type="button" disabled={pageLoading} onClick={() => {
                const input = document.getElementById(`waitlist-reason-${entry.id}`) as HTMLInputElement | null;
                void withdraw(entry, input?.value ?? "");
              }}>Withdraw entry</button>
            </>}
            {entry.state === "promoted" && <p role="status">Your appointment is confirmed. Find it in Appointments.</p>}
          </article>
        ))}
        {listActionError && <p role="alert">{listActionError}</p>}
        {list.nextCursor && <button type="button" disabled={list.loadingMore} onClick={() => void list.loadMore()}>{list.loadingMore ? "Loading…" : "Load more entries"}</button>}
        {list.loadMoreError && <div role="alert"><p>{list.loadMoreError}</p><button type="button" onClick={() => void list.loadMore()}>Retry loading entries</button></div>}
        <PageRefresh type="button" onClick={list.reload}>Refresh waitlists</PageRefresh>
      </section>
    </div>
  );
}

interface LandingToken {
  appointmentId: string;
  token: string;
}

function readLandingFragment(): { value: LandingToken | null; invalid: boolean } {
  const fragment = window.location.hash;
  if (!fragment) return { value: null, invalid: false };
  const params = new URLSearchParams(fragment.slice(1));
  const appointmentIds = params.getAll("appointment_id");
  const tokens = params.getAll("token");
  const keys = Array.from(params.keys());
  const value = keys.length === 2 && keys.includes("appointment_id") && keys.includes("token") &&
    appointmentIds.length === 1 && tokens.length === 1 &&
    isId(appointmentIds[0]) && /^[A-Za-z0-9]{22}$/.test(tokens[0])
    ? { appointmentId: appointmentIds[0], token: tokens[0] }
    : null;
  return { value, invalid: value === null };
}

function safeLandingUrl(issue: TokenIssue): string | null {
  const expected = `/patient/check-in#appointment_id=${issue.appointment_id}&token=${issue.token}`;
  if (issue.landing_path !== expected) return null;
  const url = new URL(issue.landing_path, window.location.origin);
  if (url.origin !== window.location.origin || url.pathname !== "/patient/check-in" || url.search) return null;
  return url.toString();
}

export function PatientCheckinPage({
  renderQr,
}: {
  renderQr?: (sameOriginUrl: string) => ReactNode;
} = {}) {
  const demo = useLocalDemo();
  const [manualMode,setManualMode]=useState(false);
  const { api, gate } = usePatientAccess();
  const [landing, setLanding] = useState<LandingToken | null>(null);
  const [invalidLanding, setInvalidLanding] = useState(false);
  const [appointmentId, setAppointmentId] = useState("");
  const [manualToken, setManualToken] = useState("");
  const [issue, setIssue] = useState<TokenIssue | null>(null);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [issuePending, setIssuePending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmPending, setConfirmPending] = useState(false);
  const [result, setResult] = useState<CheckinResult | null>(null);
  const [confirmationKey, setConfirmationKey] = useState<string | null>(null);
  useLayoutEffect(() => {
    const fragment = readLandingFragment();
    if (window.location.hash) window.history.replaceState(null, "", "/patient/check-in");
    setLanding(fragment.value);
    setInvalidLanding(fragment.invalid);
    if (fragment.value) {
      setAppointmentId(fragment.value.appointmentId);
      setManualToken(fragment.value.token);
    }
  }, []);

  useEffect(() => {
    if (gate === "anonymous" || gate === "forbidden") {
      setLanding(null);
      setManualToken("");
      setIssue(null);
      setConfirmationKey(null);
    }
  }, [gate]);

  useEffect(() => {
    const clearSecret = () => {
      setLanding(null);
      setManualToken("");
      setIssue(null);
      setConfirmationKey(null);
    };
    window.addEventListener("pagehide", clearSecret);
    return () => window.removeEventListener("pagehide", clearSecret);
  }, []);

  const appointment = isId(appointmentId) ? appointmentId : "";
  const workflow = useLoad<Workflow>(api, gate === "ready" && appointment ? `/api/v1/appointments/${appointment}/workflow` : null, gate === "ready" && !!appointment);
  const profile = useLoad<PatientProfile>(api, gate === "ready" ? "/api/v1/patients/me" : null, gate === "ready");
  const appointmentsPath = profile.data
    ? buildQuery("/api/v1/appointments", { patient_id: profile.data.id, limit: "20" })
    : null;
  const appointments = usePagedItems<Appointment>(api, appointmentsPath, gate === "ready" && !!profile.data);
  const ownAppointments = appointments.items.filter((item) => item.state === "confirmed");
  const selectedAppointment = ownAppointments.find((item) => item.id === appointment);

  async function issueLink() {
    if (!appointment || !workflow.etag) {
      setIssueError("Load your current workflow version before requesting a check-in link.");
      return;
    }
    setIssueError(null);
    setActionError(null);
    setResult(null);
    setIssue(null);
    setIssuePending(true);
    try {
      const created = await sendCommand<TokenIssue>(
        api,
        `/api/v1/appointments/${appointment}/check-in-links`,
        {},
        { ifMatch: workflow.etag },
      );
      if (created.data.appointment_id !== appointment || !/^[A-Za-z0-9]{22}$/.test(created.data.token) || !safeLandingUrl(created.data)) {
        setIssueError("The service returned a check-in link that does not match the frozen contract. No link is displayed.");
        return;
      }
      setIssue(created.data);
      setManualToken(created.data.token);
      workflow.reload();
    } catch (error) {
      setIssueError(`${getErrorMessage(error)} If the first response was lost, request a new link explicitly; the service may have revoked the prior link.`);
    } finally {
      setIssuePending(false);
    }
  }

  async function confirmCheckin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setActionError(null);
    setResult(null);
    if (!appointment) {
      setActionError("Enter a valid appointment ID.");
      return;
    }
    if (!/^[A-Za-z0-9]{22}$/.test(manualToken.trim())) {
      setActionError("Enter the 22-character check-in code, or get a new code above.");
      return;
    }
    if (!workflow.etag) {
      setActionError("The latest workflow version is unavailable. Reload it before confirming check-in.");
      return;
    }
    setConfirmPending(true);
    let key: string;
    try {
      key = confirmationKey ?? newIdempotencyKey();
    } catch (error) {
      setActionError(getErrorMessage(error));
      setConfirmPending(false);
      return;
    }
    setConfirmationKey(key);
    try {
      const confirmed = await sendCommand<CheckinResult>(
        api,
        `/api/v1/appointments/${appointment}/check-in`,
        { token: manualToken.trim() },
        { ifMatch: workflow.etag },
        key,
      );
      setResult(confirmed.data);
      setLanding(null);
      setManualToken("");
      setIssue(null);
      setConfirmationKey(null);
      workflow.reload();
    } catch (error) {
      if (idempotencyRecovery(error)) {
        setActionError(`${getErrorMessage(error)} Check-in was not confirmed in this view. Retry with the same request key to recover the saved result.`);
      } else {
        setConfirmationKey(null);
        if (error instanceof ApiError && error.code === "token_invalid") {
          setLanding(null);
          setManualToken("");
          setIssue(null);
          setActionError("This QR or token is invalid, expired, consumed, or revoked. No check-in was confirmed. Request a new link.");
        } else if (error instanceof ApiError && error.code === "checkin_window_closed") {
          setActionError("The service reports that the check-in window is closed. No check-in was confirmed.");
        } else {
          setActionError(getErrorMessage(error));
        }
      }
    } finally {
      setConfirmPending(false);
    }
  }

  if (gate !== "ready") return <PatientGate state={gate} />;
  const activeIssueUrl = issue ? safeLandingUrl(issue) : null;
  const manualOpen = manualMode || !!appointmentId;
  return (
    <div className="patient-workflow waiting-station">
      <aside className="checkin-kiosk"><h2>Check In Here</h2><p>Scan your secure QR code.</p><div className="scanner-frame"><Suspense fallback={<p role="status">Loading scanner…</p>}><PatientScanner disabled={confirmPending || issuePending} onScan={scan=>{setAppointmentId(scan.appointmentId);setManualToken(scan.token);setLanding(null);setInvalidLanding(false);setIssue(null);setActionError(null);setConfirmationKey(null);setResult(null);}}/></Suspense></div><button type="button" onClick={()=>setManualMode(true)}>Check in manually</button></aside>
      <details id="manual-checkin" className="patient-workflow__panel" open={manualOpen || undefined}><summary>Check in manually</summary><section aria-labelledby="checkin-title">
        <h2 id="checkin-title">Secure QR check-in</h2>
        <p>Opening a QR link never checks you in. Confirm below to send the authenticated check-in command.</p>
        {landing && <p role="status">QR link received for appointment {landing.appointmentId}. Verify the appointment and confirm check-in below.</p>}
        {invalidLanding && <p role="alert">The check-in QR fragment is malformed. It was removed from the address bar. Select your appointment and request a new link.</p>}
        {profile.loading && <p role="status">Loading your patient profile…</p>}
        {profile.error && <div role="alert"><p>{profile.error}</p><RetryButton onClick={profile.reload} /></div>}
        {appointments.loading && <p role="status">Loading your appointments…</p>}
        {appointments.error && <div role="alert"><p>{appointments.error}</p><RetryButton onClick={appointments.reload} /></div>}
        {ownAppointments.length > 0 && <label htmlFor="checkin-appointment-select">Choose a confirmed appointment</label>}
        {ownAppointments.length > 0 && <select id="checkin-appointment-select" value={appointmentId} onChange={(event) => {
          setAppointmentId(event.target.value);
          setManualToken("");
          setLanding(null);
          setInvalidLanding(false);
          setIssue(null);
          setActionError(null);
          setConfirmationKey(null);
        }}>
          <option value="">Select an appointment</option>
          {ownAppointments.map((item) => <option key={item.id} value={item.id}>{demo?.appointments[item.id]?.label??"Appointment"} — {formatTime(item.starts_at)}</option>)}
        </select>}
        {appointments.nextCursor && <button type="button" disabled={appointments.loadingMore} onClick={() => void appointments.loadMore()}>{appointments.loadingMore ? "Loading appointments…" : "Load more appointments"}</button>}
        {appointments.loadMoreError && <div role="alert"><p>{appointments.loadMoreError}</p><button type="button" onClick={() => void appointments.loadMore()}>Retry loading appointments</button></div>}
        <AdvancedLookup title="Check-in reference">        <label htmlFor="checkin-appointment-id">Appointment ID</label>
        <input id="checkin-appointment-id" inputMode="numeric" value={appointmentId} onChange={(event) => {
          setAppointmentId(event.target.value);
          setManualToken("");
          setLanding(null);
          setInvalidLanding(false);
          setIssue(null);
          setActionError(null);
          setConfirmationKey(null);
        }} aria-describedby="checkin-appointment-help" />
        <span id="checkin-appointment-help" className="patient-workflow__hint">Use a reference from your confirmed appointments.</span></AdvancedLookup>
        {workflow.loading && appointment && <p role="status">Loading current check-in status…</p>}
        {workflow.error && appointment && (workflow.notFound
          ? <p className="patient-workflow__calm" role="status">Check-in opens on the day of your appointment{selectedAppointment ? ` (${formatTime(selectedAppointment.starts_at)})` : ""}. Come back then to check in here.</p>
          : <div role="alert"><p>{workflow.error}</p><RetryButton onClick={workflow.reload} /></div>)}
        {workflow.data && <dl className="patient-workflow__facts">
          <div><dt>Status</dt><dd>{workflowLabels[workflow.data.state]}</dd></div>
          <div><dt>Check-in opens</dt><dd><time dateTime={workflow.data.checkin_window.starts_at}>{formatTime(workflow.data.checkin_window.starts_at)}</time></dd></div>
          <div><dt>Check-in closes</dt><dd><time dateTime={workflow.data.checkin_window.ends_at}>{formatTime(workflow.data.checkin_window.ends_at)}</time></dd></div>
        </dl>}
        {(result || (workflow.data && workflow.data.state !== "booked")) ? (
          <div className="patient-workflow__done" role="status">
            <h3>{result || workflow.data?.state === "checked_in" ? "You're checked in" : workflowLabels[workflow.data!.state]}</h3>
            {result && <p>Your queue token is <strong>{result.queue_entry.token_number}</strong>.</p>}
            {(result || workflow.data?.state === "checked_in" || workflow.data?.state === "in_consultation") && <Link className="button" to="/patient/queue">Follow your place in the Waiting Room →</Link>}
          </div>
        ) : workflow.data?.state === "booked" && <>
          <div className="patient-workflow__step">
            <p>No QR to scan? Ask for a one-time check-in code for this appointment, then confirm below.</p>
            <button type="button" disabled={issuePending || workflow.loading || !workflow.etag} onClick={() => void issueLink()}>{issuePending ? "Requesting code…" : issue ? "Issue a new check-in code" : "Get a check-in code"}</button>
          </div>
          {issueError && <div role="alert"><p>{issueError}</p><button type="button" disabled={issuePending} onClick={() => void issueLink()}>Request a new code</button></div>}
          {issue && activeIssueUrl && <details className="patient-workflow__item" aria-label="Check-in link receipt">
            <summary>Show this code as a QR</summary>
            <p>Expires at <time dateTime={issue.expires_at}>{formatTime(issue.expires_at)}</time>. Reissuing revokes unused codes.</p>
            <div className="patient-workflow__qr" aria-label="Check-in QR display">
              {renderQr ? renderQr(activeIssueUrl) : <CheckinQr value={activeIssueUrl} />}
            </div>
            <label htmlFor="checkin-landing-url">Secure same-origin landing URL</label>
            <input id="checkin-landing-url" readOnly value={activeIssueUrl} onFocus={(event) => event.currentTarget.select()} />
            <p className="patient-workflow__muted">The code is not saved in browser storage and is cleared on logout or page exit.</p>
          </details>}
          {actionError && <p role="alert">{actionError}</p>}
          <form onSubmit={(event) => void confirmCheckin(event)} noValidate>
            <label htmlFor="checkin-token-input">Check-in code</label>
            <input id="checkin-token-input" autoComplete="off" value={manualToken} placeholder="22 letters and digits, e.g. aB3dE5fG7hJ9kL1mN3pQ5r" aria-describedby="checkin-token-help" onChange={(event) => {
              setManualToken(event.target.value);
              setConfirmationKey(null);
            }} maxLength={22} />
            <span id="checkin-token-help" className="patient-workflow__hint">Filled in for you when you scan a QR or get a code above.</span>
            <button type="submit" disabled={confirmPending || workflow.loading || !workflow.etag}>{confirmPending ? "Confirming…" : confirmationKey ? "Retry check-in confirmation" : "Confirm check-in"}</button>
          </form>
        </>}
      </section></details>
    </div>
  );
}

interface QueueSnapshot {
  queue: OwnQueue | null;
  workflow: Workflow | null;
}

async function fetchQueueSnapshot(
  api: ReturnType<typeof usePatientAccess>["api"],
  appointmentId: string,
  signal: AbortSignal,
): Promise<QueueSnapshot> {
  async function optional<T>(path: string) {
    try {
      return (await api.requestWithMetadata<T>(path, { signal })).data;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }
  const [queue, workflow] = await Promise.all([
    optional<OwnQueue>(`/api/v1/appointments/${appointmentId}/queue`),
    optional<Workflow>(`/api/v1/appointments/${appointmentId}/workflow`),
  ]);
  return { queue, workflow };
}

function mergeQueueSnapshot(current: QueueSnapshot | null, incoming: QueueSnapshot): QueueSnapshot {
  if (!current) return incoming;
  const queue = incoming.queue && current.queue &&
    incoming.queue.queue_version < current.queue.queue_version
    ? current.queue
    : incoming.queue;
  const workflow = incoming.workflow && current.workflow &&
    incoming.workflow.version < current.workflow.version
    ? current.workflow
    : incoming.workflow;
  return { queue, workflow };
}

export function PatientQueuePage() {
  const navigate = useNavigate();
  const demo=useLocalDemo();
  const { api, gate, sessionKey } = usePatientAccess();
  const profile = useLoad<PatientProfile>(api, gate === "ready" ? "/api/v1/patients/me" : null, gate === "ready");
  const appointmentsPath = profile.data
    ? buildQuery("/api/v1/appointments", { patient_id: profile.data.id, limit: "20" })
    : null;
  const appointments = usePagedItems<Appointment>(api, appointmentsPath, gate === "ready" && !!profile.data);
  const [selectedId, setSelectedId] = useState("");
  const confirmed = appointments.items.filter((item) => item.state === "confirmed");
  useEffect(() => {
    if (!selectedId && confirmed[0]) setSelectedId(confirmed[0].id);
    if (selectedId && !confirmed.some((item) => item.id === selectedId)) setSelectedId("");
  }, [confirmed, selectedId]);
  const poll = useCallback((signal: AbortSignal) => fetchQueueSnapshot(api, selectedId, signal), [api, selectedId]);
  const live = usePolling<QueueSnapshot>(api, `${sessionKey}:${selectedId}`, gate === "ready" && isId(selectedId), poll, 5000, mergeQueueSnapshot);

  if (gate !== "ready") return <PatientGate state={gate} />;
  return <div className="patient-workflow waiting-station queue-station"><aside className="checkin-kiosk"><h2>Check In Here</h2><p>Scan your secure QR code.</p><div className="scanner-frame"><Suspense fallback={<p role="status">Loading scanner…</p>}><PatientScanner onScan={scan=>navigate(`/patient/check-in#${new URLSearchParams({appointment_id:scan.appointmentId,token:scan.token})}`)}/></Suspense></div><Link className="text-link" to="/patient/check-in">Manual check-in →</Link><div className="kiosk-brand"><DepartmentIcon department="waiting"/><strong>PulseGrid</strong><small>Patient check-in</small></div><Link className="text-link" to="/patient/waitlist">View waitlist →</Link></aside>
    <section className="patient-workflow__panel queue-monitor" aria-label="Your consultation queue">
      <header className="queue-monitor-heading"><DepartmentIcon department="waiting"/><h2 id="patient-queue-title">Live Queue</h2><span>{live.error ? "Unavailable" : live.stale ? "Reconnecting" : live.data?.queue ? "Live" : "Your visit"}</span></header>
      {appointments.loading && <p role="status">Loading your appointments…</p>}
      {appointments.error && <div role="alert"><p>{appointments.error}</p><RetryButton onClick={appointments.reload} /></div>}
      {confirmed.length > 0 && <>
        <label htmlFor="patient-queue-appointment">Appointment</label>
        <select id="patient-queue-appointment" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          {confirmed.map((item) => <option key={item.id} value={item.id}>{demo?.appointments[item.id]?.label??"Appointment"} — {formatTime(item.starts_at)}</option>)}
        </select>
      </>}
      {appointments.nextCursor && <button type="button" disabled={appointments.loadingMore} onClick={() => void appointments.loadMore()}>{appointments.loadingMore ? "Loading appointments…" : "Load more appointments"}</button>}
      {appointments.loadMoreError && <div role="alert"><p>{appointments.loadMoreError}</p><button type="button" onClick={() => void appointments.loadMore()}>Retry loading appointments</button></div>}
      {!appointments.loading && !appointments.error && confirmed.length === 0 && <p>No confirmed appointments were returned for queue tracking.</p>}
      {live.loading && !live.data && <p role="status">Connecting to your queue…</p>}
      {profile.loading && <p role="status">Loading your patient profile…</p>}
      {live.error && <div role="alert"><p>{live.error}</p>{live.stopped ? <p>Polling stopped because the service denied access. Check the signed-in account and reload this page after access is corrected.</p> : <button type="button" onClick={live.retryNow}>Reconnect now</button>}</div>}
      {live.stale && live.data && <p className="patient-workflow__stale" role="status">Queue data is stale. Reconnecting; last successful refresh was {live.lastSuccessAt ? formatTime(new Date(live.lastSuccessAt).toISOString()) : "not reported"}.</p>}
      {live.data?.queue && <>
        <div className="queue-wall-table"><table><caption>Live Queue · Your consultation</caption><thead><tr><th scope="col">Your token</th><th scope="col">Position</th><th scope="col">Status</th></tr></thead><tbody><tr><td><strong className="queue-token-number">{live.data.queue.entry.token_number}</strong></td><td>{live.data.queue.entry.position??'—'}</td><td><span className="owner-state">{live.data.queue.entry.state.replaceAll('_',' ')}</span></td></tr></tbody></table></div>
        <div className="queue-count-strip"><span><strong>{live.data.queue.waiting_count}</strong> Waiting</span><span><strong>{live.data.queue.in_consultation_count}</strong> In consultation</span></div>
        <details className="queue-source-details"><summary>Queue details and freshness</summary>
        <dl className="patient-workflow__facts">
          <div><dt>Queue token</dt><dd>{live.data.queue.entry.token_number}</dd></div>
          <div><dt>Your position</dt><dd>{live.data.queue.entry.position ?? "Not currently waiting"}</dd></div>
          <div><dt>Queue status</dt><dd>{live.data.queue.entry.state.replaceAll("_", " ")}</dd></div>
          <div><dt>Waiting count</dt><dd>{live.data.queue.waiting_count}</dd></div>
          <div><dt>In consultation</dt><dd>{live.data.queue.in_consultation_count}</dd></div>
          <div><dt>Queue snapshot version</dt><dd>{live.data.queue.queue_version}</dd></div>
          <div><dt>Backend observed at</dt><dd><time dateTime={live.data.queue.observed_at}>{formatTime(live.data.queue.observed_at)}</time></dd></div>
        </dl>
        <p>Queue status updates are polled every five seconds while this page is visible. Other patients’ identities are never requested or shown.</p></details>
      </>}
      {live.data && !live.data.queue && <p role="status">The service has not returned a queue entry for this appointment. Check-in may still be pending, or the appointment may not be enrolled in Phase 3.</p>}
      {live.data?.workflow && <p>Visit status: <strong>{workflowLabels[live.data.workflow.state]}</strong></p>}
      {live.data && !live.data.workflow && <p className="patient-workflow__muted">Check-in opens on the day of your appointment.</p>}
      {!live.error && selectedId && <PageRefresh type="button" onClick={live.retryNow}>Refresh queue now</PageRefresh>}
      <footer className="queue-monitor-footer"><span>PulseGrid · Consultation queue</span>{live.data?.queue && <time dateTime={live.data.queue.observed_at}>Observed {formatTime(live.data.queue.observed_at)}</time>}</footer>
    </section>
    <aside className="queue-wait-sign"><header><DepartmentIcon department="waiting"/><h2>Your Turn</h2></header><div className="waiting-position-display"><small>QUEUE POSITION</small><strong>{live.data?.queue?.entry.position??'—'}</strong><p>{live.data?.queue?.entry.position?'Your current queue position':'Check in for your position'}</p></div><dl className="waiting-status-lines"><div><dt>Your token</dt><dd>{live.data?.queue?.entry.token_number??'Not checked in'}</dd></div><div><dt>Status</dt><dd>{live.data?.queue?.entry.state.replaceAll('_',' ')??'Not available'}</dd></div></dl><p>Keep this page open for status updates.</p><small>Wait estimates are not supplied by the service.</small></aside>
  </div>;
}

const stageOrder: JourneyStage["name"][] = ["appointment", "check_in", "consultation", "prescription", "pharmacy", "billing"];
const stageLabels: Record<JourneyStage["name"], string> = {
  appointment: "Appointment",
  check_in: "Check-in",
  consultation: "Consultation",
  prescription: "Prescription",
  pharmacy: "Pharmacy",
  billing: "Billing",
};

function JourneyTimeline({ journey }: { journey: Journey }) {
  const stages = [...journey.stages].sort((left, right) => stageOrder.indexOf(left.name) - stageOrder.indexOf(right.name));
  return <ol className="patient-workflow__timeline" aria-label={`Journey stages for appointment ${journey.appointment_id}`}>
    {stages.map((stage) => <li key={stage.name} className={`patient-workflow__stage patient-workflow__stage--${stage.state}`}>
      <div className="patient-workflow__stage-marker" aria-hidden="true" />
      <div>
        <h4>{stageLabels[stage.name]}</h4>
        <p><strong>{stage.state === "pending" ? "Incomplete" : stage.state}</strong>{stage.pending_reason ? ` — ${stage.pending_reason.replaceAll("_", " ")}` : ""}</p>
        {stage.observed_at && <p className="patient-workflow__meta">Updated {formatTime(stage.observed_at)}.</p>}
        {stage.sources.length > 0 && <ItemDetails><ul>{stage.sources.map((source) => <li key={`${source.owner}:${source.resource_type}:${source.resource_id}`}>
          {source.owner} {source.resource_type} {source.resource_id}, version {source.version}, observed {formatTime(source.observed_at)}
        </li>)}</ul></ItemDetails>}
      </div>
    </li>)}
  </ol>;
}

export function PatientJourneyPage() {
  const demo=useLocalDemo();
  const { api, gate } = usePatientAccess();
  const profile = useLoad<PatientProfile>(api, gate === "ready" ? "/api/v1/patients/me" : null, gate === "ready");
  const listPath = profile.data
    ? buildQuery("/api/v1/appointments/journeys", { patient_id: profile.data.id, limit: "20" })
    : null;
  const list = usePagedItems<Journey>(api, listPath, gate === "ready" && !!profile.data);
  const [selectedId, setSelectedId] = useState("");
  const [reconcilePending, setReconcilePending] = useState(false);
  const [reconcileError, setReconcileError] = useState<string | null>(null);
  const journeys = list.items;
  useEffect(() => {
    if (!selectedId && journeys[0]) setSelectedId(journeys[0].id);
    if (selectedId && !journeys.some((journey) => journey.id === selectedId)) setSelectedId("");
  }, [journeys, selectedId]);
  const detail = useLoad<Journey>(api, gate === "ready" && selectedId ? `/api/v1/appointments/journeys/${selectedId}` : null, gate === "ready" && !!selectedId);
  async function reconcile() {
    if (!detail.data || !detail.etag) {
      setReconcileError("Reload the journey to obtain its current version before reconciliation.");
      return;
    }
    setReconcilePending(true);
    setReconcileError(null);
    try {
      await sendCommand<Journey>(
        api,
        `/api/v1/appointments/journeys/${detail.data.id}/reconcile`,
        {},
        { ifMatch: detail.etag },
      );
      detail.reload();
      list.reload();
    } catch (error) {
      setReconcileError(getErrorMessage(error));
      detail.reload();
    } finally {
      setReconcilePending(false);
    }
  }

  if (gate !== "ready") return <PatientGate state={gate} />;
  return <div className="patient-workflow">
    <section className="patient-workflow__panel" aria-labelledby="patient-journey-title">
      <h2 id="patient-journey-title">Patient journey</h2>
      <p>Your visit, step by step.</p>
      {profile.error && <div role="alert"><p>{profile.error}</p><RetryButton onClick={profile.reload} /></div>}
      {profile.loading && <p role="status">Loading your patient profile…</p>}
      {list.loading && <p role="status">Loading your journeys…</p>}
      {list.error && <div role="alert"><p>{list.error}</p><RetryButton onClick={list.reload} /></div>}
      {list.nextCursor && <button type="button" disabled={list.loadingMore} onClick={() => void list.loadMore()}>{list.loadingMore ? "Loading journeys…" : "Load more journeys"}</button>}
      {list.loadMoreError && <div role="alert"><p>{list.loadMoreError}</p><button type="button" onClick={() => void list.loadMore()}>Retry loading journeys</button></div>}
      {!list.loading && !list.error && journeys.length === 0 && <p>No journey records were returned for this patient.</p>}
      {journeys.length > 0 && <>
        <label htmlFor="patient-journey-select">Journey</label>
        <select id="patient-journey-select" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
          {journeys.map((journey) => <option key={journey.id} value={journey.id}>Visit — {demo?.appointments[journey.appointment_id]?.label??"Your visit"} — {journey.state}</option>)}
        </select>
      </>}
      {detail.loading && <p role="status">Loading current journey details…</p>}
      {detail.error && <div role="alert"><p>{detail.error}</p><RetryButton onClick={detail.reload} /></div>}
      {detail.data && <>
        <dl className="patient-workflow__facts">
          <div><dt>Journey status</dt><dd>{detail.data.state}</dd></div>
          <div><dt>Appointment</dt><dd>{demo?.appointments[detail.data.appointment_id]?.label??"Your visit"}</dd></div>
          <div><dt>Updated</dt><dd>{formatTime(detail.data.last_reconciled_at)}</dd></div>
          <div><dt>Review required</dt><dd>{detail.data.review_required ? "Yes" : "No"}</dd></div>
        </dl>
        <ItemDetails>Journey {detail.data.id} · Appointment {detail.data.appointment_id}</ItemDetails>
        <JourneyTimeline journey={detail.data} />
        <WorkflowHistory path={`/api/v1/appointments/journeys/${detail.data.id}/history`} />
        <PageRefresh type="button" onClick={() => void reconcile()} disabled={reconcilePending || detail.loading || !detail.etag}>{reconcilePending ? "Refreshing journey…" : "Refresh journey from current owner snapshots"}</PageRefresh>
        {reconcileError && <p role="alert">{reconcileError}</p>}
        {detail.data.review_required && <p role="status">The service has flagged this journey for review. Patient actions cannot clear that flag.</p>}
        {detail.data.discharge_eligible && <p role="status">The service reports the workflow ready for staff discharge. Patients cannot discharge a journey.</p>}
      </>}
    </section>
  </div>;
}
