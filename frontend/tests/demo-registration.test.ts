import { webcrypto } from "node:crypto";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { handleMockRequest, resetMockState, exportMockState, importMockState } from "../dev-mock/handlers";
import type { PatientProfile } from "../src/api/authApi";

const patient = { email: "new-patient@example.test", password: "demo-password-123", display_name: "New Patient", date_of_birth: "2000-01-01", synthetic_contact: "new@example.test" };
async function request(path: string, method = "GET", body?: unknown, token?: string, extra: Record<string, string> = {}) {
  return handleMockRequest({ method, url: new URL(path, "https://demo.test"), body, headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), ...extra } });
}
const registrationHeaders = (key = "registration-1") => ({ "idempotency-key": key, "x-anonymous-command-id": "anonymous-registration-owner" });
async function register(input = patient, key = "registration-1") { return request("/api/v1/auth/register", "POST", input, undefined, registrationHeaders(key)); }
async function login(email = patient.email, password = patient.password) {
  const result = await request("/api/v1/auth/login", "POST", { email, password });
  expect(result.status).toBe(200);
  return (result.body as { access_token: string }).access_token;
}
beforeEach(() => { vi.stubGlobal("crypto", webcrypto); resetMockState(); });
afterEach(() => vi.unstubAllGlobals());

describe("public demo patient registration", () => {
  it("reports the Patient service ready without a session so the sign-up preflight passes", async () => {
    const result = await request("/api/v1/patients/health/ready");
    expect(result.status).toBe(200);
    expect(result.body).toEqual({ status: "ready", service: "patient", application: "ready" });
  });
  it("creates a new patient, signs in with the chosen password and returns that patient's profile", async () => {
    const result = await register();
    expect(result.status).toBe(201);
    const profile = result.body as PatientProfile;
    expect(profile).toMatchObject({ display_name: patient.display_name, date_of_birth: patient.date_of_birth, synthetic_contact: patient.synthetic_contact, version: 1 });
    expect(profile.id).not.toBe("2001");
    const token = await login();
    expect((await request("/api/v1/patients/me", "GET", undefined, token)).body).toEqual(profile);
    expect((await request("/api/v1/auth/login", "POST", { email: patient.email, password: "wrong-password" })).status).toBe(401);
  });
  it("normalizes email, rejects only real duplicates and preserves anonymous idempotency", async () => {
    const first = await register({ ...patient, email: "  New-Patient@Example.Test  " });
    expect(first.status).toBe(201);
    expect(await register({ ...patient, email: "  New-Patient@Example.Test  " })).toEqual(first);
    const duplicate = await register(patient, "registration-2");
    expect(duplicate.status).toBe(409);
    expect(duplicate.body).toMatchObject({ error: { code: "email_unavailable" } });
    expect((await register({ ...patient, email: "different@example.test" }, "registration-3")).status).toBe(201);
    expect((await register({ ...patient, email: "changed@example.test" })).status).toBe(422);
  });
  it("keeps new patient records empty, blocks other patients' resources and prevents role escalation", async () => {
    const result = await request("/api/v1/auth/register", "POST", { ...patient, roles: ["hospital_admin"] }, undefined, registrationHeaders());
    const profile = result.body as PatientProfile;
    const token = await login();
    const claims = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    expect(claims.roles).toEqual(["patient"]);
    for (const path of ["/api/v1/appointments", "/api/v1/records/prescriptions", "/api/v1/records/consultations", "/api/v1/billing/invoices", "/api/v1/emergencies", "/api/v1/appointments/waitlists", "/api/v1/appointments/journeys", `/api/v1/records/patients/${profile.id}`]) {
      const response = await request(path, "GET", undefined, token);
      expect(response.status, path).toBe(200);
      expect(response.body, path).toMatchObject({ items: [] });
    }
    for (const path of ["/api/v1/appointments/5101", "/api/v1/appointments/5101/queue", "/api/v1/appointments/5101/workflow", "/api/v1/appointments/journeys/9401", "/api/v1/pharmacy/reservations/7001", "/api/v1/billing/invoices/9701"]) {
      expect((await request(path, "GET", undefined, token)).status, path).toBeGreaterThanOrEqual(400);
    }
    expect((await request("/api/v1/patients/users", "GET", undefined, token)).status).toBe(403);
  });
  it("supports profile edits, booking and emergency requests with the new patient ID and persists across reload", async () => {
    const profile = (await register()).body as PatientProfile;
    const token = await login();
    expect((await request("/api/v1/patients/me", "PATCH", { display_name: "Updated Patient" }, token, { "if-match": '"1"' })).status).toBe(200);
    const from = new Date(Date.now() + 86400000).toISOString().slice(0, 10) + "T00:00:00Z";
    const to = new Date(Date.parse(from) + 86400000).toISOString();
    const availability = await request(`/api/v1/appointments/availability?doctor_id=8001&from=${from}&to=${to}`, "GET", undefined, token);
    const slot = (availability.body as { slots: { id: string; state: string; revision: number }[] }).slots.find(item => item.state === "bookable")!;
    const booking = await request("/api/v1/appointments", "POST", { patient_id: profile.id, slot_id: slot.id, expected_schedule_revision: slot.revision }, token, { "idempotency-key": "book-new-patient" });
    expect(booking.status).toBe(201);
    const emergency = await request("/api/v1/emergencies", "POST", { patient_id: profile.id, description: "Synthetic demo request", reported_urgency: "unspecified" }, token, { "idempotency-key": "new-emergency" });
    expect(emergency.status).toBe(201);
    const saved = exportMockState();
    expect(saved).not.toContain(patient.password);
    expect(saved).not.toContain(token);
    resetMockState();
    importMockState(saved);
    const restored = await login();
    expect((await request("/api/v1/patients/me", "GET", undefined, restored)).body).toMatchObject({ id: profile.id, display_name: "Updated Patient" });
    expect((await request("/api/v1/appointments", "GET", undefined, restored)).body).toMatchObject({ items: [booking.body] });
    expect((await request("/api/v1/emergencies", "GET", undefined, restored)).body).toMatchObject({ items: [expect.objectContaining({ id: (emergency.body as { id: string }).id })] });
    const seededToken = await login("patient@pulsegrid.test", "x");
    expect((await request(`/api/v1/appointments/${(booking.body as { id: string }).id}`, "GET", undefined, seededToken)).status).toBe(404);
  });
  it("does not accept malformed registration or passwords without anonymous command headers", async () => {
    expect((await request("/api/v1/auth/register", "POST", patient)).status).toBe(428);
    expect((await register({ ...patient, email: "invalid" })).status).toBe(422);
    expect((await register({ ...patient, password: "short" }, "short-password")).status).toBe(422);
  });
});

