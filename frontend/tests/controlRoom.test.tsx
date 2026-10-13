import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const request = vi.fn();
  return { request, api: { request } };
});

vi.mock("../src/auth/authContext", () => ({ useAuth: () => ({ api: mocks.api, state: {status:"authenticated", user:{id:"21",roleHints:["ops"]},roleHints:["ops"]} }) }));

import { ControlRoom, TraceExplorer } from "../src/ops/ControlRoom";

const service = {
  name: "doctor",
  health: "healthy" as const,
  healthy_instances: 2,
  instance_count: 2,
  request_rate_per_second: 1.25,
  error_rate_percent: 0,
  p95_latency_ms: 48,
  recent_activity: "active" as const,
};

const summary = {
  status: "available" as const,
  observed_at: "2026-10-13T00:00:00Z",
  system: {
    health: "healthy" as const,
    request_rate_per_second: 1.25,
    error_rate_percent: 0,
    p95_latency_ms: 48,
    active_alert_count: 0,
    surge_mode: { state: "NORMAL", changed_at: null },
  },
  services: [service],
  trends: { request_rate: [{ timestamp: 1, value: 1.25 }], error_rate: [{ timestamp: 1, value: 0 }] },
  alerts: [],
  components: {
    rate_limiter: [],
    cache: [],
    consistent_hashing: {
      topology_epoch: [{ owner: "doctor", value: 17 }],
      configured_nodes: [{ owner: "doctor", value: 2 }],
    },
    circuit_breakers: [],
    bulkheads: [],
  },
  messaging: {
    queues: [{ name: "pulsegrid.appointment.journey.billing.v1", ready: 0, unacknowledged: 0, consumers: 1 }],
    outbox_pending_by_owner: [],
    outbox_oldest_seconds_by_owner: [],
    publisher_failures_15m: [],
    consumer_processed_15m: [],
    delivery_p95_seconds: [],
  },
  recent_events: { available: true, items: [] },
};

function renderInRouter(node: ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

describe("PulseGrid Control Room", () => {
  beforeEach(() => mocks.request.mockReset());
  afterEach(() => cleanup());

  it("renders live service and messaging data returned by the operational API", async () => {
    mocks.request.mockResolvedValue(summary);
    renderInRouter(<ControlRoom workspaceBasePath="/ops" />);

    expect(await screen.findByRole("heading", { name: "Control Room" })).toBeInTheDocument();
    expect(screen.queryByText("Surge Mode controls · Administrator")).not.toBeInTheDocument();
    expect(await screen.findByText("healthy", { selector: "span" })).toBeInTheDocument();
    expect(screen.getAllByText("1.25").length).toBeGreaterThan(0);
    expect(screen.getByText("Hash topology epoch")).toBeInTheDocument();
    expect(screen.getByText("17.00")).toBeInTheDocument();
    expect(screen.getByText("epoch")).toBeInTheDocument();
    expect(screen.getByText("2.00")).toBeInTheDocument();
    expect(screen.getByText("nodes")).toBeInTheDocument();
    expect(screen.getByText("appointment.journey.billing.v1")).toBeInTheDocument();
    expect(mocks.request).toHaveBeenCalledWith(
      "/api/v1/appointments/operations/control-room/summary",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("lists recent traces and renders only the API-provided safe span summary", async () => {
    let calls = 0;
    mocks.request.mockImplementation(() => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve({ traces: [{ trace_id: "a".repeat(32), service: "appointment", operation: "POST /api/v1/appointments", duration_ms: 42, start_time_unix_nano: 1_000_000 }] });
      }
      return Promise.resolve({ spans: [{ service: "appointment", operation: "POST /api/v1/appointments", start_time_unix_nano: 1_000_000, duration_ms: 42 }] });
    });
    renderInRouter(<TraceExplorer />);

    fireEvent.click(await screen.findByRole("button", { name: /POST \/api\/v1\/appointments/ }));

    expect(await screen.findByText("Trace ID " + "a".repeat(32))).toBeInTheDocument();
    expect(screen.getAllByText("POST /api/v1/appointments").length).toBeGreaterThan(0);
  });
});
