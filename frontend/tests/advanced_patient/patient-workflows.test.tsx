import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, type Role } from "../../src/auth/authContext";
import { createApiClient } from "../../src/api/client";
import {
  PatientCheckinPage,
  PatientFulfillmentPanel,
  PatientJourneyPage,
  PatientQueuePage,
  PatientWaitlistPage,
} from "../../src/advanced/patient";
import type {
  Appointment,
  CheckinResult,
  Fulfillment,
  Journey,
  JourneyStage,
  OwnQueue,
  Prescription,
  Reservation,
  TokenIssue,
  Waitlist,
  Workflow,
} from "../../src/advanced/patient/contracts";

const patientProfile = { id: "11", user_id: "101", display_name: "Synthetic patient", date_of_birth: "2000-01-01", version: 1 };
const appointment: Appointment = {
  id: "51",
  journey_id: null,
  patient_id: "11",
  doctor_id: "21",
  slot_id: "41",
  starts_at: "2027-01-01T09:00:00Z",
  ends_at: "2027-01-01T09:30:00Z",
  state: "confirmed",
  version: 5,
};
const workflow: Workflow = {
  appointment_id: "51",
  journey_id: "101",
  patient_id: "11",
  doctor_id: "21",
  state: "booked",
  checkin_window: {
    starts_at: "2027-01-01T08:30:00Z",
    ends_at: "2027-01-01T09:15:00Z",
  },
  queue_entry_id: null,
  version: 2,
};
const token = "Abcdef0123456789ABCDEF";

function json(body: unknown, status = 200, etag?: string): Response {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (etag) headers.set("ETag", etag);
  return new Response(JSON.stringify(body), { status, headers });
}

