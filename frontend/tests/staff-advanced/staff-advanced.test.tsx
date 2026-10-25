import { commandLabels } from "../commandLabels";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../src/api/client";
import { AuthProvider, type Role } from "../../src/auth/authContext";
import { DoctorQueuePage } from "../../src/hospital/staffAdvanced/DoctorQueuePage";
import { ReceptionWorkflowPanel } from "../../src/hospital/staffAdvanced/ReceptionWorkflowPanel";
import { StaffFulfillmentPanel } from "../../src/hospital/staffAdvanced/StaffFulfillmentPanel";
import type { CheckinResult, Fulfillment, Journey, QueueEntry, StaffQueue, Workflow } from "../../src/hospital/staffAdvanced/contracts";
import { parseCheckinQr, validateCheckinToken } from "../../src/hospital/staffAdvanced/utils";

type Handler = (url: URL, init: RequestInit) => Response | undefined | Promise<Response | undefined>;

function json(data: unknown, status = 200, etag?: string): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json",
      ...(etag ? { ETag: etag } : {}),
    },
  });
}

function failure(status: number, code: string, message: string): Response {
  return json({ error: { code, message, request_id: "00000000-0000-4000-8000-000000000001" } }, status);
}

function setup(role: Role, component: React.ReactNode, handler: Handler = () => undefined) {
  const fetcher = vi.fn<typeof fetch>(async (input, init = {}) => {
    const url = new URL(String(input), "http://pulsegrid.test");
    const response = await handler(url, init);
    return response ?? failure(404, "not_found", "Resource not found.");
  });
  const token = `header.${btoa(JSON.stringify({ sub: "101", roles: [role] }))}.signature`;
  const auth = {
    login: async () => ({ access_token: token, token_type: "Bearer" as const, expires_in: 600 }),
    refresh: async () => ({ access_token: token, token_type: "Bearer" as const, expires_in: 600 }),
    register: async () => ({ id: "11", user_id: "101", display_name: "Synthetic Patient", date_of_birth: "2000-01-01", version: 1 }),
    logout: async () => undefined,
  };
  const view = render(
    <AuthProvider client={auth} apiClient={createApiClient({ fetcher })}>
      <MemoryRouter>{component}</MemoryRouter>
    </AuthProvider>,
  );
  return { fetcher, view };
}

function getCalls(fetcher: ReturnType<typeof setup>["fetcher"]) {
  return fetcher.mock.calls.filter(([, init]) => !init?.method || init.method === "GET");
}

function writes(fetcher: ReturnType<typeof setup>["fetcher"]) {
  return fetcher.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
}

function lastWrite(fetcher: ReturnType<typeof setup>["fetcher"]) {
  const call = writes(fetcher).at(-1);
  if (!call) throw new Error("No write request was recorded.");
  return call;
}

function requestHeaders(init: RequestInit) {
  return new Headers(init.headers);
}

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function confirm(title: string) {
  fireEvent.click(screen.getByRole("button", { name: commandLabels(title).review }));
  fireEvent.click(await screen.findByRole("button", { name: commandLabels(title).confirm }));
  await screen.findByText((_text, element) => element?.getAttribute("role") === "status" && (element.textContent ?? "").includes(commandLabels(title).success));
}

const token = "0123456789012345678901";

const workflow: Workflow = {
  appointment_id: "51",
  journey_id: "151",
  patient_id: "11",
  doctor_id: "21",
  state: "booked",
  checkin_window: {
    starts_at: "2027-01-01T08:30:00Z",
    ends_at: "2027-01-01T09:15:00Z",
  },
  queue_entry_id: null,
  version: 3,
};

const queueEntry: QueueEntry = {
  id: "91",
  appointment_id: "51",
  doctor_id: "21",
  local_date: "2027-01-01",
  token_number: 7,
  state: "waiting",
  position: 1,
  version: 4,
  patient_id: "11",
};

