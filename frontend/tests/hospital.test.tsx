import { sortEmergencyQueue } from "../src/hospital/billingEmergency";
import { commandLabels } from "./commandLabels";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider, type Role } from "../src/auth/authContext";
import { createApiClient } from "../src/api/client";
import { PulseGridRoutes } from "../src/app/App";
import { CommandForm, date, id, integer, money, utc } from "../src/hospital/ui";

import type {
  PatientProfile,
  Doctor,
  Slot,
  Appointment,
  Consultation,
  Prescription,
  Reservation,
  Invoice,
  Emergency,
  Proposal,
  Batch,
  Dispensing,
  MedicalRecord,
} from "../src/hospital/models";

const profile = {
  id: "11",
  user_id: "101",
  display_name: "Synthetic Patient",
  date_of_birth: "2000-01-01",
  version: 2,
} satisfies PatientProfile;
const doctor = {
  id: "21",
  display_name: "Synthetic Doctor",
  specialties: [{ id: "31", name: "General medicine" }],
  active: true,
  version: 3,
} satisfies Doctor;
const slot = {
  id: "41",
  doctor_id: "21",
  starts_at: "2027-01-01T09:00:00Z",
  ends_at: "2027-01-01T09:30:00Z",
  state: "bookable",
  revision: 4,
} satisfies Slot;
const appointment = {
  id: "51",
  journey_id: null,
  patient_id: "11",
  doctor_id: "21",
  slot_id: "41",
  starts_at: slot.starts_at,
  ends_at: slot.ends_at,
  state: "confirmed",
  version: 5,
} satisfies Appointment;
const clinicalContent = {
  summary: "Synthetic summary",
  assessment: "Synthetic assessment",
  plan: "Synthetic plan",
};
const consultation = {
  id: "61",
  appointment_id: "51",
  patient_id: "11",
  doctor_id: "21",
  status: "draft",
  clinical_content: clinicalContent,
  revision: 1,
  version: 2,
} satisfies Consultation;
const prescription = {
  id: "71",
  consultation_id: "61",
  patient_id: "11",
  journey_id: null,
  revision: 1,
  state: "issued",
  items: [
    {
      id: "72",
      medicine_id: "81",
      quantity: 5,
      dosage: "Synthetic dosage",
      instructions: "Synthetic instructions",
    },
  ],
  version: 2,
} satisfies Prescription;
const reservation = {
  id: "91",
  patient_id: "11",
  prescription_id: "71",
  state: "reserved",
  items: [{ prescription_item_id: "72", medicine_id: "81", quantity: 2 }],
  expires_at: "2027-01-01T09:30:00Z",
  version: 2,
} satisfies Reservation;
const invoice = {
  id: "111",
  journey_id: null,
  appointment_id: "51",
  patient_id: "11",
  status: "open",
  items: [],
  total_minor: 10000,
  paid_minor: 0,
  balance_minor: 10000,
  currency: "INR",
  version: 3,
} satisfies Invoice;
const emergency = {
  id: "121",
  state: "triaged",
  reported_urgency: "urgent",
  assigned_priority: 2,
  created_at: "2027-01-01T09:00:00Z",
  updated_at: "2027-01-01T09:01:00Z",
  version: 3,
} satisfies Emergency;
const proposal = {
  id: "131",
  doctor_id: "21",
  revision: 5,
  status: "pending",
  timezone: "Asia/Kolkata",
  slot_minutes: 30,
  intervals: [],
  conflicts: [],
  version: 1,
} satisfies Proposal;
const medicalRecord = {
  id: "62",
  consultation_id: "61",
  patient_id: "11",
  content: clinicalContent,
  revision: 1,
  supersedes_id: null,
  version: 1,
} satisfies MedicalRecord;
const batch = {
  id: "82",
  medicine_id: "81",
  batch_code: "SYN-A",
  expires_on: "2027-01-01",
  on_hand: 10,
  reserved: 0,
  available: 10,
  version: 1,
} satisfies Batch;
const dispensing = {
  id: "92",
  reservation_id: "91",
  prescription_id: "71",
  patient_id: "11",
  appointment_id: "51",
  items: [
    { id: "93", prescription_item_id: "72", medicine_id: "81", quantity: 2 },
  ],
  completed_at: "2027-01-01T09:00:00Z",
  version: 1,
} satisfies Dispensing;
function json(data: unknown, status = 200, etag = '"2"') {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ETag: etag },
  });
}
function failure(status: number, code: string, message: string) {
  return json(
    {
      error: {
        code,
        message,
        request_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      },
    },
    status,
  );
}
type Handler = (
  path: string,
  init: RequestInit,
  url: URL,
) => Response | Promise<Response> | undefined;
function setup(
  path: string,
  role: Role,
  handler: Handler = () => undefined,
  component?: React.ReactNode,
) {
  const fetcher = vi.fn<typeof fetch>(async (input, init = {}) => {
    const url = new URL(String(input), "http://pulsegrid.test");
    const response = await handler(url.pathname, init, url);
    if (response) return response;
    if (url.pathname === "/api/v1/patients/me")
      return json(profile, 200, '"2"');
    if (url.pathname === "/api/v1/doctors/me")
      return json({ doctor, staff_user_id: "101" }, 200, '"3"');
    if (url.pathname === "/api/v1/appointments/availability")
      return json({
        slots: [slot],
        accepted_revision: 4,
        observed_at: "2027-01-01T08:00:00Z",
      });
    if (url.searchParams.has("limit"))
      return json({ items: [], next_cursor: null });
    return failure(404, "not_found", "Resource not found.");
  });
  const token = `header.${btoa(JSON.stringify({ sub: "101", roles: [role] }))}.signature`;
  const auth = {
    login: async () => ({
      access_token: token,
      token_type: "Bearer" as const,
      expires_in: 600,
    }),
    refresh: async () => ({
      access_token: token,
      token_type: "Bearer" as const,
      expires_in: 600,
    }),
    register: async () => profile,
    logout: async () => undefined,
  };
  const view = render(
    <AuthProvider client={auth} apiClient={createApiClient({ fetcher })}>
      <MemoryRouter initialEntries={[path]}>
        {component ?? <PulseGridRoutes />}
      </MemoryRouter>
    </AuthProvider>,
  );
  return { fetcher, view };
}
function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
async function command(title: string) {
  fireEvent.click(screen.getByRole("button", { name: commandLabels(title).review }));
  fireEvent.click(
    await screen.findByRole("button", { name: commandLabels(title).confirm }),
  );
}
function writes(fetcher: ReturnType<typeof setup>["fetcher"]) {
  return fetcher.mock.calls.filter(
    ([, init]) => init?.method && init.method !== "GET",
  );
}
function lastBody(fetcher: ReturnType<typeof setup>["fetcher"]) {
  return JSON.parse(String(writes(fetcher).at(-1)?.[1]?.body));
}
function expectConditional(
  fetcher: ReturnType<typeof setup>["fetcher"],
  path: string,
  method = "POST",
  etag = '"2"',
) {
  const [url, init] = writes(fetcher).at(-1)!;
  expect(String(url)).toBe(path);
  expect(init!.method).toBe(method);
  const headers = new Headers(init!.headers);
  expect(headers.get("If-Match")).toBe(etag);
  expect(headers.get("Authorization")).toContain("Bearer ");
  if (method === "POST")
    expect(headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
}

describe("patient profiles and appointment commands", () => {
  it("loads and edits a profile with its ETag", async () => {
    const { fetcher } = setup("/patient/dashboard", "patient", (path, init) =>
      path === "/api/v1/patients/me" && init.method === "PATCH"
        ? json({ ...profile, display_name: "Updated", version: 3 }, 200, '"3"')
        : undefined,
    );
    const profileMenu = await screen.findByText("Your profile",{selector:"summary"});
    const account = profileMenu.closest(".account-menu")!;
    fireEvent.click(account.querySelector(":scope > summary")!);
    fireEvent.click(profileMenu);
    await screen.findByDisplayValue(profile.display_name);
    fill("Display name", "Updated");
    await command("Save profile");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(fetcher, "/api/v1/patients/me", "PATCH");
    expect(lastBody(fetcher)).toEqual({ display_name: "Updated" });
  });
  it("validates empty names and future births without a mutation", async () => {
    const { fetcher } = setup("/patient/dashboard", "patient");
    const profileMenu = await screen.findByText("Your profile",{selector:"summary"});
    const account = profileMenu.closest(".account-menu")!;
    fireEvent.click(account.querySelector(":scope > summary")!);
    fireEvent.click(profileMenu);
    await screen.findByDisplayValue(profile.display_name);
    fill("Display name", " ");
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Save profile").review }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Display name is required",
    );
    fill("Display name", "Synthetic");
    fill("Date of birth", "2999-01-01");
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Save profile").review }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "cannot be in the future",
    );
    expect(writes(fetcher)).toHaveLength(0);
  });
  it("shows profile loading and owner failure rather than invented data", async () => {
    let release!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    setup("/patient/dashboard", "patient", () => pending);
    expect(await screen.findByText("Loading resource…")).toBeInTheDocument();
    release(
      failure(503, "dependency_unavailable", "Patient service unavailable."),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Patient service unavailable",
    );
    expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
  });
  it("searches doctors, paginates opaque cursors and resets cursors when filters change", async () => {
    const { fetcher } = setup(
      "/patient/doctors",
      "patient",
      (path, init, url) =>
        path === "/api/v1/doctors" && init.method === "GET"
          ? json({
              items: [doctor],
              next_cursor: url.searchParams.has("cursor")
                ? null
                : "opaque cursor",
            })
          : undefined,
    );
    await screen.findByRole("button", { name: "View doctor 21" });
    fill("Doctor search", "S");
    fireEvent.click(screen.getByRole("button", { name: "Search doctors" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("2 to 100");
    fill("Doctor search", "Synthetic");
    fill("Specialty ID filter", "31");
    fireEvent.click(screen.getByRole("button", { name: "Search doctors" }));
    await waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) =>
          String(url).includes("q=Synthetic&specialty_id=31&limit=20"),
        ),
      ).toBe(true),
    );
    const doctors = screen
      .getByRole("heading", { name: "Doctors" })
      .closest("section")!;
    await waitFor(() =>
      expect(
        within(doctors).getByRole("button", { name: "Next page" }),
      ).toBeEnabled(),
    );
    fireEvent.click(within(doctors).getByRole("button", { name: "Next page" }));
    await waitFor(() =>
      expect(
        fetcher.mock.calls.some(([url]) =>
          String(url).includes("cursor=opaque%20cursor"),
        ),
      ).toBe(true),
    );
    fill("Doctor search", "Updated");
    fireEvent.click(screen.getByRole("button", { name: "Search doctors" }));
    await waitFor(() =>
      expect(String(fetcher.mock.calls.at(-1)![0])).toBe(
        "/api/v1/doctors?q=Updated&specialty_id=31&limit=20",
      ),
    );
  });
  it("opens the first owner profile without an empty selection card and keeps internal IDs in Details",async()=>{
    setup('/patient/doctors','patient',(path)=>path==='/api/v1/doctors'?json({items:[doctor],next_cursor:null}):path==='/api/v1/doctors/21'?json(doctor,200,'"3"'):undefined);
    expect(await screen.findByRole('heading',{name:doctor.display_name,level:2})).toBeInTheDocument();
    expect(screen.queryByText('Select your doctor')).not.toBeInTheDocument();
    expect(screen.queryByText('Internal Doctor ID')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'Details'}));
    expect(await screen.findByText('Internal Doctor ID')).toBeInTheDocument();
    expect(screen.getByText(doctor.id)).toBeInTheDocument();
  });
  it("does not expose receptionist appointment links to an administrator without that role",async()=>{
    const {fetcher}=setup('/admin/doctors','hospital_admin',path=>path==='/api/v1/doctors'?json({items:[doctor],next_cursor:null}):path==='/api/v1/doctors/21'?json(doctor,200,'"3"'):undefined);
    await screen.findByRole('heading',{name:doctor.display_name,level:2});
    expect(screen.queryByRole('link',{name:'Appointments'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Book Appointment'})).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([url])=>String(url).startsWith('/api/v1/appointments?'))).toBe(false);
  });
  it("books accepted availability with own profile ID, clears selection and reloads the available slots", async () => {
    let booked = false;
    const { fetcher } = setup(
      "/patient/appointments",
      "patient",
      (path, init) => {
        if (path === "/api/v1/appointments" && init.method === "POST") {
          booked = true;
          return json(appointment, 201);
        }
        if (path === "/api/v1/appointments/availability") return json({ slots: booked ? [] : [slot], accepted_revision: 4, observed_at: slot.starts_at });
        return undefined;
      },
    );
    await screen.findByLabelText("Doctor ID for availability");
    fill("Doctor ID for availability", "21");
    fireEvent.submit(
      screen.getByLabelText("Doctor ID for availability").closest("form")!,
    );
    fill("From (UTC)", "2027-01-01T00:00:00Z");
    fill("To (UTC)", "2027-01-02T00:00:00Z");
    fireEvent.click(
      await screen.findByRole("button", { name: /^Select 09:00 am, 1 Jan 2027 \(UTC\)$/i }),
    );
    expect(screen.getByRole("button",{name:commandLabels("Book appointment").review})).toBeInTheDocument();
    fill("From (UTC)", "2027-01-02T00:00:00Z");
    expect(screen.queryByRole("button",{name:commandLabels("Book appointment").review})).not.toBeInTheDocument();
    fill("From (UTC)", "2027-01-01T00:00:00Z");
    fireEvent.click(await screen.findByRole("button",{name:/^Select 09:00 am, 1 Jan 2027 \(UTC\)$/i}));
    await command("Book appointment");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expect(lastBody(fetcher)).toEqual({
      patient_id: "11",
      slot_id: "41",
      expected_schedule_revision: 4,
    });
    expect(
      await screen.findByText("Appointment booked"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Review booking" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Booked 09:00 am UTC/i })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^Select 09:00 am/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Book another appointment" }));
    expect(screen.queryByRole("button", { name: "Review booking" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm booking" })).not.toBeInTheDocument();
  });
  it("rejects non-UTC and overlong availability windows without a request", async () => {
    const { fetcher } = setup("/patient/appointments", "patient");
    await screen.findByLabelText("Doctor ID for availability");
    fill("Doctor ID for availability", "21");
    fireEvent.submit(
      screen.getByLabelText("Doctor ID for availability").closest("form")!,
    );
    await waitFor(() => expect(fetcher.mock.calls.some(([url]) => String(url).includes("/availability"))).toBe(true));
    const availabilityCalls = fetcher.mock.calls.filter(([url]) => String(url).includes("/availability")).length;
    fill("From (UTC)", "2027-01-01T00:00:00+05:30");
    expect(await screen.findByRole("alert")).toHaveTextContent("UTC timestamp");
    fill("To (UTC)", "2027-03-02T00:00:00Z");
    fill("From (UTC)", "2027-01-01T00:00:00Z");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "at most 31 days",
    );
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).includes("/availability")).length,
    ).toBe(availabilityCalls);
  });
  it("cancels an appointment with reason and resource ETag", async () => {
    const { fetcher } = setup(
      "/patient/appointments",
      "patient",
      (path, init) => {
        if (path === "/api/v1/appointments")
          return json({ items: [appointment], next_cursor: null });
        if (path === "/api/v1/appointments/51")
          return json(appointment, 200, '"5"');
        if (path.endsWith("/cancel") && init.method === "POST")
          return json({ ...appointment, state: "cancelled", version: 6 });
        return undefined;
      },
    );
    fireEvent.click(await screen.findByRole("button", { name: "My Appointments" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Cancel appointment 51" }),
    );
    expect(fetcher.mock.calls.some(([url])=>String(url).includes("patient_id=11"))).toBe(true);
    await screen.findByLabelText("Reason for cancelling");
    fill("Reason for cancelling", "Synthetic cancellation");
    await command("Cancel appointment");
    await screen.findByText("Appointment cancelled.");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(fetcher, "/api/v1/appointments/51/cancel", "POST", '"5"');
    expect(lastBody(fetcher)).toEqual({ reason: "Synthetic cancellation" });
  });
  it("reschedules the same appointment to an accepted target slot", async () => {
    const { fetcher } = setup(
      "/receptionist/appointments",
      "receptionist",
      (path, init) => {
        if (path === "/api/v1/appointments")
          return json({ items: [appointment], next_cursor: null });
        if (path === "/api/v1/appointments/51")
          return json(appointment, 200, '"5"');
        if (path.endsWith("/reschedule") && init.method === "POST")
          return json({ ...appointment, version: 6 });
        return undefined;
      },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Appointments" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Reschedule appointment 51" }),
    );
    await screen.findByLabelText("Target doctor ID");
    fill("Target doctor ID", "21");
    fireEvent.submit(
      screen.getByLabelText("Target doctor ID").closest("form")!,
    );
    fill("From (UTC)", "2027-01-01T00:00:00Z");
    fill("To (UTC)", "2027-01-02T00:00:00Z");
    fireEvent.click(
      await screen.findByRole("button", { name: /^Select 09:00 am, 1 Jan 2027 \(UTC\)$/i }),
    );
    await command("Reschedule appointment");
    await screen.findByText(/^Appointment moved to /);
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(
      fetcher,
      "/api/v1/appointments/51/reschedule",
      "POST",
      '"5"',
    );
    expect(lastBody(fetcher)).toEqual({
      target_slot_id: "41",
      expected_schedule_revision: 4,
    });
  });
});

