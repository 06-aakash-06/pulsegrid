import { useAuth } from "../auth/authContext";
import { CommandForm, Facts, Resource } from "../hospital/ui";
const path = "/api/v1/appointments/operations/surge-mode";
interface SurgeSnapshot {
  state: string;
  version: number;
  changed_at: string | null;
  expires_at: string | null;
  reason_code: string | null;
}
export function SurgeModeControls({ onChange }: { onChange: () => void }) {
  const { state } = useAuth();
  // Phase 6 GET/POST both require current hospital_admin authority; ops is read-only.
  if (
    state.status !== "authenticated" ||
    !state.roleHints.includes("hospital_admin")
  )
    return null;
  return (
    <details className="surge-console">
      <summary>Surge Mode controls · Administrator</summary>
      <Resource<SurgeSnapshot> path={path}>
        {(snapshot, _etag, reload) => (
          <>
            <Facts
              values={{
                State: snapshot.state,
                Version: snapshot.version,
                "Changed (UTC)": snapshot.changed_at,
                "Expires (UTC)": snapshot.expires_at,
                Reason: snapshot.reason_code,
              }}
            />
            <p>
              Enter Surge Mode or begin its server-timed recovery. The shared
              admission policy keeps critical operations protected. Changes
              require review and an audited reason.
            </p>
            <CommandForm
              title="Change Surge Mode"
              path={path}
              fields={[
                {
                  name: "active",
                  label: "Requested operation",
                  kind: "select",
                  required: true,
                  options: ["true", "false"],
                  optionLabels: {
                    true: "Enter Surge Mode",
                    false: "Begin Recovery",
                  },
                },
                {
                  name: "reason_code",
                  label: "Operational reason",
                  kind: "select",
                  required: true,
                  options: [
                    "capacity_pressure",
                    "dependency_degraded",
                    "planned_recovery",
                    "incident_override",
                  ],
                  optionLabels: {
                    capacity_pressure: "Capacity pressure",
                    dependency_degraded: "Dependency degraded",
                    planned_recovery: "Planned recovery",
                    incident_override: "Incident override",
                  },
                },
                {
                  name: "override",
                  label: "Transition policy",
                  kind: "select",
                  required: true,
                  initial: "false",
                  options: ["false", "true"],
                  optionLabels: {
                    false: "Standard transition",
                    true: "Incident override (audited)",
                  },
                },
              ]}
              build={(values) => {
                const override = values.override === "true";
                if (override !== (values.reason_code === "incident_override"))
                  throw new Error(
                    "An incident override requires both the incident reason and the explicitly selected override policy.",
                  );
                return {
                  active: values.active === "true",
                  reason_code: values.reason_code,
                  override,
                };
              }}
              onSuccess={() => {
                reload();
                onChange();
              }}
            />
          </>
        )}
      </Resource>
    </details>
  );
}
