import { StatusBadge } from "../components/StatusBadge";
import { m } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  type ApiResponse,
  type ApiRequestOptions,
} from "../api/client";
import { publishHospitalIdentity } from "../design/hospitalIdentity";
import { useAuth } from "../auth/authContext";
import type { Page, Versioned } from "./models";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const advice =
      error.status === 412
        ? " Reload the resource and review your changes before submitting again."
        : "";
    const retry=error.retryAfterSeconds !== undefined ? ` Wait ${error.retryAfterSeconds} seconds before retrying.` : "";
    return `${error.message}${retry}${advice}${error.requestId ? ` Request ID: ${error.requestId}` : ""}`;
  }
  return error instanceof Error
    ? error.message
    : "The request could not be completed.";
}
export function query(
  path: string,
  filters: Record<string, string | undefined>,
) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return params.size ? `${path}?${params}` : path;
}
export function useResource<T>(path: string | null, revision = 0) {
  const { api, state } = useAuth();
  const [response, setResponse] = useState<ApiResponse<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    setResponse(null);
    setError(null);
    setLoading(!!path);
    if (!path) return;
    const controller = new AbortController();
    void api
      .requestWithMetadata<T>(path, { signal: controller.signal })
      .then((result) => {
        if (!controller.signal.aborted) {
          setResponse(result);
          if(state.status==='authenticated' && state.user.id){
            const owner=result.data as {display_name?:string;user_id?:string;staff_user_id?:string;doctor?:{display_name?:string}};
            if(path==='/api/v1/patients/me' && owner.user_id===state.user.id && typeof owner.display_name==='string')publishHospitalIdentity(state.user.id,owner.display_name);
            if(path==='/api/v1/doctors/me' && owner.staff_user_id===state.user.id && typeof owner.doctor?.display_name==='string')publishHospitalIdentity(state.user.id,owner.doctor.display_name);
          }
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [api, path, revision, reload]);
  return {
    response,
    error,
    loading,
    refresh: () => setReload((value) => value + 1),
  };
}
export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="hospital-panel" data-panel={title.toLowerCase().replaceAll(" ", "-")}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export function Resource<T>({
  path,
  revision = 0,
  showReload = true,
  children,
}: {
  path: string | null;
  revision?: number;
  showReload?: boolean;
  children: (data: T, etag: string | null, refresh: () => void) => ReactNode;
}) {
  const resource = useResource<T>(path, revision);
  return (
    <>
      {resource.loading && <p role="status">Loading resource…</p>}
      {resource.error && <p role="alert">{resource.error}</p>}
      {path && showReload && (
        <button
          type="button"
          disabled={resource.loading}
          onClick={resource.refresh}
        >
          Reload resource
        </button>
      )}
      {resource.response &&
        children(
          resource.response.data,
          resource.response.etag,
          resource.refresh,
        )}
    </>
  );
}
export function Collection<T extends { id: string }>({
  path,
  title,
  renderItem,
  revision = 0,
}: {
  path: string | null;
  title: string;
  renderItem: (item: T) => ReactNode;
  revision?: number;
}) {
  return (
    <CollectionPage<T>
      key={`${path}:${revision}`}
      path={path}
      title={title}
      renderItem={renderItem}
    />
  );
}
function CollectionPage<T extends { id: string }>({
  path,
  title,
  renderItem,
}: {
  path: string | null;
  title: string;
  renderItem: (item: T) => ReactNode;
}) {
  const [cursor, setCursor] = useState<string | undefined>();
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const pagedPath = path
    ? `${path}${path.includes("?") ? "&" : "?"}limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`
    : null;
  const resource = useResource<Page<T>>(pagedPath);
  return (
    <Panel title={title}>
      {resource.loading && <p role="status">Loading {title.toLowerCase()}…</p>}
      {resource.error && <p role="alert">{resource.error}</p>}
      <div className="resource-toolbar"><span>Owner service data</span><button
        type="button"
        onClick={resource.refresh}
        disabled={!path || resource.loading}
      >
        Refresh {title.toLowerCase()}
      </button></div>
      {resource.response && (
        <>
          {resource.response.data.items.length === 0 && (
            <div className="resource-empty"><strong>No {title.toLowerCase()} found.</strong><p>Nothing to display for the current filters.</p></div>
          )}
          <div className="hospital-items">
            {resource.response.data.items.map((item) => (
              <m.article initial={false} layout="position" transition={{duration:0.18}} className="hospital-item" key={item.id}>
                {renderItem(item)}
              </m.article>
            ))}
          </div>
          <div className="hospital-actions">
            <button
              type="button"
              disabled={history.length === 0 || resource.loading}
              onClick={() => {
                setCursor(history.at(-1));
                setHistory(history.slice(0, -1));
              }}
            >
              Previous page
            </button>
            <button
              type="button"
              disabled={!resource.response.data.next_cursor || resource.loading}
              onClick={() => {
                setHistory([...history, cursor]);
                setCursor(resource.response!.data.next_cursor!);
              }}
            >
              Next page
            </button>
          </div>
        </>
      )}
    </Panel>
  );
}
export interface Field {
  name: string;
  label: string;
  kind?: "text" | "textarea" | "date" | "number" | "select" | "ids";
  required?: boolean;
  max?: number;
  min?: number;
  options?: string[];
  optionLabels?: Record<string,string>;
  initial?: string;
  nullable?: boolean;
  id?: boolean;
}
export type Values = Record<string, string>;
export function id(value: string): string {
  if (!/^[1-9][0-9]{0,18}$/.test(value) || BigInt(value) > 9223372036854775807n)
    throw new Error("Enter a valid positive decimal ID.");
  return value;
}
export function integer(
  value: string,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
): number {
  if (
    !/^-?\d+$/.test(value) ||
    !Number.isSafeInteger(Number(value)) ||
    Number(value) < min ||
    Number(value) > max
  )
    throw new Error(`Enter a whole number between ${min} and ${max}.`);
  return Number(value);
}
export function ids(value: string, min = 0, max = 50): string[] {
  const list = value.trim() ? value.split(",").map((v) => id(v.trim())) : [];
  if (
    list.length < min ||
    list.length > max ||
    new Set(list).size !== list.length
  )
    throw new Error(
      `Enter ${min} to ${max} distinct IDs, separated by commas.`,
    );
  return list;
}
export function utc(value: string): string {
  if (
    !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?(Z|\+00:00)$/.test(value) ||
    !Number.isFinite(Date.parse(value)) ||
    new Date(value).toISOString().slice(0, 19) !== value.slice(0, 19)
  )
    throw new Error("Enter a UTC timestamp such as 2026-10-12T09:00:00Z.");
  return value;
}
export function date(value: string): string {
  if (
    !/^\d{4}-\d\d-\d\d$/.test(value) ||
    new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value
  )
    throw new Error("Enter a valid date.");
  return value;
}
export const idField = (
  name: string,
  label: string,
  required = true,
): Field => ({ name, label, required, id: true });
export const textField = (name: string, label: string, max = 4000): Field => ({
  name,
  label,
  required: true,
  max,
  kind: "textarea",
});
export const reasonField = textField("reason", "Reason", 500);
export function buildFields(
  fields: Field[],
  values: Values,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  fields.forEach((field) => {
    const value = (values[field.name] ?? "").trim();
    if (!value) {
      if (field.required) throw new Error(`${field.label} is required.`);
      if (field.nullable) body[field.name] = null;
      return;
    }
    if (field.max && field.kind !== "number" && value.length > field.max)
      throw new Error(`${field.label} is too long.`);
    if (field.options && !field.options.includes(value))
      throw new Error(`Choose a valid ${field.label.toLowerCase()}.`);
    body[field.name] = field.id
      ? id(value)
      : field.kind === "number"
        ? integer(value, field.min, field.max)
        : field.kind === "ids"
          ? ids(value)
          : field.kind === "date"
            ? date(value)
            : value;
  });
  return body;
}
export function Inputs({
  fields,
  values,
  change,
  disabled,
}: {
  fields: Field[];
  values: Values;
  change: (name: string, value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="hospital-fields">
      {fields.map((field) => (
        <label key={field.name}>
          {field.label}
          {field.kind === "select" ? (
            <select
              value={values[field.name] ?? ""}
              disabled={disabled}
              onChange={(e) => change(field.name, e.target.value)}
            >
              <option value="">Select…</option>
              {field.options?.map((option) => (
                <option key={option} value={option}>{field.optionLabels?.[option] ?? option}</option>
              ))}
            </select>
          ) : field.kind === "textarea" ? (
            <textarea
              value={values[field.name] ?? ""}
              disabled={disabled}
              maxLength={field.max}
              onChange={(e) => change(field.name, e.target.value)}
            />
          ) : (
            <input
              type={
                field.kind === "date"
                  ? "date"
                  : field.kind === "number"
                    ? "number"
                    : "text"
              }
              value={values[field.name] ?? ""}
              disabled={disabled}
              maxLength={field.kind !== "number" ? field.max : undefined}
              onChange={(e) => change(field.name, e.target.value)}
            />
          )}
        </label>
      ))}
    </div>
  );
}
interface Attempt {
  path: string;
  options: ApiRequestOptions;
}
export function CommandForm<T = unknown>({
  title,
  path,
  fields = [],
  method = "POST",
  etag,
  conditional = false,
  build,
  onSuccess,
  onLockChange,
  notice,
  children,
}: {
  title: string;
  path: string;
  fields?: Field[];
  method?: "POST" | "PATCH" | "DELETE";
  etag?: string | null;
  conditional?: boolean;
  build?: (values: Values) => unknown;
  onSuccess?: (data: T, etag: string | null) => void;
  onLockChange?: (locked: boolean) => void;
  notice?: string;
  children?: ReactNode;
}) {
  const { api } = useAuth();
  const [values, setValues] = useState<Values>(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ""])),
  );
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const lock = useRef(false);
  useEffect(()=>{onLockChange?.(!!attempt || pending);},[attempt,pending,onLockChange]);
  async function send(command: Attempt) {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError(null);
    setSuccess(false);
    try {
      const response = await api.requestWithMetadata<T>(
        command.path,
        command.options,
      );
      setAttempt(null);
      setAmbiguous(false);
      setSuccess(true);
      onSuccess?.(response.data, response.etag);
    } catch (err) {
      setError(errorMessage(err));
      const uncertain =
        method === "POST" &&
        err instanceof ApiError &&
        (err.status === 0 ||
          err.status >= 500 ||
          err.code === "invalid_response");
      setAmbiguous(uncertain);
      if (!uncertain) setAttempt(null);
    } finally {
      lock.current = false;
      setPending(false);
    }
  }
  return (
    <form
      className="hospital-form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (pending || attempt) return;
        setSuccess(false);
        setError(null);
        try {
          if (conditional && (!etag || !/^"[1-9][0-9]*"$/.test(etag)))
            throw new Error(
              "Reload this resource to obtain its current version before changing it.",
            );
          const normalizedValues = Object.fromEntries(
            Object.entries(values).map(([key, value]) => [key, value.trim()]),
          );
          const fieldBody = buildFields(fields, normalizedValues);
          const body =
            method === "DELETE"
              ? undefined
              : build
                ? build(normalizedValues)
                : fieldBody;
          setAttempt({
            path,
            options: {
              method,
              body,
              ...(method === "POST"
                ? { idempotencyKey: crypto.randomUUID() }
                : {}),
              ...(conditional ? { ifMatch: etag! } : {}),
            },
          });
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <h3>{title}</h3>
      {notice && <p>{notice}</p>}
      <fieldset
        disabled={!!attempt || pending}
        className="hospital-command-inputs"
      >
        {children}
      </fieldset>
      <Inputs
        fields={fields}
        values={values}
        change={(name, value) => setValues({ ...values, [name]: value })}
        disabled={!!attempt || pending}
      />
      {error && <p role="alert">{error}</p>}
      {success && <m.p initial={{opacity:.5,y:5}} animate={{opacity:1,y:0}} transition={{duration:.22}} role="status" className="command-receipt">{title}: confirmed by the service.</m.p>}
      {pending && <p role="status">Submitting {title.toLowerCase()}…</p>}
      {attempt ? (
        <m.div initial={{opacity:.7}} animate={{opacity:1}} transition={{duration:.18}}
          className="hospital-confirm"
          role="group"
          aria-label={`Confirm ${title}`}
        >
          <p>
            {ambiguous
              ? "The outcome is uncertain. Retry the original command with the same content and key before starting a different command. Keep this page open to retain the retry."
              : `Confirm ${title.toLowerCase()} with the values shown above?`}
          </p>
          <button
            type="button"
            disabled={pending}
            onClick={() => void send(attempt)}
          >
            {ambiguous ? "Retry original command" : `Confirm ${title}`}
          </button>
          {!ambiguous && (
            <button
              type="button"
              disabled={pending}
              onClick={() => setAttempt(null)}
            >
              Keep editing
            </button>
          )}
        </m.div>
      ) : (
        <button type="submit" disabled={pending || (conditional && !etag)}>
          Review {title}
        </button>
      )}
    </form>
  );
}
export function Lookup({
  label,
  onSelect,
}: {
  label: string;
  onSelect: (id: string) => void;
}) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        try {
          onSelect(id(value.trim()));
          setError("");
        } catch (err) {
          setError(errorMessage(err));
        }
      }}
    >
      <label>
        {label}
        <input value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <button>Open</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
