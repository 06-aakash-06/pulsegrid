import { QueuePatientName } from "../../components/HumanLabels";
import { ItemDetails, PageRefresh } from "../../components/PageTools";
import { QueueTransitions } from "./QueueTransitions";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/authContext";
import { date as validateDate, Facts, Panel } from "../ui";
import type { DoctorSelf, OwnQueue, QueueEntry, StaffQueue } from "./contracts";
import { StaffJourneyTools } from "./JourneyTools";
import { StaffRoleGate } from "./StaffRoleGate";
import "./staffAdvanced.css";
import {
  appendQueueQuery,
  currentLocalDate,
  errorMessage,
  idempotencyKey,
  isAmbiguousCommandFailure,
  scheduleLocalTime,
} from "./utils";

const STAFF_POLL_MS = 3000;
const STALE_AFTER_MS = 15000;
const RETRY_SECONDS = [5, 10, 20, 30];

interface LoadedPage {
  snapshot: StaffQueue;
  etag: string | null;
}

interface PendingQueueStart {
  entryId: string;
  appointmentId: string;
  tokenNumber: number;
  ifMatch: string;
  key: string;
}

function retryDelay(attempt: number): number {
  const seconds = RETRY_SECONDS[Math.min(attempt, RETRY_SECONDS.length - 1)];
  return Math.round(seconds * 1000 * (0.75 + Math.random() * 0.5));
}

function queueCommandMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    const conflictMessages: Record<string, string> = {
      doctor_busy: "Another queue entry is already in consultation. Refresh the queue before starting another patient.",
      not_queue_head: "The queue head changed. The current queue is being refreshed.",
      invalid_transition: "This entry changed state before it could be started. Refresh the queue.",
      queue_changed: "The queue snapshot changed while paging. Reload the first page.",
    };
    return conflictMessages[error.code] ?? errorMessage(error);
  }
  return errorMessage(error);
}