describe("command safety and states", () => {
  it("preserves exact POST key/body/precondition after ambiguous failure and offers explicit retry", async () => {
    let attempts = 0;
    const { fetcher } = setup(
      "/",
      "patient",
      (path, init) => {
        if (path === "/api/v1/test" && init.method === "POST") {
          attempts++;
          if (attempts === 1) throw new TypeError("offline");
          return json({ id: "1" }, 201);
        }
        return undefined;
      },
      <CommandForm
        title="Test command"
        path="/api/v1/test"
        conditional
        etag='"3"'
        fields={[{ name: "name", label: "Name", required: true }]}
      />,
    );
    fill("Name", "Original");
    await command("Test command");
    expect(
      await screen.findByRole("button", { name: "Retry original command" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(writes(fetcher)).toHaveLength(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Retry original command" }),
    );
    await screen.findByText("Test command: done.");
    const calls = writes(fetcher);
    expect(calls).toHaveLength(2);
    expect(calls[0][1]?.body).toBe(calls[1][1]?.body);
    expect(new Headers(calls[0][1]?.headers).get("Idempotency-Key")).toBe(
      new Headers(calls[1][1]?.headers).get("Idempotency-Key"),
    );
    expect(new Headers(calls[1][1]?.headers).get("If-Match")).toBe('"3"');
  });
  it("requires confirmation and allows editing without sending", () => {
    const { fetcher } = setup(
      "/",
      "patient",
      () => undefined,
      <CommandForm title="Test command" path="/api/v1/test" />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Test command").review }),
    );
    expect(writes(fetcher)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(
      screen.getByRole("button", { name: commandLabels("Test command").review }),
    ).toBeEnabled();
  });
  it("reports stale versions with reload guidance and does not retry PATCH", async () => {
    const { fetcher } = setup(
      "/",
      "patient",
      () => failure(412, "version_conflict", "Stale version."),
      <CommandForm
        title="Edit"
        path="/api/v1/test"
        method="PATCH"
        conditional
        etag='"2"'
      />,
    );
    await command("Edit");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Refresh to load the latest version",
    );
    expect(writes(fetcher)).toHaveLength(1);
    expect(
      screen.queryByRole("button", { name: "Retry original command" }),
    ).not.toBeInTheDocument();
  });
  it("disables duplicate submissions while pending", async () => {
    let release!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const { fetcher } = setup(
      "/",
      "patient",
      () => pending,
      <CommandForm title="Test command" path="/api/v1/test" />,
    );
    await command("Test command");
    expect(
      await screen.findByText("Sending…"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: commandLabels("Test command").confirm }),
    ).toBeDisabled();
    release(json({}));
    await screen.findByText("Test command: done.");
    expect(writes(fetcher)).toHaveLength(1);
  });
  it("disables conditional mutation without an owner ETag", () => {
    setup(
      "/",
      "patient",
      () => undefined,
      <CommandForm
        title="Edit"
        path="/api/v1/test"
        method="PATCH"
        conditional
        etag={null}
      />,
    );
    expect(screen.getByRole("button", { name: commandLabels("Edit").review })).toBeDisabled();
  });
  it("shows empty lists and deferred workflows without commands", async () => {
    const { fetcher, view } = setup("/patient/appointments?view=upcoming", "patient");
    expect(
      await screen.findByText("No upcoming appointments in this list."),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Upcoming (0)" })).toHaveAttribute("aria-selected", "true");
    view.unmount();
    const deferred = setup("/patient/check-in", "patient");
    expect(
      await screen.findByText("Secure QR check-in"),
    ).toBeInTheDocument();
    expect(writes(deferred.fetcher)).toHaveLength(0);
    expect(writes(fetcher)).toHaveLength(0);
  });
  it.each(["0", "-1", "1.1", "9223372036854775808", "1e5"])(
    "rejects invalid decimal ID %s",
    (value) => {
      expect(() => id(value)).toThrow();
    },
  );
  it("validates dates, UTC and integer money boundaries", () => {
    expect(() => date("2027-02-30")).toThrow();
    expect(() => utc("2027-02-30T00:00:00Z")).toThrow();
    expect(() => integer("1.5")).toThrow();
    expect(() => integer("9007199254740992")).toThrow();
    expect(id("9223372036854775807")).toBe("9223372036854775807");
  });
});

describe("clinical and pharmacy workflows", () => {
  it("creates assigned consultations with exact clinical content", async () => {
    const { fetcher } = setup(
      "/doctor/consultations",
      "doctor",
      (path, init) =>
        path === "/api/v1/records/consultations" && init.method === "POST"
          ? json(consultation, 201)
          : undefined,
    );
    await screen.findByLabelText("Assigned appointment ID");
    fill("Assigned appointment ID", "51");
    fill("Summary", "Synthetic summary");
    fill("Assessment", "Synthetic assessment");
    fill("Plan", "Synthetic plan");
    await command("Create consultation");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expect(lastBody(fetcher)).toEqual({
      appointment_id: "51",
      clinical_content: clinicalContent,
    });
  });
  it("finalizes a consultation with prescribed item fields and refreshes the register and dossier", async () => {
    let finalized = false;
    const { fetcher } = setup(
      "/doctor/consultations",
      "doctor",
      (path, init) => {
        if (path === "/api/v1/records/consultations")
          return json({ items: [{ ...consultation, status: finalized ? "finalized" : "draft" }], next_cursor: null });
        if (path === "/api/v1/records/consultations/61")
          return json({ ...consultation, status: finalized ? "finalized" : "draft", revision: finalized ? 2 : 1 });
        if (path.endsWith("/finalize") && init.method === "POST") {
          finalized = true;
          return json({
            consultation: { ...consultation, status: "finalized" },
            record: medicalRecord,
            prescription,
          });
        }
        return undefined;
      },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "View consultation 61" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Add prescribed medicine" }),
    );
    fill("Medicine ID 1", "81");
    fill("Quantity 1", "5");
    fill("Dosage 1", "Synthetic dosage");
    fill("Instructions 1", "Synthetic instructions");
    await command("Finalize consultation");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    await waitFor(() => expect(screen.getAllByText("Finalized")).toHaveLength(2));
    expect(screen.queryByText("Draft")).not.toBeInTheDocument();
    for (const path of ["/api/v1/records/consultations", "/api/v1/records/consultations/61"]) {
      expect(fetcher.mock.calls.filter(([url, init]) => new URL(String(url), "http://test").pathname === path && init?.method === "GET").length).toBeGreaterThanOrEqual(2);
    }
    expectConditional(fetcher, "/api/v1/records/consultations/61/finalize");
    expect(lastBody(fetcher)).toEqual({
      prescription_items: [
        {
          medicine_id: "81",
          quantity: 5,
          dosage: "Synthetic dosage",
          instructions: "Synthetic instructions",
        },
      ],
    });
    expect(
      await screen.findByText(/Medical record 62/),
    ).toBeInTheDocument();
  });
  it("reads own medical history and record detail", async () => {
    const { fetcher } = setup("/patient/records", "patient", (path, _init, url) => {
      if (path === "/api/v1/records/prescriptions" && url.searchParams.get("patient_id") === "11" && url.searchParams.get("consultation_id") === "61")
        return json({items:[{id:"71",consultation_id:"61",patient_id:"11",journey_id:null,revision:1,state:"issued",version:1,items:[{id:"72",medicine_id:"81",quantity:2,dosage:"Fixture dosage",instructions:"Fixture instructions"}]}],next_cursor:null});
      if (path === "/api/v1/records/patients/11")
        return json({
          items: [
            {
              id: "62",
              consultation_id: "61",
              patient_id: "11",
              revision: 1,
              created_at: "2027-01-01T00:00:00Z",
              version: 1,
            },
          ],
          next_cursor: null,
        });
      if (path === "/api/v1/records/62")
        return json({
          id: "62",
          consultation_id: "61",
          patient_id: "11",
          revision: 1,
          content: clinicalContent,
          supersedes_id: null,
          version: 1,
        });
      return undefined;
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "View record 62" }),
    );
    expect(await screen.findByText("Synthetic assessment")).toBeInTheDocument();
    expect(await screen.findByText("Fixture instructions")).toBeInTheDocument();
    expect(fetcher.mock.calls.some(([url])=>String(url).includes("prescriptions?patient_id=11&consultation_id=61"))).toBe(true);
  });
  it("uses pharmacist prescription lookup without bulk clinical lists, then reserves items", async () => {
    const { fetcher } = setup(
      "/pharmacist/prescriptions",
      "pharmacist",
      (path, init) =>
        path === "/api/v1/records/prescriptions/71"
          ? json(prescription)
          : path === "/api/v1/pharmacy/reservations" && init.method === "POST"
            ? json(reservation, 201)
            : undefined,
    );
    await screen.findByLabelText("Prescription ID");
    fill("Prescription ID", "71");
    fireEvent.submit(screen.getByLabelText("Prescription ID").closest("form")!);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Request medicines from this prescription",
      }),
    );
    fill("Quantity for item 72 (medicine 81, prescribed 5)", "2");
    await command("Reserve medicines");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expect(lastBody(fetcher)).toEqual({
      prescription_id: "71",
      items: [{ prescription_item_id: "72", quantity: 2 }],
    });
    expect(
      fetcher.mock.calls.some(([url]) =>
        String(url).startsWith("/api/v1/records/prescriptions?"),
      ),
    ).toBe(false);
  });
  it.each([
    ["Release reservation", "DELETE", ""],
    ["Revalidate reservation", "POST", "/revalidate"],
    ["Dispense reservation", "POST", "/dispense"],
  ] as const)("%s uses reservation ETag", async (title, method, suffix) => {
    const { fetcher } = setup(
      "/pharmacist/prescriptions",
      "pharmacist",
      (path, init) => {
        if (path === "/api/v1/pharmacy/reservations")
          return json({ items: [reservation], next_cursor: null });
        if (
          path === "/api/v1/pharmacy/reservations/91" &&
          init.method === "GET"
        )
          return json(reservation);
        if (
          init.method === method &&
          path === `/api/v1/pharmacy/reservations/91${suffix}`
        )
          return method === "DELETE"
            ? new Response(null, { status: 204 })
            : json(suffix === "/dispense" ? dispensing : reservation, 201);
        return undefined;
      },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "View reservation 91" }),
    );
    await screen.findByRole("button", { name: commandLabels(title).review });
    await command(title);
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(
      fetcher,
      `/api/v1/pharmacy/reservations/91${suffix}`,
      method,
    );
    expect(writes(fetcher)[0][1]?.body).toBe(
      method === "DELETE" ? undefined : "{}",
    );
  });
  it("validates stock delta and sends batch precondition in request body", async () => {
    const { fetcher } = setup(
      "/pharmacist/inventory",
      "pharmacist",
      (path, init) =>
        path === "/api/v1/pharmacy/inventory-adjustments" &&
        init.method === "POST"
          ? json({ movement_id: "83", batch }, 201)
          : undefined,
    );
    await screen.findByLabelText("Batch code");
    fill("Medicine ID", "81");
    fill("Batch code", "SYN-A");
    fill("Batch expiry", "2027-01-01");
    fill("Stock delta (positive or negative)", "0");
    fill("Expected batch version (0 for new batch)", "0");
    fill("Reason", "Synthetic setup");
    fireEvent.click(
      screen.getByRole("button", { name: commandLabels("Adjust stock").review }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "cannot be zero",
    );
    fill("Stock delta (positive or negative)", "10");
    await command("Adjust stock");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expect(lastBody(fetcher)).toEqual({
      medicine_id: "81",
      batch_code: "SYN-A",
      expires_on: "2027-01-01",
      delta: 10,
      expected_batch_version: 0,
      reason: "Synthetic setup",
    });
  });
});

