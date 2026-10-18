// Synthetic Control Room telemetry for `npm run dev:mock`. Shapes follow src/ops/ControlRoom.tsx.

const STEP_SECONDS = 75;
const POINTS = 24;
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

function series(base: number, swing: number, skip?: number) {
  const now = Math.floor(Date.now() / 1000);
  return Array.from({ length: POINTS }, (_, index) => ({
    timestamp: now - (POINTS - 1 - index) * STEP_SECONDS,
    value: Number((base + Math.sin(index / 3) * swing + (index % 5) * swing * 0.15).toFixed(3)),
  })).filter((_, index) => index !== skip);
}

export function controlRoomSummary(surgeState: string, surgeChangedAt: string | null) {
  const service = (name: string, healthy: number, count: number, rate: number, errors: number | null, p95: number | null, activity: "active" | "quiet" | "no_data" = "active") => ({
    name,
    health: healthy === count ? ("healthy" as const) : ("degraded" as const),
    healthy_instances: healthy,
    instance_count: count,
    request_rate_per_second: rate,
    error_rate_percent: errors,
    p95_latency_ms: p95,
    recent_activity: activity,
  });
  return {
    status: "available" as const,
    observed_at: iso(Date.now()),
    system: {
      health: "degraded" as const,
      request_rate_per_second: 4.21,
      error_rate_percent: 0.8,
      p95_latency_ms: 142,
      active_alert_count: 2,
      surge_mode: { state: surgeState, changed_at: surgeChangedAt },
    },
    services: [
      service("patient", 2, 2, 0.62, 0, 38),
      service("doctor", 2, 2, 0.94, 0, 46),
      service("appointment", 3, 3, 1.38, 0.4, 168),
      service("records", 2, 2, 0.41, 0, null, "quiet"),
      service("pharmacy", 2, 2, 0.33, 0, 72),
      service("billing", 1, 2, 0.29, 3.1, 121),
      service("emergency", 2, 2, 0.24, 0, 54),
    ],
    trends: { request_rate: series(4.1, 0.6, 15), error_rate: series(0.7, 0.25) },
    alerts: [
      { name: "BillingReplicaNotReady", service: "billing", severity: "critical" as const },
      { name: "AppointmentP95LatencyHigh", service: "appointment", severity: "warning" as const },
    ],
    components: {
      rate_limiter: [
        { owner: "appointment", outcome: "allowed", value: 3.1 },
        { owner: "appointment", outcome: "rejected", value: 0.02 },
      ],
      cache: [
        { owner: "doctor", outcome: "hit", value: 2.4 },
        { owner: "doctor", outcome: "miss", value: 0.6 },
      ],
      consistent_hashing: {
        topology_epoch: [{ owner: "doctor", value: 3 }],
        configured_nodes: [{ owner: "doctor", value: 2 }],
      },
      circuit_breakers: [
        { dependency: "records", state: "closed", value: 0 },
        { dependency: "pharmacy", state: "closed", value: 0 },
      ],
      bulkheads: [{ dependency: "records", owner: "appointment", value: 0.25 }],
    },
    messaging: {
      queues: [
        { name: "pulsegrid.appointment.journey.pharmacy.v1", ready: 3, unacknowledged: 1, consumers: 2 },
        { name: "pulsegrid.appointment.journey.billing.v1", ready: 7, unacknowledged: 0, consumers: 2 },
        { name: "pulsegrid.appointment.journey.records.v1", ready: 0, unacknowledged: 0, consumers: 2 },
        { name: "pulsegrid.billing.reconcile.v1", ready: 12, unacknowledged: 2, consumers: 1 },
      ],
      outbox_pending_by_owner: [{ owner: "pharmacy", value: 1 }, { owner: "billing", value: 4 }],
      outbox_oldest_seconds_by_owner: [{ owner: "billing", value: 38 }],
      publisher_failures_15m: [],
      consumer_processed_15m: [{ owner: "appointment", value: 214 }],
      delivery_p95_seconds: [{ owner: "appointment", value: 1.8 }],
    },
    recent_events: {
      available: true,
      items: [
        { action: "surge_mode_changed", previous_state: "RECOVERY", new_state: "NORMAL", reason_code: "planned_recovery", occurred_at: surgeChangedAt },
      ],
    },
  };
}

const traceIds = ["4f1c2a9e8b7d6c5f4e3d2c1b0a998877", "5a6b7c8d9e0f11223344556677889900", "6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e", "7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f"];
export function traceList() {
  const now = Date.now();
  const at = (minutesAgo: number) => (now - minutesAgo * 60_000) * 1_000_000;
  return {
    traces: [
      { trace_id: traceIds[0], service: "appointment", operation: "POST /api/v1/appointments/{id}/check-in", duration_ms: 186.4, start_time_unix_nano: at(2) },
      { trace_id: traceIds[1], service: "appointment", operation: "GET /api/v1/appointments/journeys/{id}", duration_ms: 241.9, start_time_unix_nano: at(6) },
      { trace_id: traceIds[2], service: "pharmacy", operation: "POST /api/v1/pharmacy/reservations", duration_ms: 97.2, start_time_unix_nano: at(11) },
      { trace_id: traceIds[3], service: "billing", operation: "POST /api/v1/billing/invoices/{id}/charges", duration_ms: 312.5, start_time_unix_nano: at(19) },
    ],
  };
}
export function traceSpans(traceId: string) {
  const index = traceIds.indexOf(traceId);
  if (index < 0) return null;
  const start = traceList().traces[index].start_time_unix_nano;
  const span = (service: string, operation: string, offsetMs: number, duration_ms: number) => ({ service, operation, start_time_unix_nano: start + offsetMs * 1_000_000, duration_ms });
  if (index === 1) {
    return {
      spans: [
        span("appointment", "GET /api/v1/appointments/journeys/{id}", 0, 241.9),
        span("appointment", "SELECT journey projection", 3, 6.2),
        span("records", "GET /internal/v1/records/consultations/{id}", 14, 61.4),
        span("records", "SELECT consultation", 18, 9.8),
        span("pharmacy", "GET /internal/v1/pharmacy/prescriptions/{id}/fulfillment", 82, 54.1),
        span("billing", "GET /internal/v1/billing/invoices/{id}", 141, 72.3),
      ],
    };
  }
  return {
    spans: [
      span(traceList().traces[index].service, traceList().traces[index].operation, 0, traceList().traces[index].duration_ms),
      span("appointment", "UPDATE appointment workflow", 8, 14.6),
      span("records", "GET /internal/v1/records/consultations/{id}", 31, 48.2),
    ],
  };
}
