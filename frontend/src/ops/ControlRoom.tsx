import { SurgeModeControls } from "./SurgeModeControls";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { StatusBadge } from "../components/StatusBadge";
import "./controlRoom.css";

const API_ROOT = "/api/v1/appointments/operations/control-room";

interface ServiceHealth {
  name: string;
  health: "healthy" | "degraded" | "no_data";
  healthy_instances: number;
  instance_count: number;
  request_rate_per_second: number | null;
  error_rate_percent: number | null;
  p95_latency_ms: number | null;
  recent_activity: "active" | "quiet" | "no_data";
}

interface MetricPoint {
  timestamp: number;
  value: number;
}

interface AlertItem {
  name: string;
  service: string | null;
  severity: "warning" | "critical" | "info";
}

interface ComponentMetric {
  owner?: string;
  outcome?: string;
  class?: string;
  state?: string;
  dependency?: string;
  value: number;
}

interface QueueMetric {
  name: string;
  ready: number;
  unacknowledged: number;
  consumers: number;
}

interface RecentEvent {
  action: string;
  previous_state: string | null;
  new_state: string | null;
  reason_code: string | null;
  occurred_at: string | null;
}

interface ControlRoomSummary {
  status: "available";
  observed_at: string;
  system: {
    health: "healthy" | "degraded" | "unknown";
    request_rate_per_second: number;
    error_rate_percent: number | null;
    p95_latency_ms: number | null;
    active_alert_count: number;
    surge_mode: { state: string; changed_at: string | null };
  };
  services: ServiceHealth[];
  trends: { request_rate: MetricPoint[]; error_rate: MetricPoint[] };
  alerts: AlertItem[];
  components: {
    rate_limiter: ComponentMetric[];
    cache: ComponentMetric[];
    consistent_hashing: {
      topology_epoch: ComponentMetric[];
      configured_nodes: ComponentMetric[];
    };
    circuit_breakers: ComponentMetric[];
    bulkheads: ComponentMetric[];
  };
  messaging: {
    queues: QueueMetric[];
    outbox_pending_by_owner: ComponentMetric[];
    outbox_oldest_seconds_by_owner: ComponentMetric[];
    publisher_failures_15m: ComponentMetric[];
    consumer_processed_15m: ComponentMetric[];
    delivery_p95_seconds: ComponentMetric[];
  };
  recent_events: { available: boolean; items: RecentEvent[] };
}

interface TraceSummary {
  trace_id: string;
  service: string;
  operation: string;
  duration_ms: number;
  start_time_unix_nano: number;
}

interface TraceSpan {
  service: string;
  operation: string;
  start_time_unix_nano: number;
  duration_ms: number;
}

