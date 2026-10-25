import { WorkflowHistory } from "../../advanced/shared/WorkflowHistory";
import { useState } from "react";
import { CommandForm, Facts, Lookup, Panel, Resource } from "../ui";
import type { Journey } from "./contracts";
import { scheduleLocalTime } from "./utils";

export function StaffJourneyTools() {
  const [journeyId, setJourneyId] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  return (
    <Panel title="Patient journey">
      <p>
        Journey stages contain owner-reported workflow state and source versions. They do not include clinical notes. Reconciliation can leave owner-unavailable stages pending.
      </p>
      <Lookup label="Journey ID" onSelect={setJourneyId} />
      <Resource<Journey>
        path={journeyId ? `/api/v1/appointments/journeys/${journeyId}` : null}
        revision={reload}
      >
        {(journey, etag, refresh) => {
          const canDischarge =
            journey.state === "ready" &&
            journey.discharge_eligible &&
            !journey.review_required;
          return (
            <div className="staff-advanced-journey">
              <WorkflowHistory path={`/api/v1/appointments/journeys/${journey.id}/history`} />
              <Facts
                values={{
                  "Journey ID": journey.id,
                  "Appointment ID": journey.appointment_id,
                  State: journey.state,
                  "Discharge eligible": String(journey.discharge_eligible),
                  "Review required": String(journey.review_required),
                  "Last reconciled (UTC)": journey.last_reconciled_at
                    ? scheduleLocalTime(journey.last_reconciled_at)
                    : "Not reconciled",
                }}
              />
              <h3>Journey stages</h3>
              <ol className="staff-advanced-stage-list">
                {journey.stages.map((stage) => (
                  <li className="staff-advanced-stage" key={stage.name}>
                    <strong>{stage.name.replaceAll("_", " ")}</strong>
                    <p>State: {stage.state}</p>
                    {stage.pending_reason && <p>Pending reason: {stage.pending_reason.replaceAll("_", " ")}</p>}
                    <p>
                      Observed: {stage.observed_at ? scheduleLocalTime(stage.observed_at) : "Not observed"}
                    </p>
                    {stage.sources.length > 0 && (
                      <ul>
                        {stage.sources.map((source) => (
                          <li key={`${source.owner}:${source.resource_type}:${source.resource_id}`}>
                            {source.owner} {source.resource_type} {source.resource_id}, version {source.version}, observed {scheduleLocalTime(source.observed_at)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ol>
              <CommandForm<Journey>
                title="Reconcile journey" reviewLabel="Review reconcile" confirmLabel="Reconcile journey" successMessage="Journey reconciled."
                path={`/api/v1/appointments/journeys/${journey.id}/reconcile`}
                conditional
                etag={etag}
                onSuccess={() => {
                  refresh();
                  setReload((value) => value + 1);
                }}
                notice="The service fetches current owner snapshots. An unavailable owner remains pending; the UI does not mark that stage complete."
              />
              {canDischarge ? (
                <CommandForm<Journey>
                  title="Discharge journey" reviewLabel="Review discharge" confirmLabel="Discharge journey" successMessage="Journey discharged."
                  path={`/api/v1/appointments/journeys/${journey.id}/discharge`}
                  conditional
                  etag={etag}
                  fields={[{ name: "reason", label: "Reason", kind: "textarea", required: true, max: 500 }]}
                  onSuccess={() => {
                    refresh();
                    setReload((value) => value + 1);
                  }}
                  notice="This is an administrative workflow action, not clinical clearance."
                />
              ) : (
                <p className="staff-advanced-muted">
                  Discharge is available only to receptionists after the service reports a ready, eligible journey with no review flag.
                </p>
              )}
            </div>
          );
        }}
      </Resource>
    </Panel>
  );
}