function failure(status: number, code: string, message: string): Response {
  return json({ error: { code, message, request_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" } }, status);
}

type Handler = (url: URL, init: RequestInit) => Response | Promise<Response> | undefined;

function setup(component: React.ReactNode, handler: Handler, role: Role = "patient") {
  const fetcher = vi.fn<typeof fetch>(async (input, init = {}) => {
    const url = new URL(String(input), "http://pulsegrid.test");
    return (await handler(url, init)) ?? failure(404, "not_found", `No fixture for ${url.pathname}.`);
  });
  const access = `header.${btoa(JSON.stringify({ sub: "user-101", roles: [role] }))}.signature`;
  const auth = {
    login: async () => ({ access_token: access, token_type: "Bearer" as const, expires_in: 600 }),
    refresh: async () => ({ access_token: access, token_type: "Bearer" as const, expires_in: 600 }),
    register: async () => patientProfile,
    logout: async () => undefined,
  };
  render(
    <AuthProvider client={auth} apiClient={createApiClient({ fetcher })}>
      <MemoryRouter>{component}</MemoryRouter>
    </AuthProvider>,
  );
  return fetcher;
}

function method(init: RequestInit): string {
  return init.method ?? "GET";
}

function body(init: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init.body));
}

function headers(init: RequestInit): Headers {
  return new Headers(init.headers);
}

function page<T>(items: T[]) {
  return { items, next_cursor: null };
}

function waitingEntry(state: Waitlist["state"] = "waiting"): Waitlist {
  return {
    id: "61",
    slot_id: "41",
    patient_id: "11",
    state,
    joined_at: "2026-10-10T10:00:00Z",
    promoted_appointment_id: state === "promoted" ? "51" : null,
    skip_reason: null,
    version: 2,
  };
}

function waitlistHandler(
  onJoin?: (url: URL, init: RequestInit) => Response | undefined,
  onWithdraw?: (url: URL, init: RequestInit) => Response | undefined,
): Handler {
  return (url, init) => {
    if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
    if (url.pathname === "/api/v1/appointments/waitlists" && method(init) === "GET") return json(page([waitingEntry()]));
    if (url.pathname === "/api/v1/appointments/waitlist-slots/41") return json({
      slot_id: "41", waiting_count: 3, promotion_pending: false, accepted_revision: 4, observed_at: "2026-10-11T10:00:00Z",
    });
    if (url.pathname === "/api/v1/appointments/waitlists" && method(init) === "POST") return onJoin?.(url, init);
    if (url.pathname === "/api/v1/appointments/waitlists/61" && method(init) === "GET") return json(waitingEntry(), 200, '"2"');
    if (url.pathname === "/api/v1/appointments/waitlists/61/withdraw") return onWithdraw?.(url, init);
    return undefined;
  };
}

describe("Agent 6 patient workflows", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
    vi.restoreAllMocks();
  });

  it("joins with the self profile ID and frozen waitlist request fields", async () => {
    let posted: { url: URL; init: RequestInit } | null = null;
    const fetcher = setup(<PatientWaitlistPage />, waitlistHandler((url, init) => {
      posted = { url, init };
      return json(waitingEntry(), 201, '"2"');
    }));

    await screen.findByText(/3 patients are waiting on this slot/);
    fireEvent.change(screen.getByLabelText("Slot ID"), { target: { value: "41" } });
    fireEvent.change(screen.getByLabelText("Accepted schedule revision"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Join waitlist" }));

    await screen.findByText(/Waitlist entry 61 was created/);
    expect(posted).not.toBeNull();
    expect(body(posted!.init)).toEqual({ patient_id: "11", slot_id: "41", expected_schedule_revision: 4 });
    expect(headers(posted!.init).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers(posted!.init).get("Authorization")).toContain("Bearer ");
    expect(fetcher.mock.calls.some(([input, init]) => String(input).endsWith("/withdraw") && method(init ?? {}) === "POST")).toBe(false);
    expect(await screen.findByText((_content, element) => element?.tagName === "P" && element.textContent?.includes("not your exact position") === true)).toBeInTheDocument();
  });

  it("uses the current waitlist ETag when withdrawing and explains immediate promotion", async () => {
    const promoted = waitingEntry("promoted");
    let isPromoted = false;
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments/waitlists" && method(init) === "GET") return json(page([isPromoted ? promoted : waitingEntry()]));
      if (url.pathname === "/api/v1/appointments/waitlist-slots/41") return json({ slot_id: "41", waiting_count: 1, promotion_pending: false, accepted_revision: 4, observed_at: "2026-10-11T10:00:00Z" });
      if (url.pathname === "/api/v1/appointments/waitlists/61" && method(init) === "GET") return json(waitingEntry(), 200, '"2"');
      if (url.pathname === "/api/v1/appointments/waitlists/61/withdraw" && method(init) === "POST") {
        isPromoted = true;
        return json({ ...waitingEntry("withdrawn"), version: 3 }, 200, '"3"');
      }
      return undefined;
    };
    const fetcher = setup(<PatientWaitlistPage />, handler);
    await screen.findByRole("button", { name: "Withdraw entry" });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw entry" }));
    await screen.findByText(/no offer acceptance or rejection action/i);
    const withdraw = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/waitlists/61/withdraw") && method(init ?? {}) === "POST");
    expect(withdraw).toBeDefined();
    expect(headers(withdraw![1]!).get("If-Match")).toBe('"2"');
    expect(body(withdraw![1]!)).toEqual({ reason: "I no longer need this waitlist entry." });
  });

  it("does not claim a waitlist join when the slot is free", async () => {
    const fetcher = setup(<PatientWaitlistPage />, waitlistHandler((_url, _init) => failure(409, "slot_available", "The slot is available.")));
    await screen.findByRole("button", { name: "Join waitlist" });
    fireEvent.change(screen.getByLabelText("Slot ID"), { target: { value: "41" } });
    fireEvent.change(screen.getByLabelText("Accepted schedule revision"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Join waitlist" }));
    await screen.findByText("This slot is available now. Book it from Appointments instead.");
    expect(fetcher.mock.calls.some(([input, init]) => String(input).includes("/waitlists") && method(init ?? {}) === "POST")).toBe(true);
  });

  it("strips a landing fragment, issues a token, and checks in only after confirmation", async () => {
    window.history.replaceState(null, "", `/patient/check-in#appointment_id=51&token=${token}`);
    let workflowReads = 0;
    let issueRequest: { init: RequestInit } | null = null;
    let checkinRequest: { init: RequestInit } | null = null;
    const tokenIssue: TokenIssue = {
      link_id: "91",
      appointment_id: "51",
      expires_at: "2026-10-12T12:00:00Z",
      token,
      landing_path: `/patient/check-in#appointment_id=51&token=${token}`,
      version: 1,
    };
    const result: CheckinResult = {
      workflow: { ...workflow, state: "checked_in", queue_entry_id: "71", version: 3 },
      queue_entry: { id: "71", appointment_id: "51", doctor_id: "21", local_date: "2027-01-01", token_number: 7, state: "waiting", position: 2, version: 1 },
    };
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments" && method(init) === "GET") return json(page([appointment]));
      if (url.pathname === "/api/v1/appointments/51/workflow" && method(init) === "GET") {
        workflowReads += 1;
        return json(workflowReads === 1 ? workflow : { ...workflow, version: 3 }, 200, workflowReads === 1 ? '"2"' : '"3"');
      }
      if (url.pathname === "/api/v1/appointments/51/check-in-links" && method(init) === "POST") {
        issueRequest = { init };
        return json(tokenIssue, 201, '"1"');
      }
      if (url.pathname === "/api/v1/appointments/51/check-in" && method(init) === "POST") {
        checkinRequest = { init };
        return json(result, 200, '"3"');
      }
      return undefined;
    };
    const fetcher = setup(<PatientCheckinPage />, handler);

    expect(window.location.hash).toBe("");
    await screen.findByRole("button", { name: "Request check-in QR" });
    expect(fetcher.mock.calls.some(([input, init]) => String(input).endsWith("/check-in") && method(init ?? {}) === "POST")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Request check-in QR" }));
    expect(await screen.findByLabelText("One-time token (held in memory)")).toHaveValue(token);
    expect(await screen.findByAltText("Single-use appointment check-in QR")).toBeInTheDocument();
    expect(issueRequest).not.toBeNull();
    expect(headers(issueRequest!.init).get("If-Match")).toBe('"2"');
    expect(screen.getByLabelText("Secure same-origin landing URL")).toHaveValue(`${window.location.origin}/patient/check-in#appointment_id=51&token=${token}`);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm check-in" }));
    await screen.findByText(/Check-in confirmed by the service/);
    expect(body(checkinRequest!.init)).toEqual({ token });
    expect(headers(checkinRequest!.init).get("If-Match")).toBe('"3"');
    expect(headers(checkinRequest!.init).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(window.location.hash).not.toContain(token);
  });

  it("shows a backend invalid-or-expired token response without claiming check-in", async () => {
    window.history.replaceState(null, "", `/patient/check-in#appointment_id=51&token=${token}`);
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments" && method(init) === "GET") return json(page([appointment]));
      if (url.pathname === "/api/v1/appointments/51/workflow") return json(workflow, 200, '"2"');
      if (url.pathname === "/api/v1/appointments/51/check-in" && method(init) === "POST") return failure(409, "token_invalid", "The supplied token is invalid.");
      return undefined;
    };
    const fetcher = setup(<PatientCheckinPage />, handler);
    const confirm = await screen.findByRole("button", { name: "Confirm check-in" });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm);
    await waitFor(() => expect(fetcher.mock.calls.some(([input, init]) => String(input).endsWith("/check-in") && method(init ?? {}) === "POST")).toBe(true));
    await screen.findByText((_content, element) => element?.tagName === "P" && element.textContent?.includes("No check-in was confirmed") === true);
    expect(screen.queryByText(/Check-in confirmed by the service/)).not.toBeInTheDocument();
  });

  it("reconnects the own-queue poll and renders only the backend position and status", async () => {
    let queueReads = 0;
    const queue: OwnQueue = {
      entry: { id: "71", appointment_id: "51", doctor_id: "21", local_date: "2027-01-01", token_number: 7, state: "waiting", position: 2, version: 2 },
      waiting_count: 4,
      in_consultation_count: 1,
      queue_version: 5,
      observed_at: "2026-10-11T10:00:00Z",
    };
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments" && method(init) === "GET") return json(page([appointment]));
      if (url.pathname === "/api/v1/appointments/51/queue") {
        queueReads += 1;
        return queueReads === 1 ? failure(503, "dependency_unavailable", "Queue temporarily unavailable.") : json(queue);
      }
      if (url.pathname === "/api/v1/appointments/51/workflow") return json({ ...workflow, state: "in_consultation" }, 200, '"3"');
      return undefined;
    };
    setup(<PatientQueuePage />, handler);
    fireEvent.click(await screen.findByRole("button", { name: "Reconnect now" }));
    await screen.findByText("in_consultation");
    expect(screen.getByText("2", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("7", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/Queue status updates are polled every five seconds/)).toBeInTheDocument();
  });

  it("clears an old queue token and position when the backend reports no current entry", async () => {
    let present = true;
    const queue: OwnQueue = {
      entry: { id: "71", appointment_id: "51", doctor_id: "21", local_date: "2027-01-01", token_number: 7, state: "waiting", position: 2, version: 2 },
      waiting_count: 4,
      in_consultation_count: 1,
      queue_version: 5,
      observed_at: "2026-10-11T10:00:00Z",
    };
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments" && method(init) === "GET") return json(page([appointment]));
      if (url.pathname === "/api/v1/appointments/51/queue") {
        return present ? json(queue) : failure(404, "not_found", "No active queue entry.");
      }
      if (url.pathname === "/api/v1/appointments/51/workflow") return json(workflow, 200, '"2"');
      return undefined;
    };
    setup(<PatientQueuePage />, handler);
    expect(await screen.findByText("7", { selector: "dd" })).toBeInTheDocument();
    present = false;
    fireEvent.click(screen.getByRole("button", { name: "Refresh queue now" }));
    await screen.findByText(/The service has not returned a queue entry/);
    expect(screen.queryByText("7", { selector: "dd" })).not.toBeInTheDocument();
  });

  it("renders all journey stages and sends reconcile with the detail ETag", async () => {
    const stageNames: JourneyStage["name"][] = ["appointment", "check_in", "consultation", "prescription", "pharmacy", "billing"];
    const stages: JourneyStage[] = stageNames.map((name, index) => ({
      name,
      state: (["complete", "pending", "skipped", "reopened", "complete", "pending"] as const)[index],
      sources: [],
      observed_at: index ? "2026-10-11T10:00:00Z" : null,
      pending_reason: index === 1 ? "awaiting_source" : index === 5 ? "unpaid" : null,
    }));
    const journey: Journey = {
      id: "101", appointment_id: "51", patient_id: "11", state: "reopened", stages,
      discharge_eligible: false, review_required: true, last_reconciled_at: "2026-10-11T10:00:00Z", version: 4,
    };
    let request: RequestInit | null = null;
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/appointments/journeys" && method(init) === "GET") return json(page([journey]));
      if (url.pathname === "/api/v1/appointments/journeys/101" && method(init) === "GET") return json(journey, 200, '"4"');
      if (url.pathname === "/api/v1/appointments/journeys/101/reconcile" && method(init) === "POST") {
        request = init;
        return json({ ...journey, version: 5 }, 200, '"5"');
      }
      return undefined;
    };
    setup(<PatientJourneyPage />, handler);
    await screen.findByText((_content, element) => element?.tagName === "P" && element.textContent?.includes("Incomplete") === true && element.textContent.includes("awaiting source"));
    expect(screen.getByText("skipped")).toBeInTheDocument();
    expect(screen.getAllByText("reopened").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Refresh journey from current owner snapshots" }));
    await waitFor(() => expect(request).not.toBeNull());
    expect(body(request!)).toEqual({});
    expect(headers(request!).get("If-Match")).toBe('"4"');
    expect(headers(request!).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByText(/cannot clear that flag/)).toBeInTheDocument();
  });

  it("requests a reservation from real remaining quantities and shows the returned Pharmacy state", async () => {
    const prescription: Prescription = {
      id: "71", consultation_id: "61", patient_id: "11", journey_id: null,
      revision: 1, state: "issued", items: [{ id: "72", medicine_id: "81", quantity: 5, dosage: "hidden", instructions: "hidden" }], version: 2,
    };
    let reserved = 0;
    const reservation: Reservation = {
      id: "91", patient_id: "11", prescription_id: "71", state: "reserved",
      items: [{ prescription_item_id: "72", medicine_id: "81", quantity: 2 }],
      expires_at: "2026-10-11T10:30:00Z", version: 1,
    };
    let request: RequestInit | null = null;
    const fulfillment: Fulfillment = {
      prescription_id: "71", appointment_id: "51", patient_id: "11", prescription_revision: 1,
      prescription_state: "issued",
      items: [{ prescription_item_id: "72", medicine_id: "81", prescribed_quantity: 5, reserved_quantity: reserved, dispensed_quantity: 1, remaining_quantity: 4 }],
      reservations: reserved ? [{ id: "91", state: "reserved", version: 1 }] : [],
      dispensings: [], review_required: false, version: reserved ? 2 : 1, observed_at: "2026-10-11T10:00:00Z",
    };
    const handler: Handler = (url, init) => {
      if (url.pathname === "/api/v1/patients/me") return json(patientProfile, 200, '"1"');
      if (url.pathname === "/api/v1/records/prescriptions") return json(page([prescription]));
      if (url.pathname === "/api/v1/pharmacy/prescriptions/71/fulfillment") return json(fulfillment);
      if (url.pathname === "/api/v1/pharmacy/reservations" && method(init) === "GET") return json(page(reserved ? [reservation] : []));
      if (url.pathname === "/api/v1/pharmacy/reservations" && method(init) === "POST") {
        request = init;
        reserved = 2;
        return json(reservation, 201, '"1"');
      }
      return undefined;
    };
    setup(<PatientFulfillmentPanel />, handler);
    fireEvent.change(await screen.findByLabelText(/Item 72 quantity \(up to 4\)/), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Request reservation" }));
    await screen.findByText(/Pharmacy returned reservation 91, state reserved/);
    expect(body(request!)).toEqual({ prescription_id: "71", items: [{ prescription_item_id: "72", quantity: 2 }] });
    expect(headers(request!).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByText(/72: 2/)).toBeInTheDocument();
    expect(screen.queryByText(/All prescribed quantities dispensed/)).not.toBeInTheDocument();
  });

  it("does not expose patient workflows to a non-patient role or call patient endpoints", async () => {
    const fetcher = setup(<PatientJourneyPage />, () => undefined, "receptionist");
    await screen.findByText("This patient workflow is available only to the signed-in patient.");
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("temporary waitlist offers", () => {
  it("retains the original command identity after ambiguous acceptance and shows only owner confirmation", async () => {
    const { WaitlistOffers } = await import("../../src/advanced/patient/WaitlistOffers");
    const offer = { id: "91", entry_id: "61", slot_id: "41", patient_id: "11", state: "pending",
      expires_at: new Date(Date.now() + 120000).toISOString(), appointment_id: null, version: 1 };
    const calls: RequestInit[] = [];
    setup(<WaitlistOffers />, (url, init) => {
      if (url.pathname.endsWith("/waitlist-offers") && method(init) === "GET") return json(page([offer]));
      if (url.pathname.endsWith("/91/accept")) {
        calls.push(init);
        return calls.length === 1 ? failure(503, "dependency_unavailable", "Retry original command.")
          : json({ offer: { ...offer, state: "accepted", version: 2 }, appointment: { id: "51" } });
      }
      return undefined;
    });
    fireEvent.click(await screen.findByRole("button", { name: "Accept slot offer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Retry original command");
    fireEvent.click(await screen.findByRole("button", { name: "Retry original offer command" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Booking confirmed: appointment 51");
    expect(headers(calls[0]).get("Idempotency-Key")).toBe(headers(calls[1]).get("Idempotency-Key"));
    expect(headers(calls[0]).get("If-Match")).toBe('"1"');
  });
});
