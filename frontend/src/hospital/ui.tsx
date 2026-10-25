import { StatusBadge } from "../components/StatusBadge";
import { m } from "motion/react";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
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
        ? " Refresh to load the latest version, then review your changes before submitting again."
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
const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function formatDateTime(
  value: string | number | Date | null | undefined,
  { utc = true, time = true }: { utc?: boolean; time?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  const day = utc ? date.getUTCDate() : date.getDate();
  const month = monthNames[utc ? date.getUTCMonth() : date.getMonth()];
  const year = utc ? date.getUTCFullYear() : date.getFullYear();
  const dateText = `${day} ${month} ${year}`;
  if (!time) return dateText;
  const hours = String(utc ? date.getUTCHours() : date.getHours()).padStart(2, "0");
  const minutes = String(utc ? date.getUTCMinutes() : date.getMinutes()).padStart(2, "0");
  return `${dateText}, ${hours}:${minutes}${utc ? " UTC" : ""}`;
}
const ReloadContext = createContext<(() => void) | null>(null);
const FlashContext = createContext<((message: string) => void) | null>(null);
export function FlashArea({ resetKey, children }: { resetKey?: string | null; children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => setMessage(null), [resetKey]);
  return (
    <FlashContext.Provider value={setMessage}>
      {message && <m.p initial={{ opacity: .5, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .22 }} role="status" className="command-receipt">{message}</m.p>}
      {children}
    </FlashContext.Provider>
  );
}
export function useResource<T>(path: string | null, revision = 0) {
  const { api, state } = useAuth();
  // The effect keys on the request, not on the client object, so a re-created client never re-fetches.
  const apiRef = useRef(api);
  apiRef.current = api;
  const [response, setResponse] = useState<ApiResponse<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const loadedPath = useRef<string | null>(null);
  useEffect(() => {
    // Refreshing the same resource keeps the current data on screen so forms below it stay mounted.
    if (loadedPath.current !== path) setResponse(null);
    loadedPath.current = path;
    setError(null);
    setLoading(!!path);
    if (!path) return;
    const controller = new AbortController();
    void apiRef.current
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
  }, [path, revision, reload]);
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
          Refresh
        </button>
      )}
      <ReloadContext.Provider value={resource.refresh}>
        {resource.response &&
          children(
            resource.response.data,
            resource.response.etag,
            resource.refresh,
          )}
      </ReloadContext.Provider>
    </>
  );
}
export function Collection<T extends { id: string }>({
  path,
  title,
  renderItem,
  revision = 0,
  onFirstItem,
  itemFilter,
  sourceNote = null,
}: {
  path: string | null;
  title: string;
  renderItem: (item: T) => ReactNode;
  revision?: number;
  onFirstItem?: (item: T) => void;
  itemFilter?: (item: T) => boolean;
  sourceNote?: ReactNode;
}) {
  const shown = useRef(new Set<string>());
  return (
    <CollectionPage<T>
      key={`${path}:${revision}`}
      animateEntry={!!path && !shown.current.has(path)}
      onShown={() => { if (path) shown.current.add(path); }}
      path={path}
      title={title}
      renderItem={renderItem}
      onFirstItem={onFirstItem}
      itemFilter={itemFilter}
      sourceNote={sourceNote}
    />
  );
}
function CollectionPage<T extends { id: string }>({
  path,
  title,
  renderItem,
  onFirstItem,
  itemFilter,
  sourceNote,
  animateEntry,
  onShown,
}: {
  path: string | null;
  title: string;
  renderItem: (item: T) => ReactNode;
  onFirstItem?: (item: T) => void;
  itemFilter?: (item: T) => boolean;
  sourceNote: ReactNode;
  animateEntry: boolean;
  onShown: () => void;
}) {
  const firstBatch = useRef<Set<string> | null>(null);
  const [cursor, setCursor] = useState<string | undefined>();
  const [history, setHistory] = useState<(string | undefined)[]>([]);
  const pagedPath = path
    ? `${path}${path.includes("?") ? "&" : "?"}limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`
    : null;
  const resource = useResource<Page<T>>(pagedPath);
  useEffect(() => {
    const first = resource.response?.data.items.find(item=>!itemFilter || itemFilter(item));
    if (first) onFirstItem?.(first);
  }, [resource.response, onFirstItem, itemFilter]);
  if (resource.response && !firstBatch.current)
    firstBatch.current = new Set(animateEntry ? resource.response.data.items.slice(0, 8).map((item) => item.id) : []);
  useEffect(() => {
    if (resource.response) onShown();
  }, [resource.response, onShown]);
  return (
    <Panel title={title}>
      {resource.loading && <p role="status">Loading {title.toLowerCase()}…</p>}
      {resource.error && <p role="alert">{resource.error}</p>}
      <div className="resource-toolbar">{sourceNote && <span>{sourceNote}</span>}<button
        type="button"
        onClick={resource.refresh}
        disabled={!path || resource.loading}
      >
        Refresh {title.toLowerCase()}
      </button></div>
      {resource.response && (
        <>
          {resource.response.data.items.filter(item=>!itemFilter || itemFilter(item)).length === 0 && (
            <div className="resource-empty"><strong>No {title.toLowerCase()} found.</strong><p>Nothing to display for the current filters.</p></div>
          )}
          <div className="hospital-items">
            {resource.response.data.items.filter(item=>!itemFilter || itemFilter(item)).map((item, index) => (
              <m.article
                initial={firstBatch.current?.has(item.id) ? { opacity: 0, y: 6 } : false}
                animate={{ opacity: 1, y: 0 }}
                layout="position"
                transition={{ duration: 0.18, delay: firstBatch.current?.has(item.id) ? Math.min(index, 7) * 0.03 : 0 }}
                className="hospital-item"
                key={item.id}
              >
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
              title={values[field.name] || field.label}
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
              title={values[field.name] || field.label}
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
              title={values[field.name] || field.label}
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
  preview,
  children,
  reviewLabel,
  confirmLabel,
  successMessage,
  onReload,
  reloadLabel = "Reload latest version",
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
  preview?: (values: Values) => ReactNode;
  children?: ReactNode;
  reviewLabel?: string;
  confirmLabel?: string;
  successMessage?: string | ((data: T) => string);
  onReload?: () => void;
  reloadLabel?: string;
}) {
  const { api } = useAuth();
  const flash = useContext(FlashContext);
  const contextReload = useContext(ReloadContext);
  const reload = onReload ?? contextReload;
  const initialValues = () => Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ""]));
  const [values, setValues] = useState<Values>(initialValues);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [ambiguous, setAmbiguous] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const lock = useRef(false);
  const latestInitial = useRef(initialValues);
  latestInitial.current = initialValues;
  const previousEtag = useRef(etag);
  const dirty = useRef(false);
  useEffect(()=>{onLockChange?.(!!attempt || pending);},[attempt,pending,onLockChange]);
  useEffect(() => {
    if (previousEtag.current === etag) return;
    previousEtag.current = etag;
    // A new server version invalidates any reviewed command built against the old one.
    if (!lock.current) {
      if (!dirty.current) setValues(latestInitial.current());
      setAttempt((current) => (ambiguous ? current : null));
      setStale(false);
      if (!ambiguous) setError(null);
    }
  }, [etag, ambiguous]);
  const review = reviewLabel ?? `Review ${title.charAt(0).toLowerCase()}${title.slice(1)}`;
  const confirm = confirmLabel ?? title;
  async function send(command: Attempt) {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError(null);
    setStale(false);
    setSuccess(null);
    try {
      const response = await api.requestWithMetadata<T>(
        command.path,
        command.options,
      );
      setAttempt(null);
      setAmbiguous(false);
      dirty.current = false;
      setValues(latestInitial.current());
      const message = typeof successMessage === "function" ? successMessage(response.data) : successMessage ?? `${title}: done.`;
      if (flash) flash(message);
      else setSuccess(message);
      onSuccess?.(response.data, response.etag);
    } catch (err) {
      setError(errorMessage(err));
      setStale(err instanceof ApiError && err.status === 412);
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
        setSuccess(null);
        setError(null);
        setStale(false);
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
        change={(name, value) => { dirty.current = true; setValues({ ...values, [name]: value }); }}
        disabled={!!attempt || pending}
      />
      {preview?.(values)}
      {error && (
        <div role="alert" className="command-error">
          <p>{stale && reload ? "This record changed since you loaded it. Reload the latest version, then review your change again." : error}</p>
          {stale && reload && (
            <button
              type="button"
              onClick={() => {
                setError(null);
                setStale(false);
                setAttempt(null);
                dirty.current = false;
                setValues(latestInitial.current());
                reload();
              }}
            >
              {reloadLabel}
            </button>
          )}
        </div>
      )}
      {success && <m.p initial={{opacity:.5,y:5}} animate={{opacity:1,y:0}} transition={{duration:.22}} role="status" className="command-receipt">{success}</m.p>}
      {pending && <p role="status">Sending…</p>}
      {attempt ? (
        <m.div initial={{opacity:.7}} animate={{opacity:1}} transition={{duration:.18}}
          className="hospital-confirm"
          role="group"
          aria-label={`Confirm: ${title}`}
        >
          <p>
            {ambiguous
              ? "The outcome is uncertain. Retry the original command with the same content and key before starting a different command. Keep this page open to retain the retry."
              : "Check the details above, then confirm."}
          </p>
          <button
            type="button"
            disabled={pending}
            onClick={() => void send(attempt)}
          >
            {ambiguous ? "Retry original command" : confirm}
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
          {review}
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
          <dd>{typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value)) ? <time dateTime={value} title={value}>{formatDateTime(value)}</time> : ["State","Status"].includes(key) && typeof value === "string" ? <StatusBadge tone={["confirmed","paid","finalized","completed","dispensed","resolved","success"].includes(value)?"success":["cancelled","declined","revoked"].includes(value)?"danger":"warning"}>{value.replaceAll("_"," ")}</StatusBadge> : value ?? "—"}</dd>
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
      <FlashArea resetKey={path}>
        <Resource<T> path={path} revision={revision}>
          {(item, etag, refresh) => (
            <div key={item.id}>
              {children(item, etag, refresh)}
            </div>
          )}
        </Resource>
      </FlashArea>
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