describe("billing, emergency, doctor and administration workflows", () => {
  it("records simulated decline as a committed outcome and refreshes invoice", async () => {
    const { fetcher } = setup("/patient/billing", "patient", (path, init) => {
      if (path === "/api/v1/billing/invoices")
        return json({ items: [invoice], next_cursor: null });
      if (path === "/api/v1/billing/invoices/111")
        return json(invoice, 200, '"3"');
      if (path.endsWith("/payments") && init.method === "POST")
        return json(
          {
            id: "112",
            invoice_id: "111",
            amount_minor: 10000,
            currency: "INR",
            status: "declined",
            version: 1,
          },
          201,
        );
      return undefined;
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "View invoice 111" }),
    );
    fireEvent.click(await screen.findByText("Outcome options", {selector:"summary"}));
    await screen.findByLabelText("Payment result");
    fill("Payment result", "decline");
    await command("Submit payment");
    expect(
      await screen.findByText(
        /decline recorded; balance was not paid/,
      ),
    ).toBeInTheDocument();
    expectConditional(
      fetcher,
      "/api/v1/billing/invoices/111/payments",
      "POST",
      '"3"',
    );
    expect(lastBody(fetcher)).toEqual({
      amount_minor: 10000,
      currency: "INR",
      simulated_outcome: "decline",
    });
  });
  it("imports source IDs without sending frontend prices", async () => {
    const { fetcher } = setup(
      "/billing/invoices",
      "billing_staff",
      (path, init) => {
        if (path === "/api/v1/billing/invoices")
          return json({ items: [invoice], next_cursor: null });
        if (path === "/api/v1/billing/invoices/111")
          return json(invoice, 200, '"3"');
        if (path.endsWith("/charges") && init.method === "POST")
          return json(invoice);
        return undefined;
      },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "View invoice 111" }),
    );
    await screen.findByLabelText("Finalized consultation ID");
    fill("Finalized consultation ID", "61");
    fill("Completed dispensing IDs (comma separated)", "92");
    await command("Import charges manually");
    await screen.findByText("Charges imported. The receipt shows the new lines.");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(
      fetcher,
      "/api/v1/billing/invoices/111/charges",
      "POST",
      '"3"',
    );
    expect(lastBody(fetcher)).toEqual({
      consultation_id: "61",
      dispensing_ids: ["92"],
    });
  });
  it("submits emergency for own profile with advisory urgency only", async () => {
    const { fetcher } = setup("/patient/emergency", "patient", (path, init) =>
      path === "/api/v1/emergencies" && init.method === "POST"
        ? json(emergency, 201)
        : undefined,
    );
    await screen.findByLabelText("What's happening?");
    fill("What's happening?", "Synthetic request");
    fill("Reported urgency (advisory)", "urgent");
    await command("Submit emergency request");
    await screen.findByText("Request sent. It now appears in Your requests.");
    expect(screen.getByLabelText("What's happening?")).toHaveValue("");
    expect(screen.getByLabelText("Reported urgency (advisory)")).toHaveValue("unspecified");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expect(lastBody(fetcher)).toEqual({
      patient_id: "11",
      description: "Synthetic request",
      reported_urgency: "urgent",
    });
  });
  it("claims requests conditionally without arbitrary staff ID", async () => {
    const { fetcher } = setup(
      "/emergency/requests",
      "emergency_staff",
      (path, init) => {
        if (path === "/api/v1/emergencies")
          return json({ items: [emergency], next_cursor: null });
        if (path === "/api/v1/emergencies/121")
          return json(
            {
              ...emergency,
              patient_id: "11",
              description: "Synthetic",
              synthetic_contact: null,
              claimed_by_user_id: null,
              claim_expires_at: null,
            },
            200,
            '"3"',
          );
        if (path.endsWith("/claim") && init.method === "POST")
          return json({
            ...emergency,
            state: "claimed",
            patient_id: "11",
            description: "Synthetic",
            synthetic_contact: null,
            claimed_by_user_id: "101",
            claim_expires_at: "2027-01-01T09:16:00Z",
          });
        return undefined;
      },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Track request 121" }),
    );
    await screen.findByRole("button", { name: commandLabels("Claim request").review });
    await command("Claim request");
    await screen.findByText("Request claimed. You hold it for 15 minutes.");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(fetcher, "/api/v1/emergencies/121/claim", "POST", '"3"');
    expect(lastBody(fetcher)).toEqual({});
  });
  it("resolves doctor identity from doctors/me and submits closure proposal", async () => {
    const { fetcher } = setup("/doctor/dashboard", "doctor", (path, init) =>
      path === "/api/v1/doctors/21/schedules" && init.method === "POST"
        ? json(proposal, 202)
        : undefined,
    );
    fireEvent.click(await screen.findByRole("tab", { name: "Schedule changes" }));
    await screen.findByLabelText("Slot length (minutes)");
    fill("Slot length (minutes)", "30");
    fill("Current schedule reference", "4");
    await command("Submit schedule proposal");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(fetcher, "/api/v1/doctors/21/schedules", "POST", '"3"');
    expect(lastBody(fetcher)).toEqual({
      timezone: "Asia/Kolkata",
      slot_minutes: 30,
      expected_revision: 4,
      intervals: [],
    });
  });
  it("requests Appointment decision and explicitly reconciles Doctor", async () => {
    const { fetcher } = setup("/doctor/dashboard", "doctor", (path, init) => {
      if (path === "/api/v1/doctors/21/schedules")
        return json({ items: [proposal], next_cursor: null });
      if (path === "/api/v1/doctors/21/schedules/131")
        return json(proposal, 200, '"1"');
      if (path === "/api/v1/appointments/schedule-decisions")
        return json(
          {
            proposal_id: "131",
            doctor_id: "21",
            revision: 5,
            state: "rejected",
            reason_code: "booked_interval",
            conflicting_appointment_ids: ["51"],
            version: 1,
          },
          201,
        );
      if (path.endsWith("/reconcile") && init.method === "POST")
        return json({ ...proposal, status: "rejected" });
      return undefined;
    });
    fireEvent.click(await screen.findByRole("tab", { name: "Schedule changes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    await screen.findByLabelText("Current accepted revision");
    fill("Current accepted revision", "4");
    await command("Request schedule decision");
    expect(
      await screen.findByText(/Conflicting appointments: 51/),
    ).toBeInTheDocument();
    expect(lastBody(fetcher)).toEqual({
      doctor_id: "21",
      proposal_id: "131",
      expected_accepted_revision: 4,
    });
    await command("Apply accepted schedule");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(2));
    expectConditional(
      fetcher,
      "/api/v1/doctors/21/schedules/131/reconcile",
      "POST",
      '"1"',
    );
  });
  it("updates account roles independently of profile version", async () => {
    const user = {
      id: "101",
      email: "staff@example.test",
      display_name: "Synthetic Staff",
      roles: ["doctor"],
      state: "active",
      auth_version: 3,
      version: 7,
    };
    const { fetcher } = setup(
      "/admin/staff",
      "hospital_admin",
      (path, init) => {
        if (path === "/api/v1/patients/users")
          return json({ items: [user], next_cursor: null });
        if (path === "/api/v1/patients/users/101")
          return json(user, 200, '"7"');
        if (path.endsWith("/roles") && init.method === "PATCH")
          return json({ ...user, version: 8 });
        return undefined;
      },
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Open account Synthetic Staff" }),
    );
    await screen.findByLabelText("Roles (comma separated)");
    fill("Roles (comma separated)", "doctor, receptionist");
    await command("Replace roles");
    await waitFor(() => expect(writes(fetcher)).toHaveLength(1));
    expectConditional(
      fetcher,
      "/api/v1/patients/users/101/roles",
      "PATCH",
      '"7"',
    );
    expect(lastBody(fetcher)).toEqual({ roles: ["doctor", "receptionist"] });
  });
});

