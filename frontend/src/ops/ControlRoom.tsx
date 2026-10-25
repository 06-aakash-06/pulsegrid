import { SurgeModeControls } from "./SurgeModeControls";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { StatusBadge } from "../components/StatusBadge";
import { DepartmentIcon } from "../design/DepartmentIcon";
import { formatDateTime } from "../hospital/ui";
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
  return formatDateTime(value);
}

function localTimeFromNanos(value: number): string {
  return formatDateTime(value / 1_000_000);
}

function toneForHealth(value: string): "success" | "warning" | "danger" | "neutral" {
  if (value === "healthy" || value === "NORMAL") return "success";
  if (value === "degraded" || value === "SURGE" || value === "RECOVERY") return "warning";
  if (value === "unknown" || value === "no_data") return "neutral";
  return "danger";
}

function trendOf(points: MetricPoint[]): { arrow: string; label: string } | null {
  if (points.length < 4) return null;
  const head = points.slice(0, 3).reduce((sum, point) => sum + point.value, 0) / 3;
  const tail = points.slice(-3).reduce((sum, point) => sum + point.value, 0) / 3;
  const change = head === 0 ? (tail === 0 ? 0 : 1) : (tail - head) / Math.abs(head);
  if (change > 0.05) return { arrow: "↑", label: "Rising over the window" };
  if (change < -0.05) return { arrow: "↓", label: "Falling over the window" };
  return { arrow: "→", label: "Steady over the window" };
}

function KpiCard({ label, value, unit, detail, points, tone = "neutral" }: {
  label: string;
  value: string;
  unit?: string;
  detail: string;
  points?: MetricPoint[];
  tone?: "success" | "warning" | "danger" | "neutral";
}) {
  const trend = points ? trendOf(points) : null;
  return (
    <article className={`ops-kpi ops-kpi--${tone}`}>
      <p className="ops-kpi__label"><span className="ops-kpi__icon" aria-hidden="true">{({ Throughput: "↗", "p95 latency": "◷", "HTTP 5xx rate": "!", "RabbitMQ backlog": "≋", "Redis hit rate": "◈" } as Record<string, string>)[label]}</span>{label}</p>
      <p className="ops-kpi__value"><strong>{value}</strong>{unit && value !== "No data" ? <span>{unit}</span> : null}</p>
      <p className="ops-kpi__detail">
        {trend ? <span className="ops-kpi__trend" title={trend.label}><span aria-hidden="true">{trend.arrow}</span><span className="sr-only">{trend.label}</span></span> : null}
        {detail}
      </p>
    </article>
  );
}

function segments(points: MetricPoint[]) {
  if (points.length < 2) return [points];
  const gaps = points.slice(1).map((point, index) => point.timestamp - points[index].timestamp).sort((a, b) => a - b);
  const step = gaps[Math.floor(gaps.length / 2)] || 1;
  const runs: MetricPoint[][] = [[points[0]]];
  points.slice(1).forEach((point, index) => {
    if (point.timestamp - points[index].timestamp > step * 1.5) runs.push([point]);
    else runs[runs.length - 1].push(point);
  });
  return runs;
}