const queue: StaffQueue = {
  doctor_id: "21",
  local_date: "2027-01-01",
  items: [queueEntry],
  next_cursor: null,
  waiting_count: 1,
  in_consultation_count: 0,
  version: 6,
  observed_at: "2027-01-01T08:45:00Z",
};

const journey: Journey = {
  id: "151",
  appointment_id: "51",
  patient_id: "11",
  state: "ready",
  stages: ["appointment", "check_in", "consultation", "prescription", "pharmacy", "billing"].map((name) => ({
    name: name as Journey["stages"][number]["name"],
    state: "complete",
    sources: [],
    observed_at: "2027-01-01T08:45:00Z",
    pending_reason: null,
  })),
  discharge_eligible: true,
  review_required: false,
  last_reconciled_at: "2027-01-01T08:45:00Z",
  version: 6,
};

const checkinResult: CheckinResult = {
  workflow: { ...workflow, state: "checked_in", queue_entry_id: "91", version: 4 },
  queue_entry: { ...queueEntry, state: "waiting", version: 1 },
};

const fulfillment: Fulfillment = {
  prescription_id: "71",
  appointment_id: "51",
  patient_id: "11",
  prescription_revision: 2,
  prescription_state: "issued",
  items: [{
    prescription_item_id: "72",
    medicine_id: "81",
    prescribed_quantity: 5,
    reserved_quantity: 2,
    dispensed_quantity: 1,
    remaining_quantity: 4,
  }],
  reservations: [{ id: "91", state: "reserved", version: 2 }],
  dispensings: [{ id: "92", version: 1, source_item_ids: ["93"] }],
  review_required: true,
  version: 4,
  observed_at: "2027-01-01T08:45:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("reception check-in", () => {
  it("confirms an audited no-show using the current workflow version and refreshes its terminal state", async () => {
    let currentWorkflow = workflow;
    const { fetcher } = setup("receptionist", <ReceptionWorkflowPanel />, (url, init) => {
      if (url.pathname === "/api/v1/appointments/51/workflow") return json(currentWorkflow, 200, `"${currentWorkflow.version}"`);
      if (url.pathname === "/api/v1/appointments/51/no-show" && init.method === "POST") {
        currentWorkflow = { ...workflow, state: "no_show", version: 4 };
        return json(currentWorkflow, 200, '"4"');
      }
      return undefined;
    });
    await screen.findByLabelText("Appointment ID");
    fill("Appointment ID", "51");
    fireEvent.submit(screen.getByLabelText("Appointment ID").closest("form")!);
    await screen.findByLabelText("No-show reason");
    fill("No-show reason", "Synthetic patient did not attend");
    fireEvent.click(screen.getByRole("button", { name: commandLabels("Mark no-show").review }));
    expect(writes(fetcher)).toHaveLength(0);
    fireEvent.click(await screen.findByRole("button", { name: commandLabels("Mark no-show").confirm }));
    await screen.findByText("no_show");
    const [url, init] = lastWrite(fetcher);
    expect(String(url)).toContain("/api/v1/appointments/51/no-show");
    expect(JSON.parse(String(init?.body))).toEqual({ reason: "Synthetic patient did not attend" });
    expect(requestHeaders(init!).get("If-Match")).toBe('"3"');
    expect(requestHeaders(init!).get("Idempotency-Key")).toBeTruthy();
    expect(screen.queryByRole("button", { name: commandLabels("Mark no-show").review })).not.toBeInTheDocument();
  });

  it("validates manual token input, supports scanner fallback and confirms owner success", async () => {
    let currentWorkflow = workflow;
    const { fetcher } = setup("receptionist", <ReceptionWorkflowPanel />, async (url, init) => {
      if (url.pathname === "/api/v1/appointments/51/workflow") return json(currentWorkflow, 200, `"${currentWorkflow.version}"`);
      if (url.pathname === "/api/v1/appointments/51/check-in" && init.method === "POST") {
        currentWorkflow = checkinResult.workflow;
        return json(checkinResult, 200, '"4"');
      }
      return undefined;
    });

    await screen.findByRole("button", { name: "Scan check-in QR" });
    fireEvent.click(screen.getByRole("button", { name: "Scan check-in QR" }));
    expect(await screen.findByText(/QR scanning is unavailable/)).toBeInTheDocument();
    fill("Appointment ID", "51");
    fireEvent.submit(screen.getByLabelText("Appointment ID").closest("form")!);
    await screen.findByText("booked");

    fill("Check-in token", "bad-token");
    fireEvent.submit(screen.getByLabelText("Check-in token").closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("22-character");
    expect(writes(fetcher)).toHaveLength(0);

    fill("Check-in token", token);
    fireEvent.submit(screen.getByLabelText("Check-in token").closest("form")!);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm check-in" }));
    expect(await screen.findByText(/Check-in confirmed by Appointment/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue(token)).not.toBeInTheDocument();
    const [url, init] = lastWrite(fetcher);
    expect(String(url)).toBe("/api/v1/appointments/51/check-in");
    expect(JSON.parse(String(init?.body))).toEqual({ token });
    expect(requestHeaders(init!).get("If-Match")).toBe('"3"');
    expect(requestHeaders(init!).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("uses the audited staff fallback and reloads after a concurrent conflict", async () => {
    const { fetcher } = setup("receptionist", <ReceptionWorkflowPanel />, (url, init) => {
      if (url.pathname === "/api/v1/appointments/51/workflow") return json(workflow, 200, '"3"');
      if (url.pathname === "/api/v1/appointments/51/staff-check-in" && init.method === "POST") {
        return failure(409, "invalid_transition", "Workflow changed before staff check-in.");
      }
      return undefined;
    });
    await screen.findByRole("button", { name: "Scan check-in QR" });
    fill("Appointment ID", "51");
    fireEvent.submit(screen.getByLabelText("Appointment ID").closest("form")!);
    await screen.findByText("booked");
    fill("Audited manual check-in reason", "Patient could not access the token.");
    fireEvent.submit(screen.getByLabelText("Audited manual check-in reason").closest("form")!);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm check-in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Workflow changed before staff check-in.");
    const [url, init] = lastWrite(fetcher);
    expect(String(url)).toBe("/api/v1/appointments/51/staff-check-in");
    expect(JSON.parse(String(init?.body))).toEqual({ reason: "Patient could not access the token." });
    expect(requestHeaders(init!).get("If-Match")).toBe('"3"');
    await waitFor(() => expect(getCalls(fetcher).filter(([input]) => String(input) === "/api/v1/appointments/51/workflow").length).toBeGreaterThan(1));
  });

  it("accepts only same-origin documented QR fragments", () => {
    expect(parseCheckinQr(
      `https://pulsegrid.test/patient/check-in#appointment_id=51&token=${token}`,
      "https://pulsegrid.test",
    )).toEqual({ appointmentId: "51", token });
    expect(() => parseCheckinQr(
      `https://evil.test/patient/check-in#appointment_id=51&token=${token}`,
      "https://pulsegrid.test",
    )).toThrow("same-origin");
    expect(() => validateCheckinToken("short")).toThrow("22-character");
  });
});

describe("doctor consultation queue", () => {
  it("loads assigned queue, starts the current server-selected head and links to consultations", async () => {
    const started = { ...queueEntry, state: "in_consultation" as const, position: null, version: 5 };
    const { fetcher } = setup("doctor", <DoctorQueuePage />, (url, init) => {
      if (url.pathname === "/api/v1/doctors/me") return json({ doctor: { id: "21", display_name: "Synthetic Doctor", active: true, version: 3 }, staff_user_id: "101" });
      if (url.pathname === "/api/v1/appointments/queues" && url.searchParams.get("state") === "waiting") return json(queue);
      if (url.pathname === "/api/v1/appointments/queues") return json(queue, 200, '"6"');
      if (url.pathname === "/api/v1/appointments/51/queue") return json({
        entry: { ...queueEntry, patient_id: undefined },
        waiting_count: 1,
        in_consultation_count: 0,
        queue_version: 6,
        observed_at: queue.observed_at,
      }, 200, '"4"');
      if (url.pathname === "/api/v1/appointments/queue-entries/91/start" && init.method === "POST") return json(started, 200, '"5"');
      if (url.pathname === "/api/v1/appointments/journeys/151") return json(journey, 200, '"6"');
      return undefined;
    });

    expect(await screen.findByText(/Waiting count/)).toBeInTheDocument();
    expect(screen.getByText(/Patient ID\s+11/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Call next patient" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm start consultation" }));
    expect(await screen.findByText(/Appointment service started queue token 7/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "consultation workspace" })).toHaveAttribute("href", "/doctor/consultations");
    const [url, init] = lastWrite(fetcher);
    expect(String(url)).toBe("/api/v1/appointments/queue-entries/91/start");
    expect(JSON.parse(String(init?.body))).toEqual({});
    expect(requestHeaders(init!).get("If-Match")).toBe('"4"');
    expect(requestHeaders(init!).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("reports queue-head conflicts and refreshes the snapshot", async () => {
    const { fetcher } = setup("doctor", <DoctorQueuePage />, (url, init) => {
      if (url.pathname === "/api/v1/doctors/me") return json({ doctor: { id: "21", display_name: "Synthetic Doctor", active: true, version: 3 }, staff_user_id: "101" });
      if (url.pathname === "/api/v1/appointments/queues" && url.searchParams.get("state") === "waiting") return json(queue);
      if (url.pathname === "/api/v1/appointments/queues") return json(queue, 200, '"6"');
      if (url.pathname === "/api/v1/appointments/51/queue") return json({
        entry: { id: "91", appointment_id: "51", doctor_id: "21", local_date: "2027-01-01", token_number: 7, state: "waiting", position: 1, version: 4 },
        waiting_count: 1,
        in_consultation_count: 0,
        queue_version: 6,
        observed_at: queue.observed_at,
      }, 200, '"4"');
      if (url.pathname === "/api/v1/appointments/queue-entries/91/start" && init.method === "POST") return failure(409, "not_queue_head", "Queue head changed.");
      if (url.pathname === "/api/v1/appointments/journeys/151") return json(journey, 200, '"6"');
      return undefined;
    });

    await screen.findByText(/Patient ID\s+11/);
    fireEvent.click(screen.getByRole("button", { name: "Call next patient" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm start consultation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("queue head changed");
    await waitFor(() => expect(getCalls(fetcher).filter(([input]) => {
      const url = new URL(String(input), "http://pulsegrid.test");
      return url.pathname === "/api/v1/appointments/queues" && !url.searchParams.has("state");
    }).length).toBeGreaterThan(1));
    expect(writes(fetcher)).toHaveLength(1);
  });

  it("retries an uncertain queue start with the same idempotency key and ETag", async () => {
    let startAttempts = 0;
    const started = { ...queueEntry, state: "in_consultation" as const, position: null, version: 5 };
    const { fetcher } = setup("doctor", <DoctorQueuePage />, (url, init) => {
      if (url.pathname === "/api/v1/doctors/me") return json({ doctor: { id: "21", display_name: "Synthetic Doctor", active: true, version: 3 }, staff_user_id: "101" });
      if (url.pathname === "/api/v1/appointments/queues" && url.searchParams.get("state") === "waiting") return json(queue);
      if (url.pathname === "/api/v1/appointments/queues") return json(queue, 200, '"6"');
      if (url.pathname === "/api/v1/appointments/51/queue") return json({
        entry: { id: "91", appointment_id: "51", doctor_id: "21", local_date: "2027-01-01", token_number: 7, state: "waiting", position: 1, version: 4 },
        waiting_count: 1,
        in_consultation_count: 0,
        queue_version: 6,
        observed_at: queue.observed_at,
      }, 200, '"4"');
      if (url.pathname === "/api/v1/appointments/queue-entries/91/start" && init.method === "POST") {
        startAttempts += 1;
        return startAttempts === 1
          ? failure(503, "dependency_unavailable", "Appointment is temporarily unavailable.")
          : json(started, 200, '"5"');
      }
      if (url.pathname === "/api/v1/appointments/journeys/151") return json(journey, 200, '"6"');
      return undefined;
    });

    await screen.findByText(/Patient ID\s+11/);
    fireEvent.click(screen.getByRole("button", { name: "Call next patient" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm start consultation" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry original start command" }));
    expect(await screen.findByText(/Appointment service started queue token 7/)).toBeInTheDocument();
    const startWrites = writes(fetcher).filter(([url]) => String(url) === "/api/v1/appointments/queue-entries/91/start");
    expect(startWrites).toHaveLength(2);
    expect(requestHeaders(startWrites[0][1]!).get("Idempotency-Key")).toBe(requestHeaders(startWrites[1][1]!).get("Idempotency-Key"));
    expect(requestHeaders(startWrites[0][1]!).get("If-Match")).toBe('"4"');
    expect(requestHeaders(startWrites[1][1]!).get("If-Match")).toBe('"4"');
  });

  it("does not call the doctor API when role hints do not include doctor", async () => {
    const { fetcher } = setup("pharmacist", <DoctorQueuePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("requires the doctor role");
    expect(fetcher).toHaveBeenCalledTimes(0);
  });

  it("refreshes the current queue when a hidden tab becomes visible again", async () => {
    let visibility: DocumentVisibilityState = "visible";
    const originalDescriptor = Object.getOwnPropertyDescriptor(document, "visibilityState");
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
    let currentQueue = queue;
    const { fetcher } = setup("doctor", <DoctorQueuePage />, (url) => {
      if (url.pathname === "/api/v1/doctors/me") return json({ doctor: { id: "21", display_name: "Synthetic Doctor", active: true, version: 3 }, staff_user_id: "101" });
      if (url.pathname === "/api/v1/appointments/queues") return json(currentQueue, 200, `"${currentQueue.version}"`);
      if (url.pathname === "/api/v1/appointments/journeys/151") return json(journey, 200, '"6"');
      return undefined;
    });
    await screen.findByText(/Patient ID\s+11/);
    visibility = "hidden";
    fireEvent(document, new Event("visibilitychange"));
    currentQueue = { ...queue, items: [], waiting_count: 0, version: 7 };
    visibility = "visible";
    fireEvent(document, new Event("visibilitychange"));
    expect(await screen.findByText("No queue entries were returned for this doctor and schedule date.")).toBeInTheDocument();
    expect(getCalls(fetcher).filter(([input]) => new URL(String(input), "http://pulsegrid.test").pathname === "/api/v1/appointments/queues").length).toBeGreaterThan(1);
    if (originalDescriptor) Object.defineProperty(document, "visibilityState", originalDescriptor);
  });
});

describe("patient journey and pharmacy fulfillment", () => {
  it("inspects stages, reconciles with ETag, and discharges only an eligible journey", async () => {
    let currentJourney = journey;
    const { fetcher } = setup("receptionist", <ReceptionWorkflowPanel />, (url, init) => {
      if (url.pathname === "/api/v1/appointments/journeys/151" && init.method !== "POST") return json(currentJourney, 200, `"${currentJourney.version}"`);
      if (url.pathname === "/api/v1/appointments/journeys/151/reconcile" && init.method === "POST") {
        currentJourney = { ...currentJourney, version: 7 };
        return json(currentJourney, 200, '"7"');
      }
      if (url.pathname === "/api/v1/appointments/journeys/151/discharge" && init.method === "POST") {
        currentJourney = { ...currentJourney, state: "discharged", discharge_eligible: false, version: 8 };
        return json(currentJourney, 200, '"8"');
      }
      return undefined;
    });
    await screen.findByLabelText("Journey ID");
    fill("Journey ID", "151");
    fireEvent.submit(screen.getByLabelText("Journey ID").closest("form")!);
    expect(await screen.findByText("billing")).toBeInTheDocument();
    await confirm("Reconcile journey");
    const reconcileCall = writes(fetcher).at(-1)!;
    expect(String(reconcileCall[0])).toBe("/api/v1/appointments/journeys/151/reconcile");
    expect(JSON.parse(String(reconcileCall[1]?.body))).toEqual({});
    expect(requestHeaders(reconcileCall[1]!).get("If-Match")).toBe('"6"');
    await waitFor(() => expect(getCalls(fetcher).filter(([input]) => String(input) === "/api/v1/appointments/journeys/151").length).toBeGreaterThan(1));
    fill("Reason", "Administrative discharge after owner snapshots.");
    await confirm("Discharge journey");
    const dischargeCall = writes(fetcher).at(-1)!;
    expect(String(dischargeCall[0])).toBe("/api/v1/appointments/journeys/151/discharge");
    expect(JSON.parse(String(dischargeCall[1]?.body))).toEqual({ reason: "Administrative discharge after owner snapshots." });
    expect(requestHeaders(dischargeCall[1]!).get("If-Match")).toBe('"7"');
    expect(await screen.findByText("discharged")).toBeInTheDocument();
  });

  it("checks current prescription state before pharmacy summary and shows stock snapshots", async () => {
    const prescription = {
      id: "71",
      consultation_id: "61",
      patient_id: "11",
      revision: 2,
      state: "issued",
      items: [{ id: "72", medicine_id: "81", quantity: 5, dosage: "Sensitive synthetic dosage", instructions: "Sensitive instructions" }],
      version: 3,
    };
    const { fetcher } = setup("pharmacist", <StaffFulfillmentPanel />, (url) => {
      if (url.pathname === "/api/v1/records/prescriptions/71") return json(prescription, 200, '"3"');
      if (url.pathname === "/api/v1/pharmacy/prescriptions/71/fulfillment") return json(fulfillment, 200, '"4"');
      if (url.pathname === "/api/v1/pharmacy/inventory" && url.searchParams.get("medicine_id") === "81") return json({
        items: [{ id: "82", medicine_id: "81", batch_code: "SYN-A", expires_on: "2027-01-01", on_hand: 5, reserved: 2, available: 3, version: 2 }],
        next_cursor: null,
      });
      if (url.searchParams.has("limit")) return json({ items: [], next_cursor: null });
      return undefined;
    });
    await screen.findByLabelText("Prescription ID for fulfillment status");
    fill("Prescription ID for fulfillment status", "71");
    fireEvent.submit(screen.getByLabelText("Prescription ID for fulfillment status").closest("form")!);
    expect(await screen.findByText(/Pharmacy review is required/)).toBeInTheDocument();
    expect(screen.getByText(/reserved 2; dispensed 1; remaining 4/)).toBeInTheDocument();
    expect(screen.queryByText("Sensitive synthetic dosage")).not.toBeInTheDocument();
    const recordCallIndex = fetcher.mock.calls.findIndex(([input]) => String(input) === "/api/v1/records/prescriptions/71");
    const fulfillmentCallIndex = fetcher.mock.calls.findIndex(([input]) => String(input) === "/api/v1/pharmacy/prescriptions/71/fulfillment");
    expect(recordCallIndex).toBeGreaterThanOrEqual(0);
    expect(fulfillmentCallIndex).toBeGreaterThan(recordCallIndex);

    fill("Medicine ID", "81");
    fireEvent.submit(screen.getByLabelText("Medicine ID").closest("form")!);
    expect(await screen.findByText(/Batch SYN-A/)).toBeInTheDocument();
    expect(screen.getByText(/available 3/)).toBeInTheDocument();
  });

  it("reserves, revalidates and dispenses using owner ETags", async () => {
    const prescription = {
      id: "71", consultation_id: "61", patient_id: "11", revision: 2, state: "issued",
      items: [{ id: "72", medicine_id: "81", quantity: 5, dosage: "Synthetic dosage", instructions: "Synthetic instructions" }], version: 3,
    };
    let reservation = {
      id: "91", patient_id: "11", prescription_id: "71", state: "reserved",
      items: [{ prescription_item_id: "72", medicine_id: "81", quantity: 2 }],
      expires_at: "2027-01-01T09:30:00Z", version: 2,
    };
    let reservationCreated = false;
    const { fetcher } = setup("pharmacist", <StaffFulfillmentPanel />, (url, init) => {
      if (url.pathname === "/api/v1/records/prescriptions/71") return json(prescription, 200, '"3"');
      if (url.pathname === "/api/v1/pharmacy/reservations" && init.method === "POST") {
        reservationCreated = true;
        return json(reservation, 201, '"2"');
      }
      if (url.pathname === "/api/v1/pharmacy/reservations" && init.method !== "POST") return json({ items: reservationCreated ? [reservation] : [], next_cursor: null });
      if (url.pathname === "/api/v1/pharmacy/reservations/91" && init.method !== "POST") return json(reservation, 200, `"${reservation.version}"`);
      if (url.pathname === "/api/v1/pharmacy/reservations/91/revalidate" && init.method === "POST") {
        reservation = { ...reservation, version: 3 };
        return json(reservation, 200, '"3"');
      }
      if (url.pathname === "/api/v1/pharmacy/reservations/91/dispense" && init.method === "POST") return json({ id: "101", reservation_id: "91", prescription_id: "71", patient_id: "11", appointment_id: "51", items: [], completed_at: "2027-01-01T09:00:00Z", version: 1 }, 201, '"4"');
      if (url.pathname === "/api/v1/pharmacy/dispensings" && init.method !== "POST") return json({ items: [], next_cursor: null });
      if (url.searchParams.has("limit")) return json({ items: [], next_cursor: null });
      return undefined;
    });
    await screen.findByLabelText("Prescription ID");
    fill("Prescription ID", "71");
    fireEvent.submit(screen.getByLabelText("Prescription ID").closest("form")!);
    fireEvent.click(await screen.findByRole("button", { name: "Request medicines from prescription 71" }));
    fill("Quantity for item 72 (medicine 81, prescribed 5)", "2");
    await confirm("Reserve medicines");
    expect(await screen.findByRole("button", { name: "View reservation 91" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View reservation 91" }));
    await screen.findByRole("button", { name: commandLabels("Revalidate reservation").review });
    await confirm("Revalidate reservation");
    await waitFor(() => expect(getCalls(fetcher).filter(([input]) => String(input) === "/api/v1/pharmacy/reservations/91").length).toBeGreaterThan(1));
    await screen.findByRole("button", { name: commandLabels("Dispense reservation").review });
    await confirm("Dispense reservation");
    expect(await screen.findByText(/Dispensed \(…101\)/)).toBeInTheDocument();
    const dispenseCall = writes(fetcher).find(([url]) => String(url) === "/api/v1/pharmacy/reservations/91/dispense")!;
    expect(JSON.parse(String(dispenseCall[1]?.body))).toEqual({});
    expect(requestHeaders(dispenseCall[1]!).get("If-Match")).toBe('"3"');
    expect(writes(fetcher)).toHaveLength(3);
  });

  it("shows service errors without inventing a fulfillment result", async () => {
    setup("pharmacist", <StaffFulfillmentPanel />, (url) => {
      if (url.pathname === "/api/v1/records/prescriptions/71") return json({ id: "71", revision: 2, state: "issued" });
      if (url.pathname === "/api/v1/pharmacy/prescriptions/71/fulfillment") return failure(503, "dependency_unavailable", "Pharmacy is temporarily unavailable.");
      if (url.searchParams.has("limit")) return json({ items: [], next_cursor: null });
      return undefined;
    });
    await screen.findByLabelText("Prescription ID for fulfillment status");
    fill("Prescription ID for fulfillment status", "71");
    fireEvent.submit(screen.getByLabelText("Prescription ID for fulfillment status").closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Pharmacy is temporarily unavailable.");
    expect(screen.queryByText(/No completed dispensings are reported/)).not.toBeInTheDocument();
  });
});