describe("large integer currency display", () => {
  it("preserves paise at the frozen safe-integer limit", () => {
    expect(money(Number.MAX_SAFE_INTEGER)).toBe("₹9,00,71,99,25,47,409.91");
    expect(money(1)).toBe("₹0.01");
  });
});


describe("final audit regressions", () => {
  it("orders emergency priority first, unassigned last, and older requests first within a priority", () => {
    const entries = [
      { ...emergency, id: "1", assigned_priority: null, created_at: "2026-10-25T01:00:00Z" },
      { ...emergency, id: "2", assigned_priority: 2, created_at: "2026-10-25T01:00:00Z" },
      { ...emergency, id: "3", assigned_priority: 1, created_at: "2026-10-25T03:00:00Z" },
      { ...emergency, id: "4", assigned_priority: 1, created_at: "2026-10-25T02:00:00Z" },
    ];
    expect(sortEmergencyQueue(entries).map(item => item.id)).toEqual(["4", "3", "2", "1"]);
    expect(entries.map(item => item.id)).toEqual(["1", "2", "3", "4"]);
  });
  it("keeps closed emergency cases below the open queue", async () => {
    const items = [
      { ...emergency, id: "10", state: "resolved", assigned_priority: 1 },
      { ...emergency, id: "11", state: "triaged", assigned_priority: 2 },
      { ...emergency, id: "12", state: "submitted", assigned_priority: null },
    ];
    setup("/emergency/requests", "emergency_staff", path => path === "/api/v1/emergencies" ? json({ items, next_cursor: null }) : undefined);
    await screen.findByRole("button", { name: "Track request 10" });
    const rows = document.querySelectorAll(".er-queue > li");
    expect(Array.from(rows).map(row => row.textContent)).toEqual([
      expect.stringContaining("P2"), expect.stringContaining("No priority"), "Closed", expect.stringContaining("P1"),
    ]);
  });
  it("shows every admin directory page, consecutive numbers and the active route", async () => {
    setup("/admin/staff", "hospital_admin");
    const nav = await screen.findByRole("navigation", { name: "Hospital administrator navigation" });
    const links = within(nav).getAllByRole("link");
    expect(links.map(link => link.getAttribute("href")).sort()).toEqual([
      "/admin/dashboard", "/admin/staff", "/admin/doctors", "/admin/control-room", "/admin/traces", "/admin/settings", "/system-design",
    ].sort());
    expect(links.map(link => link.querySelector(".directory-number")?.textContent)).toEqual(["01", "02", "03", "04", "05", "06", "07"]);
    expect(within(nav).getByRole("link", { name: "Staff & roles" })).toHaveAttribute("aria-current", "page");
  });
});