function TrendChart({ title, unit, points, description }: {
  title: string;
  unit: string;
  points: MetricPoint[];
  description: string;
}) {
  const runs = useMemo(() => segments(points), [points]);
  const gapCount = runs.length - 1;
  const paths = useMemo(() => {
    if (!points.length) return [];
    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const first = points[0].timestamp;
    const span = points[points.length - 1].timestamp - first || 1;
    return runs.map((run) => run.map((point, index) => {
      const x = ((point.timestamp - first) / span) * 240;
      const y = 40 - ((point.value - min) / range) * 32;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" "));
  }, [points, runs]);

  return (
    <article className="ops-panel ops-trend-panel">
      <div className="ops-panel-heading">
        <div><h3>{title}</h3><p>{description}</p></div>
        <span className="ops-chart-unit">{unit}</span>
      </div>
      {points.length ? (
        <svg className="ops-trend-chart" viewBox="0 0 240 48" role="img" aria-label={`${title} over the last 30 minutes${gapCount ? `, with ${gapCount} missing sample${gapCount === 1 ? "" : "s"}` : ""}`}>
          <path d="M0,44 H240" className="ops-chart-axis" />
          {paths.map((path, index) => <path key={index} d={path} className="ops-chart-line" />)}
        </svg>
      ) : <p className="ops-no-data">No metric samples in this window.</p>}
      <div className="ops-chart-caption"><span>30 minutes ago</span>{gapCount ? <span>Gap = no data</span> : null}<span>Now</span></div>
      {points.length ? (
        <details className="ops-chart-data">
          <summary>View data</summary>
          <div className="ops-table-wrap" tabIndex={0} role="region" aria-label={`${title} samples`}>
            <table className="ops-table">
              <caption className="sr-only">{title} samples ({unit})</caption>
              <thead><tr><th scope="col">Time</th><th scope="col">{unit}</th></tr></thead>
              <tbody>{points.map((point) => <tr key={point.timestamp}><th scope="row">{formatDateTime(point.timestamp * 1000)}</th><td>{number(point.value, 2)}</td></tr>)}</tbody>
            </table>
          </div>
        </details>
      ) : null}
    </article>
  );
}

function EmptyRows({ children }: { children: string }) {
  return <p className="ops-empty-row">{children}</p>;
}

export function ControlRoom({ workspaceBasePath }: { workspaceBasePath: "/ops" | "/admin" }) {
  const { api } = useAuth();
  const [summary, setSummary] = useState<ControlRoomSummary | null>(null);
  const [inspected, setInspected] = useState<string | null>(null);
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
  const services = summary?.services ?? [];
  const ready = services.filter((service) => service.instance_count > 0 && service.healthy_instances === service.instance_count).length;
  const queues = summary?.messaging.queues ?? [];
  const backlog = queues.length ? queues.reduce((total, queue) => total + queue.ready + queue.unacknowledged, 0) : null;
  const cache = summary?.components.cache ?? [];
  const hits = cache.filter((item) => item.outcome === "hit").reduce((total, item) => total + item.value, 0);
  const misses = cache.filter((item) => item.outcome === "miss").reduce((total, item) => total + item.value, 0);
  const hitRate = hits + misses > 0 ? (hits / (hits + misses)) * 100 : null;
  const percent = (value: number | null | undefined) => value === null || value === undefined ? "No data" : `${number(value)}%`;
  const ms = (value: number | null | undefined) => value === null || value === undefined ? "No data" : `${number(value, 0)} ms`;
  const inspectedService = services.find((service) => service.name === inspected);

  return (
    <section className="ops-dashboard ops-console" aria-labelledby="control-room-title">
      <header className="ops-sign">
        <span className="ops-sign__mark" aria-hidden="true"><DepartmentIcon department="control" /></span>
        <div className="ops-sign__name">
          <h1 id="control-room-title">Control Room</h1>
          <p>Distributed-systems telemetry · not a hospital census</p>
          <p className="ops-updated">{summary ? `Updated ${time(summary.observed_at)}` : "Waiting for monitoring"} <button className="ops-refresh-button" type="button" onClick={() => { setLoading(true); void refresh(); }} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button></p>
        </div>
        <dl className="ops-wall-monitor" aria-label="Headline figures">
          <div><dt>Services ready</dt><dd>{summary ? `${ready}/${services.length}` : "No data"}</dd></div>
          <div><dt>p95 latency</dt><dd>{summary ? ms(system?.p95_latency_ms) : "No data"}</dd></div>
          <div><dt>HTTP 5xx</dt><dd>{summary ? percent(system?.error_rate_percent) : "No data"}</dd></div>
          <div data-alert={(summary?.alerts.length ?? 0) > 0}><dt>Firing alerts</dt><dd>{summary ? String(summary.alerts.length) : "No data"}</dd></div>
        </dl>
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
          <div className="ops-kpi-row" aria-label="System overview">
            <KpiCard label="Throughput" value={number(system?.request_rate_per_second, 2)} unit="req/s" detail="5 minute rate" points={trendRates} />
            <KpiCard label="p95 latency" value={system?.p95_latency_ms === null || system?.p95_latency_ms === undefined ? "No data" : number(system.p95_latency_ms, 0)} unit="ms" detail={system?.p95_latency_ms === null || system?.p95_latency_ms === undefined ? "No latency samples in this window" : "95th percentile · 5 minute window"} tone={(system?.p95_latency_ms ?? 0) > 150 ? "warning" : "neutral"} />
            <KpiCard label="HTTP 5xx rate" value={system?.error_rate_percent === null || system?.error_rate_percent === undefined ? "No data" : number(system.error_rate_percent)} unit="%" detail="Observed status classes" points={trendErrors} tone={(system?.error_rate_percent ?? 0) > 5 ? "danger" : "neutral"} />
            <KpiCard label="RabbitMQ backlog" value={backlog === null ? "No data" : String(backlog)} unit="msgs" detail={`${queues.length} queues · ready + unacked`} tone={(backlog ?? 0) > 50 ? "warning" : "neutral"} />
            <KpiCard label="Redis hit rate" value={hitRate === null ? "No data" : number(hitRate)} unit="%" detail={hitRate === null ? "No cache samples" : `${number(hits, 2)} hits · ${number(misses, 2)} misses /s`} />
          </div>

          <div className="ops-console-grid">
            <section className="ops-topology" aria-labelledby="service-map-title">
              <header><h2 id="service-map-title">Service topology</h2><small>Seven owner services · readiness probed per replica</small></header>
              <div className="ops-tiles">
                {services.map((service) => (
                  <button
                    type="button"
                    key={service.name}
                    className={`ops-tile ops-tile--${service.health}`}
                    aria-label={`Inspect ${service.name} service`}
                    aria-pressed={inspected === service.name}
                    aria-controls="ops-service-inspector"
                    onClick={() => setInspected(inspected === service.name ? null : service.name)}
                  >
                    <strong>{service.name}</strong>
                    <StatusBadge tone={toneForHealth(service.health)}>{service.health.replaceAll("_", " ")}</StatusBadge>
                    <span className="ops-tile__metric"><span>p95</span>{ms(service.p95_latency_ms)}</span>
                    <span className="ops-tile__metric"><span>Replicas</span>{service.instance_count ? `${service.healthy_instances}/${service.instance_count} ready` : "No data"}</span>
                  </button>
                ))}
              </div>
              <div id="ops-service-inspector" className="ops-inspector" aria-live="polite">
                {inspectedService ? (
                  <table className="ops-table">
                    <caption>{inspectedService.name} replica measurements</caption>
                    <thead><tr><th scope="col">Replicas ready</th><th scope="col">Req/s</th><th scope="col">5xx</th><th scope="col">p95</th><th scope="col">Activity</th></tr></thead>
                    <tbody><tr><td>{inspectedService.healthy_instances} of {inspectedService.instance_count}</td><td>{number(inspectedService.request_rate_per_second, 2)}</td><td>{percent(inspectedService.error_rate_percent)}</td><td>{ms(inspectedService.p95_latency_ms)}</td><td>{inspectedService.recent_activity.replace("_", " ")}</td></tr></tbody>
                  </table>
                ) : <p>Select a service tile to inspect its replica measurements.</p>}
              </div>
              <details className="ops-service-details" id="detailed-service-health"><summary>All services table</summary>
                <div className="ops-table-wrap" tabIndex={0} role="region" aria-label="Service health table">
                  <table className="ops-table">
                    <thead><tr><th scope="col">Service</th><th scope="col">Health</th><th scope="col">Instances</th><th scope="col">Req/s</th><th scope="col">5xx</th><th scope="col">P95</th><th scope="col">Recent activity</th></tr></thead>
                    <tbody>
                      {services.map((service) => (
                        <tr key={service.name}>
                          <th scope="row">{service.name}</th>
                          <td><StatusBadge tone={toneForHealth(service.health)}>{service.health.replace("_", " ")}</StatusBadge></td>
                          <td>{service.instance_count ? `${service.healthy_instances}/${service.instance_count} ready` : "No data"}</td>
                          <td>{number(service.request_rate_per_second, 2)}</td>
                          <td>{percent(service.error_rate_percent)}</td>
                          <td>{ms(service.p95_latency_ms)}</td>
                          <td>{service.recent_activity.replace("_", " ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </section>

            <aside className="ops-side">
              <section className="ops-panel ops-alerts" aria-labelledby="ops-alerts-title">
                <div className="ops-panel-heading"><div><h2 id="ops-alerts-title">Live alerts</h2><p>Prometheus rule evaluations.</p></div></div>
                {summary.alerts.length ? (
                  <ul className="ops-alert-list">
                    {summary.alerts.map((alert, index) => <li key={`${alert.name}-${alert.service ?? "all"}-${index}`} data-severity={alert.severity}><StatusBadge tone={alert.severity === "critical" ? "danger" : alert.severity === "warning" ? "warning" : "neutral"}>{alert.severity}</StatusBadge><span><strong>{alert.name}</strong><small>{alert.service ?? "System"}</small></span></li>)}
                  </ul>
                ) : <EmptyRows>There are no firing alerts.</EmptyRows>}
              </section>
              <section className="ops-panel ops-bus" aria-labelledby="ops-bus-title">
                <div className="ops-panel-heading"><div><h2 id="ops-bus-title">Message bus &amp; cache</h2><p>RabbitMQ queues and Redis samples.</p></div></div>
                {queues.length ? (
                  <div className="ops-table-wrap" tabIndex={0} role="region" aria-label="RabbitMQ queues">
                    <table className="ops-table ops-queue-table">
                      <thead><tr><th scope="col">Queue</th><th scope="col">Ready</th><th scope="col">Unacked</th><th scope="col">Consumers</th></tr></thead>
                      <tbody>{queues.map((queue) => <tr key={queue.name}><th scope="row">{queue.name.replace("pulsegrid.", "")}</th><td>{queue.ready}</td><td>{queue.unacknowledged}</td><td>{queue.consumers}</td></tr>)}</tbody>
                    </table>
                  </div>
                ) : <EmptyRows>No RabbitMQ queue samples.</EmptyRows>}
                <ComponentList title="Redis cache samples" items={cache} primary="owner" secondary="outcome" />
                <nav aria-label="Monitoring tools" className="ops-tools"><Link to={`${workspaceBasePath}/traces`}>Distributed traces →</Link>{import.meta.env.DEV&&<a href="http://127.0.0.1:3000" target="_blank" rel="noreferrer">Local Grafana →</a>}</nav>
              </section>
            </aside>
          </div>

          <div className="ops-bottom">
            <div className="ops-trend-grid">
              <TrendChart title="Request throughput" unit="requests / sec" points={trendRates} description="Collected from service request counters." />
              <TrendChart title="HTTP 5xx rate" unit="percent" points={trendErrors} description="Computed from observed HTTP status classes." />
            </div>
            <section className="ops-panel ops-surge" aria-labelledby="ops-surge-title">
              <div className="ops-panel-heading"><div><h2 id="ops-surge-title">Surge Mode</h2><p>Shared admission state for Appointment.</p></div></div>
              <p className="ops-surge__state"><StatusBadge tone={toneForHealth(system?.surge_mode.state ?? "unknown")}>{system?.surge_mode.state ?? "UNKNOWN"}</StatusBadge><span>{system?.surge_mode.changed_at ? `Since ${time(system.surge_mode.changed_at)}` : "Change time not reported"}</span></p>
              <SurgeModeControls onChange={()=>void refresh()}/>
            </section>
          </div>

          <details className="ops-delivery-details"><summary>Distributed components, event delivery and operational audit</summary><div className="ops-two-column ops-messaging-and-events">
            <section className="ops-panel">
              <div className="ops-panel-heading"><div><h2>Distributed components</h2><p>Only recorded component metrics are shown.</p></div></div>
              <div className="ops-component-grid">
                <ComponentList title="Rate limiting" items={summary.components.rate_limiter} primary="owner" secondary="outcome" />
                <ComponentList title="Hash topology epoch" items={summary.components.consistent_hashing.topology_epoch} primary="owner" valueLabel="epoch" />
                <ComponentList title="Configured cache nodes" items={summary.components.consistent_hashing.configured_nodes} primary="owner" valueLabel="nodes" />
                <ComponentList title="Circuit breakers" items={summary.components.circuit_breakers} primary="dependency" secondary="state" />
                <ComponentList title="Bulkhead occupancy" items={summary.components.bulkheads} primary="dependency" secondary="owner" />
              </div>
            </section>
            <section className="ops-panel">
              <div className="ops-panel-heading"><div><h2>Event delivery</h2><p>Producer-owned outbox measurements.</p></div></div>
              <ComponentList title="Pending outbox" items={summary.messaging.outbox_pending_by_owner} primary="owner" valueLabel="pending" />
              <ComponentList title="Oldest pending age" items={summary.messaging.outbox_oldest_seconds_by_owner} primary="owner" valueLabel="seconds" />
              <ComponentList title="Publisher failures · 15m" items={summary.messaging.publisher_failures_15m} primary="owner" secondary="outcome" />
              <h3>Recent operational events</h3>
              {summary.recent_events.available ? summary.recent_events.items.length ? (
                <ul className="ops-event-list">
                  {summary.recent_events.items.map((event, index) => <li key={`${event.action}-${event.occurred_at ?? index}`}><span className="ops-event-mark" aria-hidden="true" /><span><strong>{event.previous_state ?? "Unknown"} → {event.new_state ?? "Unknown"}</strong><small>{event.reason_code ?? event.action} · {time(event.occurred_at)}</small></span></li>)}
                </ul>
              ) : <EmptyRows>No recent Surge Mode transitions.</EmptyRows> : <EmptyRows>Operational audit events are unavailable.</EmptyRows>}
            </section>
          </div>
          </details><p className="ops-footnote">Metrics update every 30 seconds. Missing measurements remain marked as no data.</p>
        </>
      ) : <SurgeModeControls onChange={()=>void refresh()}/>}
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
      {items.length ? <ul>{items.slice(0, 8).map((item, index) => <li key={`${String(item[primary])}-${String(secondary ? item[secondary] : "")}-${index}`}><span title={`${String(item[primary] ?? "Component")}${secondary && item[secondary] ? ` · ${item[secondary]}` : ""}`}>{item[primary] ?? "Component"}{secondary && item[secondary] ? ` · ${item[secondary]}` : ""}</span><strong>{number(item.value, 2)} <small>{valueLabel}</small></strong></li>)}</ul> : <p className="ops-no-data">No samples collected.</p>}
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

  const traceStart = spans.length ? Math.min(...spans.map((span) => span.start_time_unix_nano)) : 0;
  const traceEnd = spans.length ? Math.max(...spans.map((span) => span.start_time_unix_nano + span.duration_ms * 1_000_000)) : 1;
  const traceSpan = traceEnd - traceStart || 1;
  const selectedTrace = traces.find((trace) => trace.trace_id === selected);
  return (
    <section className="ops-dashboard ops-console ops-trace-desk" aria-labelledby="trace-explorer-title">
      <header className="ops-sign">
        <span className="ops-sign__mark" aria-hidden="true"><DepartmentIcon department="control" /></span>
        <div className="ops-sign__name"><h1 id="trace-explorer-title">Trace Explorer</h1><p>Recent trace summaries from the last hour. Sensitive span attributes are not returned.</p></div>
        <button className="ops-refresh-button" type="button" onClick={() => { setLoading(true); void load(); }} disabled={loading}>Refresh traces</button>
      </header>
      {error ? <div className="ops-monitoring-banner" role="status"><strong>Trace data is temporarily unavailable.</strong><span>Service requests continue if the trace backend is offline.</span></div> : null}
      <div className={`ops-trace-layout${selected ? " ops-trace-layout--selected" : ""}`}>
        <section className="ops-panel" aria-label="Recent traces">
          <div className="ops-panel-heading"><div><h2>Recent traces</h2><p>Service and operation summaries are allowlisted by the server.</p></div></div>
          {loading && !traces.length ? <p className="ops-loading" role="status">Loading recent traces…</p> : null}
          {!loading && !traces.length && !error ? <EmptyRows>No traces found in the last hour.</EmptyRows> : null}
          {traces.length ? <ul className="ops-trace-list">{traces.map((trace) => <li key={trace.trace_id}><button className={selected === trace.trace_id ? "ops-trace-row ops-trace-row--selected" : "ops-trace-row"} aria-pressed={selected === trace.trace_id} onClick={() => void openTrace(trace.trace_id)} type="button"><span><strong title={trace.operation}>{trace.operation}</strong><small>{trace.service} · {localTimeFromNanos(trace.start_time_unix_nano)}</small></span><span className="ops-trace-duration">{number(trace.duration_ms)} ms</span></button></li>)}</ul> : null}
        </section>
        <section className="ops-panel ops-trace-detail" aria-label="Selected trace details">
          {!selected && !detailLoading ? (
            <p className="ops-trace-empty">Select a trace to see its service path and span timings.</p>
          ) : (
            <>
              <div className="ops-panel-heading"><div><h2>{selectedTrace?.operation ?? "Trace details"}</h2><p>{`Trace ID ${selected}`}</p></div></div>
              {detailLoading ? <p className="ops-loading" role="status">Loading trace spans…</p> : null}
              {selected && !detailLoading && !spans.length ? <EmptyRows>No safe span details are available.</EmptyRows> : null}
              {spans.length ? <ol className="ops-span-list">{spans.map((span, index) => <li key={`${span.service}-${span.start_time_unix_nano}-${index}`}><span className="ops-span-copy"><strong title={span.operation}>{span.operation}</strong><small>{span.service} · {number(span.duration_ms)} ms</small></span><span className="ops-span-bar" aria-hidden="true"><i data-service={span.service} style={{ left: `${((span.start_time_unix_nano - traceStart) / traceSpan) * 100}%`, width: `${Math.max(1.5, ((span.duration_ms * 1_000_000) / traceSpan) * 100)}%` }} /></span></li>)}</ol> : null}
            </>
          )}
          <p className="ops-footnote">Trace results include safe service, operation, and timing fields only.</p>
        </section>
      </div>
    </section>
  );
}