describe("demo browser storage", () => {
  it("restores an account and its data from browser storage and never stores the raw password", async () => {
    const { createDemoStore, DEMO_STORE_KEY } = await import("../dev-mock/storage");
    const values = new Map<string, string>();
    const store = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
    let run = createDemoStore(() => store);
    const result = await run({ method: "POST", url: new URL("https://demo.test/api/v1/auth/register"), body: patient, headers: registrationHeaders() });
    expect(result.status).toBe(201);
    expect(values.get(DEMO_STORE_KEY)).not.toContain(patient.password);
    resetMockState();
    run = createDemoStore(() => store);
    const restored = await run({ method: "POST", url: new URL("https://demo.test/api/v1/auth/login"), body: { email: patient.email, password: patient.password }, headers: {} });
    expect(restored.status).toBe(200);
    const token = (restored.body as { access_token: string }).access_token;
    expect(values.get(DEMO_STORE_KEY)).not.toContain(token);
  });
  it("does not report successful registration when browser storage cannot save it", async () => {
    const { createDemoStore } = await import("../dev-mock/storage");
    const run = createDemoStore(() => ({ getItem: () => null, setItem: () => { throw new DOMException("Quota exceeded", "QuotaExceededError"); } }));
    const result = await run({ method: "POST", url: new URL("https://demo.test/api/v1/auth/register"), body: patient, headers: registrationHeaders() });
    expect(result.status).toBe(503);
    expect((await register()).status).toBe(201);
  });
});

describe("new patient appointment workflows", () => {
  it("supports own waitlist and workflow operations without exposing another account", async () => {
    const owner = (await register()).body as PatientProfile;
    const token = await login();
    const from = new Date(Date.now() + 86400000).toISOString().slice(0, 10) + "T00:00:00Z";
    const to = new Date(Date.parse(from) + 86400000).toISOString();
    const availability = await request(`/api/v1/appointments/availability?doctor_id=8001&from=${from}&to=${to}`, "GET", undefined, token);
    const slot = (availability.body as { slots: { id: string; state: string; revision: number }[] }).slots.find(item => item.state === "bookable")!;
    const booked = await request("/api/v1/appointments", "POST", { patient_id: owner.id, slot_id: slot.id, expected_schedule_revision: slot.revision }, token, { "idempotency-key": "workflow-booking" });
    const appointmentId = (booked.body as { id: string }).id;
    const workflow = await request(`/api/v1/appointments/${appointmentId}/workflow`, "GET", undefined, token);
    expect(workflow.body).toMatchObject({ patient_id: owner.id, state: "booked", version: 1 });
    const second = (await register({ ...patient, email: "second@example.test", display_name: "Second Patient" }, "second-registration")).body as PatientProfile;
    const secondToken = await login("second@example.test");
    const waiting = await request("/api/v1/appointments/waitlists", "POST", { patient_id: second.id, slot_id: slot.id, expected_schedule_revision: slot.revision }, secondToken, { "idempotency-key": "waitlist-join" });
    expect(waiting.status).toBe(201);
    expect((await request("/api/v1/appointments/waitlists", "GET", undefined, token)).body).toMatchObject({ items: [] });
    const waitlistId = (waiting.body as { id: string }).id;
    expect((await request(`/api/v1/appointments/waitlists/${waitlistId}`, "GET", undefined, token)).status).toBe(404);
    expect((await request(`/api/v1/appointments/waitlists/${waitlistId}/withdraw`, "POST", { reason: "No longer needed" }, secondToken, { "if-match": '"1"', "idempotency-key": "withdraw-own" })).status).toBe(200);
    expect((await request(`/api/v1/appointments/${appointmentId}/cancel`, "POST", { reason: "Synthetic cancellation" }, token, { "if-match": '"1"', "idempotency-key": "cancel-own" })).status).toBe(200);
    expect((await request(`/api/v1/appointments/${appointmentId}/workflow`, "GET", undefined, token)).body).toMatchObject({ state: "cancelled" });
  });
});