export function Facts({ values }: { values: Record<string, ReactNode> }) {
  return (
    <dl className="hospital-facts">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value)) ? <time dateTime={value} title={value}>{new Date(value).toLocaleString("en-IN",{timeZone:"UTC",dateStyle:"medium",timeStyle:"short"})} UTC</time> : ["State","Status"].includes(key) && typeof value === "string" ? <StatusBadge tone={["confirmed","paid","finalized","completed","dispensed","resolved","success"].includes(value)?"success":["cancelled","declined","revoked"].includes(value)?"danger":"warning"}>{value.replaceAll("_"," ")}</StatusBadge> : value ?? "None"}</dd>
        </div>
      ))}
    </dl>
  );
}
export function Selected<T extends Versioned>({
  path,
  revision,
  children,
}: {
  path: string | null;
  revision?: number;
  children: (item: T, etag: string | null, refresh: () => void) => ReactNode;
}) {
  return path ? (
    <Panel title={path.includes("/doctors/") ? "Doctor profile" : path.includes("/billing/invoices/") ? "Current invoice" : path.includes("/emergencies/") ? "Active request" : path.includes("/pharmacy/reservations/") ? "Current reservation" : path.includes("/pharmacy/medicines/") ? "Medicine details" : path.includes("/appointments/") ? "Appointment details" : path.includes("/records/prescriptions/") ? "Prescription details" : path.includes("/records/") ? "Clinical dossier" : "Selected resource"}>
      <Resource<T> path={path} revision={revision}>
        {(item, etag, refresh) => (
          <div key={`${item.id}:${item.version}`}>
            {children(item, etag, refresh)}
          </div>
        )}
      </Resource>
    </Panel>
  ) : null;
}
export function money(minor: number) {
  // Keep the last paise exact even near the maximum safe integer.
  const amount = BigInt(minor);
  const whole = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
    minimumFractionDigits: 0,
  }).format(amount / 100n);
  return `${whole}.${String(amount % 100n).padStart(2, "0")}`;
}