describe("emergency command receipts after version refresh", () => {
  it("retains priority and release confirmations while refreshing the case version", async () => {
    let current: Emergency = { ...emergency, state: "claimed", patient_id: "11", description: "Synthetic case", claimed_by_user_id: "101", claim_expires_at: "2027-01-01T10:00:00Z" };
    const { fetcher } = setup("/emergency/requests", "emergency_staff", (path, init) => {
      if (path === "/api/v1/emergencies") return json({ items: [current], next_cursor: null });
      if (path === "/api/v1/emergencies/121") return json(current, 200, `"${current.version}"`);
      if (path.endsWith("/priority") && init.method === "PATCH") {
        current = { ...current, assigned_priority: 1, version: current.version + 1 };
        return json(current, 200, `"${current.version}"`);
      }
      if (path.endsWith("/release") && init.method === "POST") {
        current = { ...current, state: "triaged", claimed_by_user_id: null, claim_expires_at: null, version: current.version + 1 };
        return json(current, 200, `"${current.version}"`);
      }
      return undefined;
    });
    fireEvent.click(await screen.findByRole("button", { name: "Change priority" }));
    fireEvent.click(screen.getByRole("button", { name: "Priority 1" }));
    fill("Reason for priority", "Synthetic priority review");
    await command("Set priority");
    await screen.findByText("Priority set to P1.");
    await waitFor(() => expect(document.querySelector(".er-case")).toHaveTextContent("P1"));
    expectConditional(fetcher, "/api/v1/emergencies/121/priority", "PATCH", '"3"');
    fireEvent.click(screen.getByRole("button", { name: "Release claim" }));
    fill("Reason for releasing", "Synthetic handoff");
    await command("Release claim");
    await screen.findByText("Claim released.");
    await waitFor(() => expect(document.querySelector(".er-case")).toHaveTextContent("triaged"));
    expect(screen.getByText("Claim released.")).toBeInTheDocument();
    expectConditional(fetcher, "/api/v1/emergencies/121/release", "POST", '"4"');
  });
});