export function DoctorQueuePage() {
  const { api, state: authState } = useAuth();
  const [doctor, setDoctor] = useState<DoctorSelf | null>(null);
  const [doctorError, setDoctorError] = useState("");
  const [doctorLoading, setDoctorLoading] = useState(true);
  const [localDate, setLocalDate] = useState(currentLocalDate);
  const [pages, setPages] = useState<LoadedPage[]>([]);
  const [queueError, setQueueError] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionPending, setActionPending] = useState(false);
  const [startAttempt, setStartAttempt] = useState<PendingQueueStart | null>(null);
  const [startAttemptAmbiguous, setStartAttemptAmbiguous] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [conflictNote, setConflictNote] = useState("");
  const [lastSuccess, setLastSuccess] = useState<number | null>(null);
  const [stale, setStale] = useState(false);
  const [started, setStarted] = useState<Pick<QueueEntry, "id" | "appointment_id" | "token_number" | "state"> | null>(null);
  const requestInFlight = useRef(false);
  const stopPollingRef = useRef(false);
  const refreshFirstPageRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (authState.status !== "authenticated" || !authState.roleHints.includes("doctor")) {
      setDoctor(null);
      setDoctorError("");
      setDoctorLoading(false);
      return;
    }
    const controller = new AbortController();
    setDoctor(null);
    setDoctorError("");
    setDoctorLoading(true);
    void api.requestWithMetadata<DoctorSelf>("/api/v1/doctors/me", { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setDoctor(response.data);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setDoctorError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDoctorLoading(false);
      });
    return () => controller.abort();
  }, [api, authState]);

  const doctorId = doctor?.doctor.id ?? null;
  let localDateValid = true;
  try {
    validateDate(localDate);
  } catch {
    localDateValid = false;
  }
  const queuePath = useMemo(() => doctorId
    && localDateValid
    ? appendQueueQuery("/api/v1/appointments/queues", {
        doctor_id: doctorId,
        local_date: localDate,
        limit: "100",
      })
    : null, [doctorId, localDate, localDateValid]);

  useEffect(() => {
    if (!queuePath) {
      setPages([]);
      setLastSuccess(null);
      setStale(false);
      return;
    }
    let disposed = false;
    let timer: number | null = null;
    let retryAttempt = 0;
    let activeController: AbortController | null = null;
    let lastQueueVersion: number | null = null;
    requestInFlight.current = false;
    stopPollingRef.current = false;
    setPages([]);
    setQueueError("");
    setConflictNote("");
    setLastSuccess(null);
    setStale(false);

    const clearTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };

    const schedule = (delay: number) => {
      clearTimer();
      if (!disposed && document.visibilityState !== "hidden") {
        timer = window.setTimeout(() => void fetchFirstPage(), delay);
      }
    };

    const fetchFirstPage = async () => {
      if (disposed || stopPollingRef.current || document.visibilityState === "hidden") return;
      if (requestInFlight.current) {
        schedule(300);
        return;
      }
      requestInFlight.current = true;
      const controller = new AbortController();
      activeController = controller;
      setRefreshing(true);
      try {
        const response = await api.requestWithMetadata<StaffQueue>(queuePath, { signal: controller.signal });
        if (disposed || controller.signal.aborted) return;
        const loaded: LoadedPage = { snapshot: response.data, etag: response.etag };
        if (lastQueueVersion !== null && response.data.version < lastQueueVersion) {
          schedule(STAFF_POLL_MS);
          return;
        }
        if (lastQueueVersion !== null && response.data.version !== lastQueueVersion) {
          setConflictNote("The queue changed. Additional pages were cleared and the first page has been refreshed.");
          setPages([loaded]);
        } else {
          setPages((current) => current.length ? [loaded, ...current.slice(1)] : [loaded]);
        }
        lastQueueVersion = response.data.version;
        setQueueError("");
        setConflictNote((current) => current.startsWith("The queue changed while paging") ? "" : current);
        setLastSuccess(Date.now());
        setStale(false);
        retryAttempt = 0;
        schedule(STAFF_POLL_MS);
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        setQueueError(errorMessage(error));
        if (error instanceof ApiError && (error.status === 403 || error.status === 401)) {
          stopPollingRef.current = true;
          return;
        }
        if (error instanceof ApiError && error.status === 409 && error.code === "queue_changed") {
          setPages([]);
          setConflictNote("The queue changed while paging. Reloading the first page.");
          retryAttempt = 0;
          schedule(500);
          return;
        }
        schedule(retryDelay(retryAttempt));
        retryAttempt += 1;
      } finally {
        if (activeController === controller) activeController = null;
        requestInFlight.current = false;
        if (!disposed) setRefreshing(false);
      }
    };

    refreshFirstPageRef.current = () => {
      clearTimer();
      void fetchFirstPage();
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        clearTimer();
        activeController?.abort();
      } else {
        if (stopPollingRef.current) return;
        retryAttempt = 0;
        clearTimer();
        void fetchFirstPage();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void fetchFirstPage();
    return () => {
      disposed = true;
      clearTimer();
      activeController?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [api, queuePath]);

  useEffect(() => {
    if (lastSuccess === null) return;
    const remaining = Math.max(0, STALE_AFTER_MS - (Date.now() - lastSuccess));
    const timer = window.setTimeout(() => setStale(true), remaining);
    return () => window.clearTimeout(timer);
  }, [lastSuccess]);

  const firstPage = pages[0]?.snapshot ?? null;
  const currentPage = pages.at(-1)?.snapshot ?? null;
  const currentCursor = currentPage?.next_cursor ?? null;
  const pageIndex = Math.max(0, pages.length - 1);

  const loadNextPage = useCallback(async () => {
    if (!queuePath || !currentCursor || requestInFlight.current) return;
    requestInFlight.current = true;
    setPageLoading(true);
    setActionError("");
    try {
      const path = appendQueueQuery("/api/v1/appointments/queues", {
        doctor_id: doctorId ?? undefined,
        local_date: localDate,
        limit: "100",
        cursor: currentCursor,
      });
      const response = await api.requestWithMetadata<StaffQueue>(path);
      if (!firstPage || response.data.version !== firstPage.version) {
        setConflictNote("The queue changed while loading the next page. Reloading the first page.");
        setPages([]);
        refreshFirstPageRef.current();
        return;
      }
      setPages((current) => [...current, { snapshot: response.data, etag: response.etag }]);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409 && error.code === "queue_changed") {
        setConflictNote("The queue changed while loading the next page. Reloading the first page.");
        setPages([]);
        refreshFirstPageRef.current();
      } else {
        setActionError(queueCommandMessage(error));
      }
    } finally {
      requestInFlight.current = false;
      setPageLoading(false);
    }
  }, [api, currentCursor, doctorId, firstPage, localDate, queuePath]);

  async function startNextPatient() {
    if (!queuePath || !doctorId || !firstPage || firstPage.waiting_count === 0 || actionPending) return;
    setActionPending(true);
    setActionError("");
    setStarted(null);
    try {
      const headPath = appendQueueQuery("/api/v1/appointments/queues", {
        doctor_id: doctorId,
        local_date: localDate,
        state: "waiting",
        limit: "1",
      });
      const headResponse = await api.requestWithMetadata<StaffQueue>(headPath);
      const head = headResponse.data.items[0];
      if (!head) {
        setActionError("There are no waiting entries in the current queue snapshot.");
        refreshFirstPageRef.current();
        return;
      }
      const ownQueueResponse = await api.requestWithMetadata<OwnQueue>(
        `/api/v1/appointments/${head.appointment_id}/queue`,
      );
      if (ownQueueResponse.data.entry.id !== head.id || ownQueueResponse.data.entry.state !== "waiting") {
        setActionError("The queue head changed before consultation could start. The first page is being refreshed.");
        refreshFirstPageRef.current();
        return;
      }
      if (!ownQueueResponse.etag || !/^"[1-9][0-9]*"$/.test(ownQueueResponse.etag)) {
        setActionError("Reload the queue entry to obtain its current version before starting consultation.");
        refreshFirstPageRef.current();
        return;
      }
      setStartAttempt({
        entryId: head.id,
        appointmentId: head.appointment_id,
        tokenNumber: head.token_number,
        ifMatch: ownQueueResponse.etag,
        key: idempotencyKey(),
      });
      setStartAttemptAmbiguous(false);
    } catch (error) {
      setActionError(queueCommandMessage(error));
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        stopPollingRef.current = true;
        setQueueError(errorMessage(error));
      }
      if (error instanceof ApiError && (error.status === 409 || error.status === 412)) {
        setConflictNote("A concurrent queue change was detected. The current first page is being refreshed.");
        refreshFirstPageRef.current();
      }
    } finally {
      setActionPending(false);
    }
  }

  async function confirmStart(command: PendingQueueStart) {
    if (actionPending) return;
    setActionPending(true);
    setActionError("");
    try {
      const response = await api.requestWithMetadata<Omit<QueueEntry, "patient_id">>(
        `/api/v1/appointments/queue-entries/${command.entryId}/start`,
        {
          method: "POST",
          body: {},
          ifMatch: command.ifMatch,
          idempotencyKey: command.key,
        },
      );
      setStarted(response.data);
      setStartAttempt(null);
      setStartAttemptAmbiguous(false);
      refreshFirstPageRef.current();
    } catch (error) {
      setActionError(queueCommandMessage(error));
      if (isAmbiguousCommandFailure(error)) {
        setStartAttemptAmbiguous(true);
      } else {
        setStartAttempt(null);
        setStartAttemptAmbiguous(false);
      }
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        stopPollingRef.current = true;
        setQueueError(errorMessage(error));
      }
      if (error instanceof ApiError && (error.status === 409 || error.status === 412)) {
        setConflictNote("A concurrent queue change was detected. The current first page is being refreshed.");
        refreshFirstPageRef.current();
      }
    } finally {
      setActionPending(false);
    }
  }

  const entries = useMemo(() => currentPage?.items ?? [], [currentPage]);

  return (
    <StaffRoleGate role="doctor">
      <div className="staff-advanced-page">
        <Panel title="Assigned consultation queue" tour="doctor-queue">
          {doctorLoading && <p role="status">Loading your doctor assignment…</p>}
          {doctorError && <p role="alert">{doctorError}</p>}
          {doctor && (
            <>
              <p>{doctor.doctor.display_name}</p>
              <label>
                Doctor local schedule date
                <input
                  type="date"
                  value={localDate}
                  onChange={(event) => {
                    const value = event.target.value;
                    setLocalDate(value);
                    if (!value) setQueueError("Choose a valid date in the doctor’s time zone.");
                    else {
                      try {
                        validateDate(value);
                        setQueueError("");
                      } catch {
                        setQueueError("Choose a valid date in the doctor’s time zone.");
                      }
                    }
                  }}
                  aria-describedby="staff-advanced-date-help"
                />
              </label>
              <p id="staff-advanced-date-help" className="staff-advanced-muted">Choose your schedule date.</p>
              <PageRefresh type="button" disabled={!queuePath || refreshing} onClick={() => refreshFirstPageRef.current()}>Refresh queue</PageRefresh>
              {!localDateValid && <p role="alert">Choose a valid date in the doctor’s time zone.</p>}
              {refreshing && !firstPage && <p role="status">Loading assigned queue…</p>}
              {queueError && <p role="alert">{queueError}</p>}
              {stale && <p role="alert" className="staff-advanced-stale">Queue data is stale. Refresh before acting.</p>}
              {conflictNote && <p role="status">{conflictNote}</p>}
              {firstPage && (
                <>
                  <Facts values={{
                    "Waiting count": firstPage.waiting_count,
                    "In consultation": firstPage.in_consultation_count,
                    "Queue version": firstPage.version,
                    "Observed (UTC)": scheduleLocalTime(firstPage.observed_at),
                    "Page": pageIndex + 1,
                  }} />
                  {pageIndex === 0 && (
                    <div className="staff-advanced-summary">
                      {firstPage.waiting_count > 0 ? (
                        <>

                          <button type="button" data-tour="queue-call-next" disabled={actionPending || stale || !!startAttempt || firstPage.in_consultation_count > 0} onClick={() => void startNextPatient()}>
                            {actionPending && !startAttempt ? "Checking queue head…" : "Call next patient"}
                          </button>
                          {firstPage.in_consultation_count > 0 && <p>Finish the active consultation before calling another patient.</p>}
                        </>
                      ) : (
                        <p>No waiting entry is available in this queue snapshot.</p>
                      )}
                      <p>Skipped patients keep their token and can be recalled.</p>
                    </div>
                  )}
                  {firstPage.waiting_count === 0 && firstPage.in_consultation_count === 0 && entries.length === 0 ? (
                    <p>No queue entries were returned for this doctor and schedule date.</p>
                  ) : (
                    <div className="task-table-wrap"><table className="task-table"><thead><tr><th>Token</th><th>Patient</th><th>Status</th><th>Position</th><th>Actions</th></tr></thead><tbody>
                      {entries.map((entry) => <tr key={entry.id}><td>{entry.token_number}</td><td><QueuePatientName patientId={entry.patient_id} name={entry.patient_name} /></td><td>{entry.state.replaceAll("_"," ")}</td><td>{entry.position ?? "—"}</td><td><QueueTransitions entry={entry} refresh={() => refreshFirstPageRef.current()} /><ItemDetails>Appointment {entry.appointment_id} · Patient {entry.patient_id} · Queue entry {entry.id} · Version {entry.version}</ItemDetails></td></tr>)}
                    </tbody></table></div>
                  )}
                  <div className="hospital-actions">
                    <button type="button" disabled={pageIndex === 0 || pageLoading} onClick={() => setPages((current) => current.slice(0, -1))}>Previous page</button>
                    <button type="button" disabled={!currentCursor || pageLoading || actionPending} onClick={() => void loadNextPage()}>{pageLoading ? "Loading next page…" : "Next page"}</button>
                  </div>
                  {pageIndex === 0 && startAttempt && (
                    <div className="hospital-confirm" role="group" aria-label="Confirm call next patient">
                      <p>
                        {startAttemptAmbiguous
                          ? "The start outcome is uncertain. Retry the original command with the same key before attempting another queue action."
                          : `Confirm calling queue token ${startAttempt.tokenNumber} ?`}
                      </p>
                      <button type="button" disabled={actionPending} onClick={() => void confirmStart(startAttempt)}>
                        {actionPending ? "Starting consultation…" : startAttemptAmbiguous ? "Retry original start command" : "Confirm start consultation"}
                      </button>
                      {!startAttemptAmbiguous && (
                        <button type="button" disabled={actionPending} onClick={() => setStartAttempt(null)}>
                          Keep current queue
                        </button>
                      )}
                    </div>
                  )}
                </>
              )}
              {actionError && <p role="alert">{actionError}</p>}
              {started && (
                <div role="status" className="staff-advanced-summary">
                  Queue token {started.token_number} is ready. Continue in the <Link to="/doctor/consultations">consultation workspace</Link> to start the visit.
                </div>
              )}
            </>
          )}
        </Panel>
        <StaffJourneyTools />
      </div>
    </StaffRoleGate>
  );
}