function number(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "No data"
    : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function time(value: string | null | undefined): string {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

function localTimeFromNanos(value: number): string {
  const date = new Date(value / 1_000_000);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString();
}

function toneForHealth(value: string): "success" | "warning" | "danger" | "neutral" {
  if (value === "healthy" || value === "NORMAL") return "success";
  if (value === "degraded" || value === "SURGE" || value === "RECOVERY") return "warning";
  if (value === "unknown" || value === "no_data") return "neutral";
  return "danger";
}

function MetricCard({ label, value, detail, tone = "neutral" }: {
  label: string;
  value: string;
  detail?: string;
  tone?: "success" | "warning" | "danger" | "neutral";
}) {
  return (
    <article className={`ops-metric-card ops-metric-card--${tone}`}>
      <p className="ops-metric-label">{label}</p>
      <strong className="ops-metric-value">{value}</strong>
      {detail ? <span className="ops-metric-detail">{detail}</span> : null}
    </article>
  );
}

function TrendChart({ title, unit, points, description }: {
  title: string;
  unit: string;
  points: MetricPoint[];
  description: string;
}) {
  const path = useMemo(() => {
    if (!points.length) return "";
    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return points.map((point, index) => {
      const x = points.length === 1 ? 120 : (index / (points.length - 1)) * 240;
      const y = 40 - ((point.value - min) / range) * 32;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [points]);

  return (
    <article className="ops-panel ops-trend-panel">
      <div className="ops-panel-heading">
        <div><h3>{title}</h3><p>{description}</p></div>
        <span className="ops-chart-unit">{unit}</span>
      </div>
      {points.length ? (
        <svg className="ops-trend-chart" viewBox="0 0 240 48" role="img" aria-label={`${title} over the last 30 minutes`}>
          <path d="M0,44 H240" className="ops-chart-axis" />
          <path d={path} className="ops-chart-line" />
        </svg>
      ) : <p className="ops-no-data">No metric samples in this window.</p>}
      <div className="ops-chart-caption"><span>30 minutes ago</span><span>Now</span></div>
    </article>
  );
}

function EmptyRows({ children }: { children: string }) {
  return <p className="ops-empty-row">{children}</p>;
}

export function ControlRoom({ workspaceBasePath }: { workspaceBasePath: "/ops" | "/admin" }) {
  const { api } = useAuth();
  const [summary, setSummary] = useState<ControlRoomSummary | null>(null);
  const [serviceDetailsOpen,setServiceDetailsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await api.request<ControlRoomSummary>(`${API_ROOT}/summary`, { signal });
      setSummary(next);
      setError(false);
    } catch (cause) {
      if (cause instanceof Error && cause.name === "AbortError") return;
      setError(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refresh]);

  const system = summary?.system;
  const trendRates = summary?.trends.request_rate ?? [];
  const trendErrors = summary?.trends.error_rate ?? [];

  return (
    <section className="ops-dashboard reference-operations" aria-labelledby="control-room-title">
      <header className="ops-page-header">
        <div>
          <p className="eyebrow">Operations · Live telemetry</p>
          <h1 id="control-room-title">Control Room</h1>
          <p className="ops-page-description">Service health, delivery signals, and recent operational changes.</p>
        </div>
        <div className="ops-header-actions">
          <span className="ops-updated">{summary ? `Updated ${time(summary.observed_at)}` : "Waiting for monitoring"}</span>
          <button className="ops-refresh-button" type="button" onClick={() => { setLoading(true); void refresh(); }} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error ? (
        <div className="ops-monitoring-banner" role="status">
          <strong>Monitoring data is temporarily unavailable.</strong>
          <span>Hospital services continue to operate independently of this dashboard.</span>
          <button type="button" onClick={() => { setLoading(true); void refresh(); }}>Try again</button>
        </div>
      ) : null}

      {!summary && loading ? <p className="ops-loading" role="status">Loading live monitoring data…</p> : null}
      {summary ? (
        <>
          <div className="ops-metric-grid" aria-label="System overview">
            <MetricCard label="System status" value={system?.health ?? "No data"} tone={toneForHealth(system?.health ?? "unknown")} />
            <MetricCard label="Requests / second" value={number(system?.request_rate_per_second, 2)} detail="5 minute rate" />
            <MetricCard label="HTTP 5xx rate" value={system?.error_rate_percent === null ? "No data" : `${number(system?.error_rate_percent)}%`} tone={(system?.error_rate_percent ?? 0) > 5 ? "danger" : "neutral"} />
            <MetricCard label="P95 latency" value={system?.p95_latency_ms === null ? "No data" : `${number(system?.p95_latency_ms)} ms`} />
            <MetricCard label="Active alerts" value={String(system?.active_alert_count ?? 0)} tone={(system?.active_alert_count ?? 0) > 0 ? "warning" : "success"} />
            <MetricCard label="Surge Mode" value={system?.surge_mode.state ?? "UNKNOWN"} detail={system?.surge_mode.changed_at ? `Since ${time(system.surge_mode.changed_at)}` : "Shared admission state"} tone={toneForHealth(system?.surge_mode.state ?? "unknown")} />
          </div>

          <section className="ops-service-map" aria-labelledby="service-map-title"><header><h2 id="service-map-title">Hospital Service Map</h2><small>Live service topology · Not a bed census</small></header><div className="ops-map-rooms">{summary.services.map(service=><button type="button" aria-label={`Inspect ${service.name} service`} aria-controls="detailed-service-health" onClick={()=>setServiceDetailsOpen(true)} className={`ops-map-room ops-map-room--${service.health}`} key={service.name}><strong>{service.name}</strong><StatusBadge tone={toneForHealth(service.health)}>{service.health.replaceAll('_',' ')}</StatusBadge><span>{service.healthy_instances} / {service.instance_count} ready</span><small>{number(service.request_rate_per_second,2)} requests / sec</small></button>)}</div><footer>Readiness and measurements from each owning service.</footer></section>
          <div className="ops-trend-grid">
            <TrendChart title="Request throughput" unit="requests / sec" points={trendRates} description="Collected from service request counters." />
            <TrendChart title="HTTP 5xx rate" unit="percent" points={trendErrors} description="Computed from observed HTTP status classes." />
          </div>

          <details className="ops-service-details" id="detailed-service-health" open={serviceDetailsOpen} onToggle={e=>setServiceDetailsOpen(e.currentTarget.open)}><summary>Detailed service health and replica measurements</summary><section className="ops-panel">
            <div className="ops-panel-heading">
              <div><h2>Service health</h2><p>Readiness is probed per running instance; service values aggregate replicas.</p></div>
            </div>
            <div className="ops-table-wrap" tabIndex={0} role="region" aria-label="Service health table">
              <table className="ops-table">
                <thead><tr><th scope="col">Service</th><th scope="col">Health</th><th scope="col">Instances</th><th scope="col">Req/s</th><th scope="col">5xx</th><th scope="col">P95</th><th scope="col">Recent activity</th></tr></thead>
                <tbody>
                  {summary.services.map((service) => (
                    <tr key={service.name}>
                      <th scope="row">{service.name}</th>
                      <td><StatusBadge tone={toneForHealth(service.health)}>{service.health.replace("_", " ")}</StatusBadge></td>
                      <td>{service.instance_count ? `${service.healthy_instances}/${service.instance_count} ready` : "No data"}</td>
                      <td>{number(service.request_rate_per_second, 2)}</td>
                      <td>{service.error_rate_percent === null ? "No data" : `${number(service.error_rate_percent)}%`}</td>
                      <td>{service.p95_latency_ms === null ? "No data" : `${number(service.p95_latency_ms)} ms`}</td>
                      <td>{service.recent_activity.replace("_", " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          </details><div className="ops-two-column ops-component-and-alerts">
            <section className="ops-panel">
              <div className="ops-panel-heading"><div><h2>Distributed components</h2><p>Only recorded component metrics are shown.</p></div></div>
              <div className="ops-component-grid">
                <ComponentList title="Rate limiting" items={summary.components.rate_limiter} primary="owner" secondary="outcome" />
                <ComponentList title="Cache" items={summary.components.cache} primary="owner" secondary="outcome" />
                <ComponentList title="Hash topology epoch" items={summary.components.consistent_hashing.topology_epoch} primary="owner" valueLabel="epoch" />
                <ComponentList title="Configured cache nodes" items={summary.components.consistent_hashing.configured_nodes} primary="owner" valueLabel="nodes" />
                <ComponentList title="Circuit breakers" items={summary.components.circuit_breakers} primary="dependency" secondary="state" />
                <ComponentList title="Bulkhead occupancy" items={summary.components.bulkheads} primary="dependency" secondary="owner" />
              </div>
            </section>
            <section className="ops-panel">
              <div className="ops-panel-heading"><div><h2>Operational alerts</h2><p>Prometheus rule evaluations.</p></div></div>
              {summary.alerts.length ? (
                <ul className="ops-alert-list">
                  {summary.alerts.map((alert, index) => <li key={`${alert.name}-${alert.service ?? "all"}-${index}`}><StatusBadge tone={alert.severity === "critical" ? "danger" : "warning"}>{alert.severity}</StatusBadge><span><strong>{alert.name}</strong><small>{alert.service ?? "System"}</small></span></li>)}
                </ul>
              ) : <EmptyRows>There are no firing alerts.</EmptyRows>}
              <section className="ops-runtime-signals"><h3>Infrastructure signals</h3><dl><div><dt>RabbitMQ queues observed</dt><dd>{summary.messaging.queues.length||"No data"}</dd></div><div><dt>Messages ready</dt><dd>{summary.messaging.queues.length?summary.messaging.queues.reduce((total,q)=>total+q.ready,0):"No data"}</dd></div><div><dt>Redis cache observations</dt><dd>{summary.components.cache.length?summary.components.cache.map(m=>`${m.outcome??"sample"}: ${number(m.value,2)}`).join(" · "):"No data"}</dd></div></dl><nav aria-label="Monitoring tools"><Link to={`${workspaceBasePath}/traces`}>Distributed traces →</Link>{import.meta.env.DEV&&<a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer">Local Grafana →</a>}</nav><small>Prometheus metrics · Missing samples remain unavailable.</small></section>
            </section>
          </div>

          <details className="ops-delivery-details"><summary>Event delivery and operational audit</summary><div className="ops-two-column ops-messaging-and-events">
            <section className="ops-panel">
              <div className="ops-panel-heading"><div><h2>Event delivery</h2><p>RabbitMQ queue state and producer-owned outbox measurements.</p></div></div>
              <div className="ops-table-wrap" tabIndex={0} role="region" aria-label="Event delivery table">
                <table className="ops-table ops-queue-table">
                  <thead><tr><th scope="col">Queue</th><th scope="col">Ready</th><th scope="col">Unacked</th><th scope="col">Consumers</th></tr></thead>
                  <tbody>{summary.messaging.queues.map((queue) => <tr key={queue.name}><th scope="row">{queue.name.replace("pulsegrid.", "")}</th><td>{queue.ready}</td><td>{queue.unacknowledged}</td><td>{queue.consumers}</td></tr>)}</tbody>
                </table>
              </div>
              <ComponentList title="Pending outbox" items={summary.messaging.outbox_pending_by_owner} primary="owner" valueLabel="pending" />
              <ComponentList title="Oldest pending age" items={summary.messaging.outbox_oldest_seconds_by_owner} primary="owner" valueLabel="seconds" />
              <ComponentList title="Publisher failures · 15m" items={summary.messaging.publisher_failures_15m} primary="owner" secondary="outcome" />
            </section>
            <section className="ops-panel">
              <div className="ops-panel-heading">
                <div><h2>Recent operational events</h2><p>Appointment Surge Mode transitions from its existing audit chain.</p></div>
              </div>
              {summary.recent_events.available ? summary.recent_events.items.length ? (
                <ul className="ops-event-list">
                  {summary.recent_events.items.map((event, index) => <li key={`${event.action}-${event.occurred_at ?? index}`}><span className="ops-event-mark" aria-hidden="true" /><span><strong>{event.previous_state ?? "Unknown"} → {event.new_state ?? "Unknown"}</strong><small>{event.reason_code ?? event.action} · {time(event.occurred_at)}</small></span></li>)}
                </ul>
              ) : <EmptyRows>No recent Surge Mode transitions.</EmptyRows> : <EmptyRows>Operational audit events are unavailable.</EmptyRows>}
              <Link className="ops-text-link" to={`${workspaceBasePath}/traces`}>Explore recent traces <span aria-hidden="true">→</span></Link>
            </section>
          </div>
          </details><p className="ops-footnote">Metrics update every 30 seconds. Missing measurements remain marked as no data.</p>
        </>
      ) : null}
      <SurgeModeControls onChange={()=>void refresh()}/>
    </section>
  );
}

function ComponentList({ title, items, primary, secondary, valueLabel = "rate" }: {
  title: string;
  items: ComponentMetric[];
  primary: keyof ComponentMetric;
  secondary?: keyof ComponentMetric;
  valueLabel?: string;
}) {
  return (
    <div className="ops-component-list">
      <h3>{title}</h3>
      {items.length ? <ul>{items.slice(0, 8).map((item, index) => <li key={`${String(item[primary])}-${String(secondary ? item[secondary] : "")}-${index}`}><span>{item[primary] ?? "Component"}{secondary && item[secondary] ? ` · ${item[secondary]}` : ""}</span><strong>{number(item.value, 2)} <small>{valueLabel}</small></strong></li>)}</ul> : <p className="ops-no-data">No samples collected.</p>}
    </div>
  );
}

export function TraceExplorer() {
  const { api } = useAuth();
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [spans, setSpans] = useState<TraceSpan[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await api.request<{ traces: TraceSummary[] }>(`${API_ROOT}/traces`, { signal });
      setTraces(response.traces);
      setError(false);
    } catch (cause) {
      if (cause instanceof Error && cause.name === "AbortError") return;
      setError(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(), 60_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);

  const openTrace = useCallback(async (traceId: string) => {
    setSelected(traceId);
    setDetailLoading(true);
    try {
      const response = await api.request<{ spans: TraceSpan[] }>(`${API_ROOT}/traces/${traceId}`);
      setSpans(response.spans);
      setError(false);
    } catch {
      setSpans([]);
      setError(true);
    } finally {
      setDetailLoading(false);
    }
  }, [api]);

  return (
    <section className="ops-dashboard ops-trace-desk" aria-labelledby="trace-explorer-title">
      <header className="ops-page-header">
        <div><p className="eyebrow">Operations · Distributed traces</p><h1 id="trace-explorer-title">Trace Explorer</h1><p className="ops-page-description">Recent trace summaries from the last hour. Sensitive span attributes are not returned.</p></div>
        <button className="ops-refresh-button" type="button" onClick={() => { setLoading(true); void load(); }} disabled={loading}>Refresh traces</button>
      </header>
      {error ? <div className="ops-monitoring-banner" role="status"><strong>Trace data is temporarily unavailable.</strong><span>Service requests continue if the trace backend is offline.</span></div> : null}
      <div className="ops-trace-layout">
        <section className="ops-panel" aria-label="Recent traces">
          <div className="ops-panel-heading"><div><h2>Recent traces</h2><p>Service and operation summaries are allowlisted by the server.</p></div></div>
          {loading && !traces.length ? <p className="ops-loading" role="status">Loading recent traces…</p> : null}
          {!loading && !traces.length && !error ? <EmptyRows>No traces found in the last hour.</EmptyRows> : null}
          {traces.length ? <ul className="ops-trace-list">{traces.map((trace) => <li key={trace.trace_id}><button className={selected === trace.trace_id ? "ops-trace-row ops-trace-row--selected" : "ops-trace-row"} onClick={() => void openTrace(trace.trace_id)} type="button"><span><strong>{trace.operation}</strong><small>{trace.service} · {localTimeFromNanos(trace.start_time_unix_nano)}</small></span><span className="ops-trace-duration">{number(trace.duration_ms)} ms</span></button></li>)}</ul> : null}
        </section>
        <section className="ops-panel" aria-label="Selected trace details">
          <div className="ops-panel-heading"><div><h2>Trace details</h2><p>{selected ? `Trace ID ${selected}` : "Select a trace to inspect its service path."}</p></div></div>
          {detailLoading ? <p className="ops-loading" role="status">Loading trace spans…</p> : null}
          {!selected && !detailLoading ? <EmptyRows>No trace selected.</EmptyRows> : null}
          {selected && !detailLoading && !spans.length ? <EmptyRows>No safe span details are available.</EmptyRows> : null}
          {spans.length ? <ol className="ops-span-list">{spans.map((span, index) => <li key={`${span.service}-${span.start_time_unix_nano}-${index}`}><span className="ops-span-rail" aria-hidden="true" /><span className="ops-span-copy"><strong>{span.operation}</strong><small>{span.service} · {number(span.duration_ms)} ms</small></span></li>)}</ol> : null}
        </section>
      </div>
      <p className="ops-footnote">Trace results include safe service, operation, and timing fields only.</p>
    </section>
  );
}
