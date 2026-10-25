import type { Appointment, Batch, Consultation, Dispensing, Emergency, Grant, Invoice, MedicalRecord, Medicine, Payment, Prescription, Reservation, Slot, Tariff } from "../src/hospital/models";
import type { CheckinResult, Fulfillment, OwnQueue, TokenIssue, Workflow } from "../src/advanced/patient/contracts";
import { createState, users, type MockUser } from "./fixtures";
import { controlRoomSummary, traceList, traceSpans } from "./operations";

export interface MockRequest {
  method: string;
  url: URL;
  headers: Record<string, string | undefined>;
  body: unknown;
}

export interface MockResponse {
  status: number;
  body?: unknown;
  etag?: string;
  headers?: Record<string, string>;
}

const SESSION_COOKIE = "pulsegrid_mock_session";
// The real services honour larger limits; a small cap keeps Next/Previous exercised with 14 medicines.
const MOCK_PAGE_CAP = 12;

let state = createState();
const idempotency = new Map<string, { fingerprint: string; response: MockResponse }>();

export function resetMockState() {
  state = createState();
  idempotency.clear();
}

const error = (status: number, code: string, message: string): MockResponse => ({
  status,
  body: { error: { code, message, request_id: `mock-${status}` } },
});
const ok = (body: unknown, etag?: number, status = 200): MockResponse => ({
  status,
  body,
  ...(etag !== undefined ? { etag: `"${etag}"` } : {}),
});
const nextId = () => String(state.nextId++);

function page<T>(items: T[], url: URL): MockResponse {
  const limit = Math.min(Number(url.searchParams.get("limit") ?? "20") || 20, MOCK_PAGE_CAP);
  const offset = Number(url.searchParams.get("cursor") ?? "0") || 0;
  const slice = items.slice(offset, offset + limit);
  const next = offset + limit < items.length ? String(offset + limit) : null;
  return ok({ items: slice, next_cursor: next });
}

function base64url(value: unknown) {
  return btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function tokenFor(user: MockUser) {
  const access_token = [
    base64url({ alg: "none", typ: "JWT" }),
    base64url({ sub: user.id, roles: user.roles, iss: "pulsegrid-mock", exp: Math.floor(Date.now() / 1000) + 3600 }),
    "mock-signature",
  ].join(".");
  return { access_token, token_type: "Bearer", expires_in: 3600 };
}

function userFromToken(header: string | undefined): MockUser | null {
  const token = header?.startsWith("Bearer ") ? header.slice(7) : "";
  try {
    const encoded = (token.split(".")[1] ?? "").replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "="))) as { sub?: string };
    return users.find((user) => user.id === claims.sub) ?? null;
  } catch {
    return null;
  }
}

function sessionUser(cookie: string | undefined): MockUser | null {
  const match = cookie?.match(new RegExp(`${SESSION_COOKIE}=(\\d+)`));
  return users.find((user) => user.id === match?.[1]) ?? null;
}

function versionMatches(request: MockRequest, version: number): MockResponse | null {
  const ifMatch = request.headers["if-match"];
  if (!ifMatch) return error(428, "precondition_required", "This change requires the current version (If-Match).");
  if (ifMatch !== `"${version}"`) {
    return error(412, "precondition_failed", "This resource changed since you loaded it.");
  }
  return null;
}

function fulfillmentFor(prescription: Prescription): Fulfillment {
  const reservations = state.reservations.filter((item) => item.prescription_id === prescription.id);
  const dispensings = state.dispensings.filter((item) => item.prescription_id === prescription.id);
  const items = prescription.items.map((item) => {
    const reserved = reservations
      .filter((reservation) => reservation.state === "reserved")
      .flatMap((reservation) => reservation.items)
      .filter((line) => line.prescription_item_id === item.id)
      .reduce((sum, line) => sum + line.quantity, 0);
    const dispensed = dispensings
      .flatMap((dispensing) => dispensing.items)
      .filter((line) => line.prescription_item_id === item.id)
      .reduce((sum, line) => sum + line.quantity, 0);
    return {
      prescription_item_id: item.id,
      medicine_id: item.medicine_id,
      prescribed_quantity: item.quantity,
      reserved_quantity: reserved,
      dispensed_quantity: dispensed,
      remaining_quantity: item.quantity - dispensed,
    };
  });
  return {
    prescription_id: prescription.id,
    appointment_id: "5101",
    patient_id: prescription.patient_id,
    prescription_revision: prescription.revision,
    prescription_state: prescription.state,
    items,
    reservations: reservations.map(({ id, state: reservationState, version }) => ({ id, state: reservationState, version })),
    dispensings: dispensings.map((item) => ({ id: item.id, version: item.version, source_item_ids: item.items.map((line) => line.id) })),
    review_required: false,
    version: state.fulfillmentVersions.get(prescription.id) ?? 1,
    observed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}

function bumpFulfillment(prescriptionId: string) {
  state.fulfillmentVersions.set(prescriptionId, (state.fulfillmentVersions.get(prescriptionId) ?? 1) + 1);
}

function adjustReserved(medicineId: string, delta: number, dispensed = false) {
  const batch = state.batches.find((item) => item.medicine_id === medicineId && (delta < 0 ? item.reserved >= -delta : item.available >= delta));
  if (!batch) return;
  batch.reserved += delta;
  if (dispensed) batch.on_hand += delta;
  batch.available = batch.on_hand - batch.reserved;
  batch.version += 1;
}

function ownsPrescription(user: MockUser, prescription: Prescription) {
  return user.roles.includes("pharmacist") || user.roles.includes("doctor") || (user.roles.includes("patient") && prescription.patient_id === state.patient.id);
}

type Route = [method: string, pattern: RegExp, handler: (request: MockRequest, user: MockUser, match: RegExpMatchArray) => MockResponse];

const isPharmacist = (user: MockUser) => user.roles.includes("pharmacist");
const isDoctor = (user: MockUser) => user.roles.includes("doctor");
const isBilling = (user: MockUser) => user.roles.includes("billing_staff");
const isEmergencyStaff = (user: MockUser) => user.roles.includes("emergency_staff");
const isPatient = (user: MockUser) => user.roles.includes("patient");
const stamp = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const DOCTOR_ID = "8001";
const isReceptionist = (user: MockUser) => user.roles.includes("receptionist");
const isOperations = (user: MockUser) => user.roles.includes("ops") || user.roles.includes("hospital_admin");
const SLOT_TIMES = ["0900", "0930", "1000", "1030", "1100", "1130", "1400", "1430", "1500", "1530", "1600", "1630"];
const OPS_ROOT = "/api/v1/appointments/operations";

function slotFromId(id: string): Slot | null {
  const match = /^([1-8])(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$/.exec(id);
  if (!match) return null;
  const [, doctorDigit, year, month, date, hour, minute] = match;
  const index = SLOT_TIMES.indexOf(`${hour}${minute}`);
  if (index < 0) return null;
  const start = Date.UTC(Number(year), Number(month) - 1, Number(date), Number(hour), Number(minute));
  const retired = (Number(doctorDigit) * 7 + Number(date) * 3 + index) % 9 === 0;
  return {
    id, doctor_id: `800${doctorDigit}`, state: retired ? "retired" : "bookable", revision: 1,
    starts_at: new Date(start).toISOString().replace(/\.\d{3}Z$/, "Z"),
    ends_at: new Date(start + 30 * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}
function slotTaken(id: string, except?: string) {
  return state.appointments.some((item) => item.slot_id === id && item.state === "confirmed" && item.id !== except);
}
function slotsFor(doctorId: string, from: number, to: number): Slot[] {
  const slots: Slot[] = [];
  const first = new Date(from);
  for (let dayStart = Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), first.getUTCDate()); dayStart < to; dayStart += 86_400_000) {
    const stamp = new Date(dayStart).toISOString().slice(0, 10).replaceAll("-", "");
    for (const hhmm of SLOT_TIMES) {
      const slot = slotFromId(`${doctorId.slice(-1)}${stamp}${hhmm}`);
      const start = slot ? Date.parse(slot.starts_at) : 0;
      if (!slot || start < from || start >= to || start < Date.now() || slotTaken(slot.id)) continue;
      slots.push(slot);
    }
  }
  return slots;
}
function bookableSlot(slotId: string, revision: unknown, except?: string): Slot | MockResponse {
  const slot = slotFromId(slotId);
  if (!slot || !state.doctors.some((item) => item.id === slot.doctor_id)) return error(404, "not_found", "Slot not found.");
  if (revision !== slot.revision) return error(409, "schedule_revision_changed", "The doctor's accepted schedule changed. Reload availability.");
  if (slot.state !== "bookable" || Date.parse(slot.starts_at) < Date.now()) return error(409, "slot_unavailable", "This time is no longer available.");
  if (slotTaken(slot.id, except)) return error(409, "slot_taken", "Another booking took this time.");
  return slot;
}
function userView(item: MockUser) {
  const name = item.email.split("@")[0];
  return { id: item.id, email: item.email, display_name: `Mock ${name[0].toUpperCase()}${name.slice(1)}`, roles: item.roles, state: "active" as const, auth_version: 1, version: 1 };
}
function journey() {
  const source = (owner: "records" | "pharmacy" | "billing", resource_type: string, resource_id: string) => ({ owner, resource_type, resource_id, version: 1, observed_at: stamp() });
  const stage = (name: string, stageState: string, sources: ReturnType<typeof source>[], pending_reason: string | null = null) => ({ name, state: stageState, sources, observed_at: stamp(), pending_reason });
  return {
    id: "9401", appointment_id: "5101", patient_id: state.patient.id, state: "active",
    stages: [
      stage("appointment", "complete", []),
      stage("check_in", "complete", []),
      stage("consultation", "complete", [source("records", "consultation", "5501")]),
      stage("prescription", "complete", [source("records", "prescription", "6001")]),
      stage("pharmacy", "pending", [source("pharmacy", "reservation", "7001")], "unfilled"),
      stage("billing", "pending", [source("billing", "invoice", "9701")], "unpaid"),
    ],
    discharge_eligible: false, review_required: false, last_reconciled_at: state.minutes(-6), version: state.journeyVersion,
  };
}
function visibleAppointment(user: MockUser, id: string): Appointment | null {
  const item = state.appointments.find((appointment) => appointment.id === id);
  if (!item) return null;
  if (isReceptionist(user) || (isPatient(user) && item.patient_id === state.patient.id) || (isDoctor(user) && item.doctor_id === DOCTOR_ID)) return item;
  return null;
}

function emergencyView(item: Emergency, user: MockUser): Emergency {
  if (isEmergencyStaff(user)) return item;
  const { id, state: emergencyState, reported_urgency, assigned_priority, created_at, updated_at, version } = item;
  return { id, state: emergencyState, reported_urgency, assigned_priority, created_at, updated_at, version };
}
function visibleEmergency(user: MockUser, id: string) {
  const item = state.emergencies.find((candidate) => candidate.id === id);
  if (!item || (!isEmergencyStaff(user) && !(isPatient(user) && item.patient_id === state.patient.id))) return null;
  return item;
}
function emergencyChange(item: Emergency, apply: () => MockResponse | void, user: MockUser): MockResponse {
  const failed = apply();
  if (failed) return failed;
  item.version += 1;
  item.updated_at = stamp();
  return ok(emergencyView(item, user), item.version);
}
function reasonOf(body: unknown) {
  const reason = (body as { reason?: string } | undefined)?.reason;
  return typeof reason === "string" && reason.trim() ? reason : null;
}
function totals(invoice: Invoice) {
  invoice.total_minor = invoice.items.reduce((sum, line) => sum + line.quantity * line.unit_amount_minor, 0);
  invoice.balance_minor = invoice.total_minor - invoice.paid_minor;
  invoice.status = invoice.total_minor > 0 && invoice.balance_minor <= 0 ? "paid" : "open";
}
function currentTariff(code: string): Tariff | undefined {
  return state.tariffs.filter((item) => item.charge_code === code).sort((a, b) => b.revision - a.revision)[0];
}
function visibleInvoice(user: MockUser, id: string) {
  const item = state.invoices.find((invoice) => invoice.id === id);
  if (!item || (!isBilling(user) && !(isPatient(user) && item.patient_id === state.patient.id))) return null;
  return item;
}
function recordSummary(item: MedicalRecord & { created_at: string }) {
  const { id, consultation_id, patient_id, revision, created_at, version } = item;
  return { id, consultation_id, patient_id, revision, created_at, version };
}
function visibleConsultation(user: MockUser, id: string): Consultation | null {
  const item = state.consultations.find((consultation) => consultation.id === id);
  if (!item) return null;
  if (isDoctor(user) && item.doctor_id === DOCTOR_ID) return item;
  if (isPatient(user) && item.patient_id === state.patient.id) return item;
  return null;
}
const forbidden = () => error(403, "forbidden", "This account is not permitted to use this resource.");

const routes: Route[] = [
  ["GET", /^\/api\/v1\/patients\/me$/, (_request, user) =>
    user.roles.includes("patient") ? ok(state.patient, state.patient.version) : error(404, "not_found", "No patient profile for this account.")],

  ["GET", /^\/api\/v1\/pharmacy\/medicines\/autocomplete$/, (request) => {
    const prefix = (request.url.searchParams.get("prefix") ?? "").toLowerCase();
    const items = state.medicines
      .filter((item) => item.active && item.name.toLowerCase().split(/\s+/).some((word) => word.startsWith(prefix)))
      .slice(0, Number(request.url.searchParams.get("limit") ?? "10"))
      .map((item) => ({ id: item.id, kind: "medicine", label: item.name }));
    return ok({ items, index_version: 1, source: "trie" });
  }],
  ["GET", /^\/api\/v1\/pharmacy\/medicines$/, (request, user) => {
    const q = request.url.searchParams.get("q")?.toLowerCase();
    const active = request.url.searchParams.get("active");
    const items = state.medicines.filter((item) =>
      (isPharmacist(user) || item.active) &&
      (!q || item.name.toLowerCase().includes(q) || item.sku.toLowerCase().includes(q)) &&
      (!active || String(item.active) === active));
    return page(items, request.url);
  }],
  ["POST", /^\/api\/v1\/pharmacy\/medicines$/, (request, user) => {
    if (!isPharmacist(user)) return forbidden();
    const body = request.body as { sku?: string; name?: string };
    if (!body.sku || !body.name) return error(422, "validation_failed", "SKU and name are required.");
    if (state.medicines.some((item) => item.sku === body.sku)) return error(409, "duplicate_sku", "A medicine with this SKU already exists.");
    const created: Medicine = { id: nextId(), sku: body.sku, name: body.name, active: true, availability: "unknown", catalog_version: 1, version: 1 };
    state.medicines.push(created);
    return ok(created, created.version, 201);
  }],
  ["GET", /^\/api\/v1\/pharmacy\/medicines\/(\d+)$/, (_request, _user, match) => {
    const item = state.medicines.find((medicine) => medicine.id === match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Medicine not found.");
  }],
  ["PATCH", /^\/api\/v1\/pharmacy\/medicines\/(\d+)$/, (request, user, match) => {
    if (!isPharmacist(user)) return forbidden();
    const item = state.medicines.find((medicine) => medicine.id === match[1]);
    if (!item) return error(404, "not_found", "Medicine not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    const body = request.body as { name?: string; active?: boolean };
    if (typeof body.name === "string") item.name = body.name;
    if (typeof body.active === "boolean") item.active = body.active;
    item.version += 1;
    item.catalog_version += 1;
    return ok(item, item.version);
  }],

  ["GET", /^\/api\/v1\/pharmacy\/inventory$/, (request, user) => {
    if (!isPharmacist(user)) return forbidden();
    const medicineId = request.url.searchParams.get("medicine_id");
    return page(state.batches.filter((item) => !medicineId || item.medicine_id === medicineId), request.url);
  }],
  ["POST", /^\/api\/v1\/pharmacy\/inventory-adjustments$/, (request, user) => {
    if (!isPharmacist(user)) return forbidden();
    const body = request.body as { medicine_id: string; batch_code: string; expires_on: string; delta: number; expected_batch_version: number };
    if (!state.medicines.some((item) => item.id === body.medicine_id)) return error(404, "not_found", "Medicine not found.");
    let batch = state.batches.find((item) => item.medicine_id === body.medicine_id && item.batch_code === body.batch_code);
    if ((batch?.version ?? 0) !== body.expected_batch_version) return error(412, "precondition_failed", "The batch version changed since you loaded it.");
    if (!batch) {
      batch = { id: nextId(), medicine_id: body.medicine_id, batch_code: body.batch_code, expires_on: body.expires_on, on_hand: 0, reserved: 0, available: 0, version: 0 } satisfies Batch;
      state.batches.push(batch);
    }
    if (batch.on_hand + body.delta < batch.reserved) return error(409, "insufficient_stock", "The adjustment would leave less stock than is reserved.");
    batch.on_hand += body.delta;
    batch.available = batch.on_hand - batch.reserved;
    batch.version += 1;
    return ok({ movement_id: nextId(), batch }, undefined, 201);
  }],

  ["GET", /^\/api\/v1\/pharmacy\/reservations$/, (request, user) => {
    const patientId = request.url.searchParams.get("patient_id");
    const prescriptionId = request.url.searchParams.get("prescription_id");
    if (!isPharmacist(user) && patientId !== state.patient.id) return forbidden();
    return page(state.reservations.filter((item) =>
      (!patientId || item.patient_id === patientId) && (!prescriptionId || item.prescription_id === prescriptionId)), request.url);
  }],
  ["POST", /^\/api\/v1\/pharmacy\/reservations$/, (request, user) => {
    const body = request.body as { prescription_id?: string; items?: { prescription_item_id: string; quantity: number }[] };
    const prescription = state.prescriptions.find((item) => item.id === body.prescription_id);
    if (!prescription || !ownsPrescription(user, prescription)) return error(404, "not_found", "Prescription not found.");
    if (prescription.state !== "issued") return error(409, "prescription_revoked", "This prescription is revoked.");
    const fulfillment = fulfillmentFor(prescription);
    const lines: Reservation["items"] = [];
    for (const line of body.items ?? []) {
      const item = fulfillment.items.find((candidate) => candidate.prescription_item_id === line.prescription_item_id);
      if (!item) return error(422, "validation_failed", "Unknown prescription item.");
      if (line.quantity > item.prescribed_quantity - item.dispensed_quantity - item.reserved_quantity) {
        return error(409, "allowance_exceeded", "The requested quantity exceeds the remaining prescription allowance.");
      }
      lines.push({ prescription_item_id: item.prescription_item_id, medicine_id: item.medicine_id, quantity: line.quantity });
    }
    if (!lines.length) return error(422, "validation_failed", "Request at least one item.");
    const reservation: Reservation = {
      id: nextId(), patient_id: prescription.patient_id, prescription_id: prescription.id, state: "reserved",
      items: lines, expires_at: state.minutes(30), version: 1,
    };
    state.reservations.unshift(reservation);
    lines.forEach((line) => adjustReserved(line.medicine_id, line.quantity));
    bumpFulfillment(prescription.id);
    return ok(reservation, reservation.version, 201);
  }],
  ["GET", /^\/api\/v1\/pharmacy\/reservations\/(\d+)$/, (_request, user, match) => {
    const item = state.reservations.find((reservation) => reservation.id === match[1]);
    if (!item || (!isPharmacist(user) && item.patient_id !== state.patient.id)) return error(404, "not_found", "Reservation not found.");
    return ok(item, item.version);
  }],
  ["DELETE", /^\/api\/v1\/pharmacy\/reservations\/(\d+)$/, (request, user, match) => {
    const item = state.reservations.find((reservation) => reservation.id === match[1]);
    if (!item || (!isPharmacist(user) && item.patient_id !== state.patient.id)) return error(404, "not_found", "Reservation not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.state !== "reserved") return error(409, "invalid_state", `A ${item.state} reservation cannot be released.`);
    item.state = "released";
    item.version += 1;
    item.items.forEach((line) => adjustReserved(line.medicine_id, -line.quantity));
    bumpFulfillment(item.prescription_id);
    return { status: 204 };
  }],
  ["POST", /^\/api\/v1\/pharmacy\/reservations\/(\d+)\/revalidate$/, (request, user, match) => {
    if (!isPharmacist(user)) return forbidden();
    const item = state.reservations.find((reservation) => reservation.id === match[1]);
    if (!item) return error(404, "not_found", "Reservation not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    item.version += 1;
    return ok(item, item.version);
  }],
  ["POST", /^\/api\/v1\/pharmacy\/reservations\/(\d+)\/dispense$/, (request, user, match) => {
    if (!isPharmacist(user)) return forbidden();
    const item = state.reservations.find((reservation) => reservation.id === match[1]);
    if (!item) return error(404, "not_found", "Reservation not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.state !== "reserved") return error(409, "invalid_state", `A ${item.state} reservation cannot be dispensed.`);
    item.state = "dispensed";
    item.version += 1;
    const dispensing: Dispensing = {
      id: nextId(), reservation_id: item.id, prescription_id: item.prescription_id, patient_id: item.patient_id, appointment_id: "5101",
      items: item.items.map((line) => ({ id: nextId(), ...line })),
      completed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), version: 1,
    };
    state.dispensings.unshift(dispensing);
    item.items.forEach((line) => adjustReserved(line.medicine_id, -line.quantity, true));
    bumpFulfillment(item.prescription_id);
    return ok(dispensing, dispensing.version, 201);
  }],
  ["GET", /^\/api\/v1\/pharmacy\/dispensings$/, (request, user) =>
    isPharmacist(user) ? page(state.dispensings, request.url) : forbidden()],
  ["GET", /^\/api\/v1\/pharmacy\/prescriptions\/(\d+)\/fulfillment$/, (_request, user, match) => {
    const prescription = state.prescriptions.find((item) => item.id === match[1]);
    if (!prescription || !ownsPrescription(user, prescription)) return error(404, "not_found", "Prescription not found.");
    const fulfillment = fulfillmentFor(prescription);
    return ok(fulfillment, fulfillment.version);
  }],

  ["GET", /^\/api\/v1\/records\/prescriptions$/, (request, user) => {
    const patientId = request.url.searchParams.get("patient_id");
    const consultationId = request.url.searchParams.get("consultation_id");
    if (!(isPatient(user) || isDoctor(user)) || (patientId && patientId !== state.patient.id)) return forbidden();
    const ownConsultations = state.consultations.filter((item) => item.doctor_id === DOCTOR_ID).map((item) => item.id);
    return page(state.prescriptions.filter((item) =>
      item.patient_id === state.patient.id &&
      (patientId || isPatient(user) || ownConsultations.includes(item.consultation_id)) &&
      (!consultationId || item.consultation_id === consultationId)), request.url);
  }],
  ["GET", /^\/api\/v1\/appointments\/journeys$/, (request, user) =>
    isPatient(user) || isReceptionist(user) ? page([journey()], request.url) : forbidden()],
  ["GET", /^\/api\/v1\/appointments\/journeys\/(\d+)$/, (_request, user, match) =>
    match[1] === "9401" && (isPatient(user) || isReceptionist(user)) ? ok(journey(), state.journeyVersion) : error(404, "not_found", "Journey not found.")],
  ["GET", /^\/api\/v1\/appointments\/journeys\/(\d+)\/history$/, (request) => page([], request.url)],
  ["POST", /^\/api\/v1\/appointments\/journeys\/(\d+)\/reconcile$/, (request, _user, match) => {
    if (match[1] !== "9401") return error(404, "not_found", "Journey not found.");
    const stale = versionMatches(request, state.journeyVersion);
    if (stale) return stale;
    state.journeyVersion += 1;
    return ok(journey(), state.journeyVersion);
  }],
  ["GET", /^\/api\/v1\/appointments\/waitlists$/, (request, user) =>
    isPatient(user) ? page(state.waitlists, request.url) : forbidden()],
  ["GET", /^\/api\/v1\/appointments\/waitlists\/(\d+)$/, (_request, _user, match) => {
    const item = state.waitlists.find((entry) => entry.id === match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Waitlist entry not found.");
  }],
  ["POST", /^\/api\/v1\/appointments\/waitlists\/(\d+)\/withdraw$/, (request, _user, match) => {
    const item = state.waitlists.find((entry) => entry.id === match[1]);
    if (!item) return error(404, "not_found", "Waitlist entry not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    item.state = "withdrawn";
    item.version += 1;
    return ok(item, item.version);
  }],
  ["GET", /^\/api\/v1\/appointments\/waitlist-slots\/(\d+)$/, (_request, _user, match) =>
    ok({ slot_id: match[1], waiting_count: 3, promotion_pending: false, accepted_revision: 1, observed_at: stamp() })],
  ["GET", /^\/api\/v1\/appointments\/waitlist-offers$/, (request) => page([], request.url)],
  ["GET", /^\/api\/v1\/appointments\/queues$/, (request, user) => {
    if (!(isDoctor(user) || isReceptionist(user))) return forbidden();
    const doctorId = request.url.searchParams.get("doctor_id") ?? DOCTOR_ID;
    return ok({ doctor_id: doctorId, local_date: request.url.searchParams.get("local_date") ?? state.day(0), items: doctorId === DOCTOR_ID ? state.queue : [], next_cursor: null, waiting_count: doctorId === DOCTOR_ID ? 3 : 0, in_consultation_count: doctorId === DOCTOR_ID ? 1 : 0, version: 4, observed_at: stamp() }, 4);
  }],
  ["GET", /^\/api\/v1\/doctors\/(\d+)\/schedules$/, (request, _user, match) =>
    page(state.proposals.filter((item) => item.doctor_id === match[1]), request.url)],
  ["GET", /^\/api\/v1\/doctors\/(\d+)\/schedules\/(\d+)$/, (_request, _user, match) => {
    const item = state.proposals.find((proposal) => proposal.id === match[2] && proposal.doctor_id === match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Schedule proposal not found.");
  }],
  ["GET", /^\/api\/v1\/patients\/users$/, (request, user) => {
    if (!user.roles.includes("hospital_admin")) return forbidden();
    const q = request.url.searchParams.get("q")?.toLowerCase() ?? "";
    return page(users.filter((item) => item.email.includes(q)).map(userView), request.url);
  }],
  ["GET", /^\/api\/v1\/patients\/users\/(\d+)$/, (_request, user, match) => {
    const item = users.find((candidate) => candidate.id === match[1]);
    if (!user.roles.includes("hospital_admin") || !item) return error(404, "not_found", "User not found.");
    return ok(userView(item), 1);
  }],
  ["GET", /^\/api\/v1\/records\/prescriptions\/(\d+)$/, (_request, user, match) => {
    const item = state.prescriptions.find((prescription) => prescription.id === match[1]);
    if (!item || !ownsPrescription(user, item)) return error(404, "not_found", "Prescription not found.");
    return ok(item, item.version);
  }],

  ["GET", /^\/api\/v1\/emergencies$/, (request, user) => {
    const newest = [...state.emergencies].sort((a, b) => b.created_at.localeCompare(a.created_at));
    if (isEmergencyStaff(user)) return page(newest, request.url);
    if (isPatient(user)) return page(newest.filter((item) => item.patient_id === state.patient.id).map((item) => emergencyView(item, user)), request.url);
    return forbidden();
  }],
  ["POST", /^\/api\/v1\/emergencies$/, (request, user) => {
    const body = request.body as { patient_id?: string; description?: string; reported_urgency?: Emergency["reported_urgency"]; synthetic_contact?: string };
    if (!isPatient(user) || body.patient_id !== state.patient.id) return forbidden();
    if (!body.description?.trim()) return error(422, "validation_failed", "A description is required.");
    const created: Emergency = {
      id: nextId(), state: "submitted", reported_urgency: body.reported_urgency ?? "unspecified", assigned_priority: null,
      created_at: stamp(), updated_at: stamp(), patient_id: state.patient.id, description: body.description,
      synthetic_contact: body.synthetic_contact ?? null, claimed_by_user_id: null, claim_expires_at: null, version: 1,
    };
    state.emergencies.unshift(created);
    return ok(emergencyView(created, user), created.version, 201);
  }],
  ["GET", /^\/api\/v1\/emergencies\/(\d+)$/, (_request, user, match) => {
    const item = visibleEmergency(user, match[1]);
    return item ? ok(emergencyView(item, user), item.version) : error(404, "not_found", "Emergency request not found.");
  }],
  ["PATCH", /^\/api\/v1\/emergencies\/(\d+)\/priority$/, (request, user, match) => {
    if (!isEmergencyStaff(user)) return forbidden();
    const item = visibleEmergency(user, match[1]);
    if (!item) return error(404, "not_found", "Emergency request not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    const body = request.body as { assigned_priority?: number };
    return emergencyChange(item, () => {
      if (["resolved", "cancelled"].includes(item.state)) return error(409, "invalid_state", "This request is closed.");
      if (!Number.isInteger(body.assigned_priority) || body.assigned_priority! < 1 || body.assigned_priority! > 5) return error(422, "validation_failed", "Priority must be 1 to 5.");
      if (!reasonOf(request.body)) return error(422, "validation_failed", "A reason is required.");
      item.assigned_priority = body.assigned_priority!;
      if (item.state === "submitted") item.state = "triaged";
    }, user);
  }],
  ["POST", /^\/api\/v1\/emergencies\/(\d+)\/claim$/, (request, user, match) => {
    if (!isEmergencyStaff(user)) return forbidden();
    const item = visibleEmergency(user, match[1]);
    if (!item) return error(404, "not_found", "Emergency request not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    return emergencyChange(item, () => {
      if (item.state !== "triaged") return error(409, "invalid_state", "Only triaged requests can be claimed.");
      item.state = "claimed";
      item.claimed_by_user_id = user.id;
      item.claim_expires_at = state.minutes(15);
    }, user);
  }],
  ["POST", /^\/api\/v1\/emergencies\/(\d+)\/release$/, (request, user, match) => {
    if (!isEmergencyStaff(user)) return forbidden();
    const item = visibleEmergency(user, match[1]);
    if (!item) return error(404, "not_found", "Emergency request not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    return emergencyChange(item, () => {
      if (item.state !== "claimed" || item.claimed_by_user_id !== user.id) return error(409, "invalid_state", "Only your active claim can be released.");
      if (!reasonOf(request.body)) return error(422, "validation_failed", "A reason is required.");
      item.state = "triaged";
      item.claimed_by_user_id = null;
      item.claim_expires_at = null;
    }, user);
  }],
  ["POST", /^\/api\/v1\/emergencies\/(\d+)\/transitions$/, (request, user, match) => {
    const item = visibleEmergency(user, match[1]);
    if (!item) return error(404, "not_found", "Emergency request not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    const target = (request.body as { state?: Emergency["state"] }).state;
    return emergencyChange(item, () => {
      if (!reasonOf(request.body)) return error(422, "validation_failed", "A reason is required.");
      const owner = item.claimed_by_user_id === user.id;
      const legal =
        (target === "processing" && isEmergencyStaff(user) && item.state === "claimed" && owner) ||
        (target === "resolved" && isEmergencyStaff(user) && item.state === "processing" && owner) ||
        (target === "cancelled" && (["submitted", "triaged"].includes(item.state) || (isEmergencyStaff(user) && item.state === "claimed")));
      if (!legal) return error(409, "invalid_transition", `A ${item.state} request cannot move to ${target}.`);
      item.state = target!;
      if (target !== "processing") { item.claimed_by_user_id = target === "resolved" ? item.claimed_by_user_id : null; item.claim_expires_at = null; }
    }, user);
  }],

  // Explicit synthetic empty state until a provider fixture is configured.
  ["GET", /^\/api\/v1\/billing\/insurance\/providers$/, (request, user) =>
    isBilling(user) ? page([], request.url) : forbidden()],
  ["GET", /^\/api\/v1\/billing\/tariffs$/, (request, user) =>
    isBilling(user) ? page([...state.tariffs].sort((a, b) => a.charge_code.localeCompare(b.charge_code) || b.revision - a.revision), request.url) : forbidden()],
  ["POST", /^\/api\/v1\/billing\/tariffs$/, (request, user) => {
    if (!isBilling(user)) return forbidden();
    const body = request.body as { charge_code?: string; unit_amount_minor?: number };
    if (!body.charge_code || !Number.isInteger(body.unit_amount_minor)) return error(422, "validation_failed", "Charge code and amount are required.");
    const created: Tariff = { id: nextId(), charge_code: body.charge_code, revision: (currentTariff(body.charge_code)?.revision ?? 0) + 1, unit_amount_minor: body.unit_amount_minor!, currency: "INR", version: 1 };
    state.tariffs.push(created);
    return ok(created, created.version, 201);
  }],
  ["GET", /^\/api\/v1\/billing\/invoices$/, (request, user) => {
    if (isBilling(user)) return page(state.invoices, request.url);
    if (isPatient(user)) return page(state.invoices.filter((item) => item.patient_id === state.patient.id), request.url);
    return forbidden();
  }],
  ["POST", /^\/api\/v1\/billing\/invoices$/, (request, user) => {
    if (!isBilling(user)) return forbidden();
    const appointmentId = (request.body as { appointment_id?: string }).appointment_id;
    if (!appointmentId) return error(422, "validation_failed", "An appointment ID is required.");
    if (state.invoices.some((item) => item.appointment_id === appointmentId)) return error(409, "invoice_exists", "This appointment already has an invoice.");
    const created: Invoice = { id: nextId(), journey_id: null, appointment_id: appointmentId, patient_id: state.patient.id, status: "open", items: [], total_minor: 0, paid_minor: 0, balance_minor: 0, currency: "INR", version: 1 };
    state.invoices.unshift(created);
    return ok(created, created.version, 201);
  }],
  ["GET", /^\/api\/v1\/billing\/invoices\/(\d+)$/, (_request, user, match) => {
    const item = visibleInvoice(user, match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Invoice not found.");
  }],
  ["GET", /^\/api\/v1\/billing\/invoices\/(\d+)\/insurance-estimates$/, (request, user, match) =>
    visibleInvoice(user, match[1]) ? page([], request.url) : error(404, "not_found", "Invoice not found.")],
  ["POST", /^\/api\/v1\/billing\/invoices\/(\d+)\/charges$/, (request, user, match) => {
    if (!isBilling(user)) return forbidden();
    const item = visibleInvoice(user, match[1]);
    if (!item) return error(404, "not_found", "Invoice not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    const body = request.body as { consultation_id?: string; dispensing_ids?: string[] };
    const additions: Invoice["items"] = [];
    if (body.consultation_id) {
      const consultation = state.consultations.find((candidate) => candidate.id === body.consultation_id);
      if (!consultation || consultation.status !== "finalized" || consultation.appointment_id !== item.appointment_id) return error(422, "invalid_source", "The consultation is not a finalized visit for this invoice's appointment.");
      if (item.items.some((line) => line.source_service === "records" && line.source_item_id === consultation.id)) return error(409, "already_imported", "This consultation is already on the invoice.");
      const tariff = currentTariff("consultation");
      if (!tariff) return error(409, "missing_tariff", "No consultation tariff exists.");
      additions.push({ id: nextId(), charge_code: "consultation", source_service: "records", source_item_id: consultation.id, quantity: 1, unit_amount_minor: tariff.unit_amount_minor, tariff_revision: tariff.revision });
    }
    for (const dispensingId of body.dispensing_ids ?? []) {
      const dispensing = state.dispensings.find((candidate) => candidate.id === dispensingId);
      if (!dispensing || dispensing.appointment_id !== item.appointment_id) return error(422, "invalid_source", `Dispensing ${dispensingId} is not a completed dispensing for this appointment.`);
      for (const dispensed of dispensing.items) {
        const tariff = currentTariff(`medicine:${dispensed.medicine_id}`);
        if (!tariff) return error(409, "missing_tariff", `No tariff exists for medicine ${dispensed.medicine_id}.`);
        additions.push({ id: nextId(), charge_code: tariff.charge_code, source_service: "pharmacy", source_item_id: dispensed.id, quantity: dispensed.quantity, unit_amount_minor: tariff.unit_amount_minor, tariff_revision: tariff.revision });
      }
    }
    if (!additions.length) return error(422, "validation_failed", "Select at least one source.");
    item.items.push(...additions);
    totals(item);
    item.version += 1;
    return ok(item, item.version, 201);
  }],
  ["GET", /^\/api\/v1\/billing\/invoices\/(\d+)\/payments$/, (request, user, match) =>
    visibleInvoice(user, match[1]) ? page(state.payments.filter((payment) => payment.invoice_id === match[1]), request.url) : error(404, "not_found", "Invoice not found.")],
  ["POST", /^\/api\/v1\/billing\/invoices\/(\d+)\/payments$/, (request, user, match) => {
    const item = visibleInvoice(user, match[1]);
    if (!item) return error(404, "not_found", "Invoice not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    const body = request.body as { amount_minor?: number; simulated_outcome?: "success" | "decline" };
    if (!Number.isInteger(body.amount_minor) || body.amount_minor! < 1 || body.amount_minor! > item.balance_minor) return error(422, "validation_failed", "The amount must be between 1 paisa and the balance.");
    const payment: Payment = { id: nextId(), invoice_id: item.id, amount_minor: body.amount_minor!, currency: "INR", status: body.simulated_outcome === "decline" ? "declined" : "success", version: 1 };
    state.payments.unshift(payment);
    if (payment.status === "success") {
      item.paid_minor += payment.amount_minor;
      totals(item);
    }
    item.version += 1;
    return ok(payment, payment.version, 201);
  }],

  ["GET", /^\/api\/v1\/records\/patients\/(\d+)$/, (request, user, match) => {
    if (match[1] !== state.patient.id || !(isPatient(user) || isDoctor(user))) return forbidden();
    return page([...state.records].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(recordSummary), request.url);
  }],
  ["GET", /^\/api\/v1\/records\/consultations$/, (request, user) => {
    if (isDoctor(user)) return page(state.consultations.filter((item) => item.doctor_id === DOCTOR_ID).reverse(), request.url);
    if (isPatient(user)) return page(state.consultations.filter((item) => item.patient_id === state.patient.id && item.status === "finalized"), request.url);
    return forbidden();
  }],
  ["POST", /^\/api\/v1\/records\/consultations$/, (request, user) => {
    if (!isDoctor(user)) return forbidden();
    const body = request.body as { appointment_id?: string; clinical_content?: Consultation["clinical_content"] };
    const appointment = state.appointments.find((item) => item.id === body.appointment_id && item.doctor_id === DOCTOR_ID);
    if (!appointment || !body.clinical_content) return error(422, "invalid_appointment", "Use an appointment assigned to you.");
    if (state.consultations.some((item) => item.appointment_id === appointment.id)) return error(409, "consultation_exists", "This appointment already has a consultation.");
    const created: Consultation = { id: nextId(), appointment_id: appointment.id, patient_id: appointment.patient_id, doctor_id: DOCTOR_ID, status: "draft", clinical_content: body.clinical_content, revision: 1, version: 1 };
    state.consultations.push(created);
    return ok(created, created.version, 201);
  }],
  ["GET", /^\/api\/v1\/records\/consultations\/(\d+)$/, (_request, user, match) => {
    const item = visibleConsultation(user, match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Consultation not found.");
  }],
  ["PATCH", /^\/api\/v1\/records\/consultations\/(\d+)$/, (request, user, match) => {
    const item = isDoctor(user) ? visibleConsultation(user, match[1]) : null;
    if (!item) return error(404, "not_found", "Consultation not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.status !== "draft") return error(409, "finalized", "Finalized consultations cannot be edited.");
    item.clinical_content = (request.body as { clinical_content: Consultation["clinical_content"] }).clinical_content;
    item.version += 1;
    return ok(item, item.version);
  }],
  ["POST", /^\/api\/v1\/records\/consultations\/(\d+)\/finalize$/, (request, user, match) => {
    const item = isDoctor(user) ? visibleConsultation(user, match[1]) : null;
    if (!item) return error(404, "not_found", "Consultation not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.status !== "draft") return error(409, "finalized", "This consultation is already finalized.");
    item.status = "finalized";
    item.version += 1;
    const created = { id: nextId(), consultation_id: item.id, patient_id: item.patient_id, content: { ...item.clinical_content }, revision: 1, supersedes_id: null, version: 1, created_at: stamp() };
    state.records.push(created);
    const lines = (request.body as { prescription_items?: Prescription["items"] }).prescription_items ?? [];
    const prescription: Prescription | null = lines.length ? { id: nextId(), consultation_id: item.id, patient_id: item.patient_id, journey_id: null, revision: 1, state: "issued", version: 1, items: lines.map((line) => ({ ...line, id: nextId() })) } : null;
    if (prescription) state.prescriptions.push(prescription);
    const { created_at: _created, ...record } = created;
    return ok({ consultation: item, record, prescription }, item.version);
  }],
  ["GET", /^\/api\/v1\/records\/(\d+)$/, (_request, user, match) => {
    const item = state.records.find((record) => record.id === match[1]);
    if (!item || !(isPatient(user) || isDoctor(user))) return error(404, "not_found", "Medical record not found.");
    const { created_at: _created, ...record } = item;
    return ok(record, item.version);
  }],
  ["POST", /^\/api\/v1\/records\/(\d+)\/amendments$/, (request, user, match) => {
    if (!isDoctor(user)) return forbidden();
    const item = state.records.find((record) => record.id === match[1]);
    if (!item) return error(404, "not_found", "Medical record not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (state.records.some((record) => record.supersedes_id === item.id)) return error(409, "superseded", "Amend the latest version of this record.");
    const body = request.body as { content?: MedicalRecord["content"]; reason?: string };
    if (!body.content || !reasonOf(body)) return error(422, "validation_failed", "Content and reason are required.");
    const created = { id: nextId(), consultation_id: item.consultation_id, patient_id: item.patient_id, content: body.content, revision: item.revision + 1, supersedes_id: item.id, version: 1, created_at: stamp() };
    state.records.push(created);
    const { created_at: _created, ...record } = created;
    return ok(record, record.version, 201);
  }],
  ["POST", /^\/api\/v1\/records\/access-grants$/, (request, user) => {
    if (!isPatient(user)) return forbidden();
    const body = request.body as Omit<Grant, "id" | "version">;
    const created: Grant = { ...body, id: nextId(), version: 1 };
    state.grants.push(created);
    return ok(created, created.version, 201);
  }],
  ["DELETE", /^\/api\/v1\/records\/access-grants\/(\d+)$/, (request, user, match) => {
    const item = state.grants.find((grant) => grant.id === match[1]);
    if (!item || !isPatient(user)) return error(404, "not_found", "Grant not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    state.grants.splice(state.grants.indexOf(item), 1);
    return { status: 204 };
  }],

  ["GET", /^\/api\/v1\/doctors\/specialties$/, (request) => page(state.specialties, request.url)],
  ["GET", /^\/api\/v1\/doctors$/, (request) => page(state.doctors, request.url)],
  ["GET", /^\/api\/v1\/doctors\/me$/, (_request, user) =>
    user.roles.includes("doctor") ? ok({ doctor: state.doctors[0], staff_user_id: user.id }, state.doctors[0].version) : error(404, "not_found", "No doctor profile for this account.")],
  ["GET", /^\/api\/v1\/doctors\/(\d+)$/, (_request, _user, match) => {
    const item = state.doctors.find((doctor) => doctor.id === match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Doctor not found.");
  }],
  ["GET", /^\/api\/v1\/appointments\/availability$/, (request) => {
    const doctorId = request.url.searchParams.get("doctor_id") ?? "8001";
    const from = Date.parse(request.url.searchParams.get("from") ?? "") || Date.now();
    const to = Date.parse(request.url.searchParams.get("to") ?? "") || from + 86_400_000;
    if (!state.doctors.some((item) => item.id === doctorId)) return error(404, "not_found", "Doctor not found.");
    if (to <= from || to - from > 31 * 86_400_000) return error(422, "validation_failed", "Use a range of at most 31 days.");
    return ok({ slots: slotsFor(doctorId, from, to), accepted_revision: 1, observed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z") });
  }],
  ["GET", /^\/api\/v1\/appointments$/, (request, user) => {
    const patientId = request.url.searchParams.get("patient_id");
    const items = state.appointments.filter((item) => visibleAppointment(user, item.id) && (!patientId || item.patient_id === patientId));
    return page(items, request.url);
  }],
  ["POST", /^\/api\/v1\/appointments$/, (request, user) => {
    const body = request.body as { patient_id?: string; slot_id?: string; expected_schedule_revision?: number };
    const patientIds = [state.patient.id, ...state.otherPatients.map((item) => item.id)];
    if (!(isReceptionist(user) || (isPatient(user) && body.patient_id === state.patient.id))) return forbidden();
    if (!body.patient_id || !patientIds.includes(body.patient_id)) return error(404, "not_found", "Patient not found.");
    const slot = bookableSlot(body.slot_id ?? "", body.expected_schedule_revision);
    if ("status" in slot) return slot;
    const created: Appointment = { id: nextId(), journey_id: null, patient_id: body.patient_id, doctor_id: slot.doctor_id, slot_id: slot.id, starts_at: slot.starts_at, ends_at: slot.ends_at, state: "confirmed", version: 1 };
    state.appointments.push(created);
    return ok(created, created.version, 201);
  }],
  ["GET", /^\/api\/v1\/appointments\/(\d+)$/, (_request, user, match) => {
    const item = visibleAppointment(user, match[1]);
    return item ? ok(item, item.version) : error(404, "not_found", "Appointment not found.");
  }],
  ["POST", /^\/api\/v1\/appointments\/(\d+)\/cancel$/, (request, user, match) => {
    const item = isDoctor(user) ? null : visibleAppointment(user, match[1]);
    if (!item) return error(404, "not_found", "Appointment not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.state !== "confirmed") return error(409, "invalid_state", "This appointment is already cancelled.");
    if (!reasonOf(request.body)) return error(422, "validation_failed", "A reason is required.");
    item.state = "cancelled";
    item.version += 1;
    return ok(item, item.version);
  }],
  ["POST", /^\/api\/v1\/appointments\/(\d+)\/reschedule$/, (request, user, match) => {
    const item = isDoctor(user) ? null : visibleAppointment(user, match[1]);
    if (!item) return error(404, "not_found", "Appointment not found.");
    const stale = versionMatches(request, item.version);
    if (stale) return stale;
    if (item.state !== "confirmed") return error(409, "invalid_state", "Only confirmed appointments can be rescheduled.");
    const body = request.body as { target_slot_id?: string; expected_schedule_revision?: number };
    const slot = bookableSlot(body.target_slot_id ?? "", body.expected_schedule_revision, item.id);
    if ("status" in slot) return slot;
    Object.assign(item, { doctor_id: slot.doctor_id, slot_id: slot.id, starts_at: slot.starts_at, ends_at: slot.ends_at, version: item.version + 1 });
    return ok(item, item.version);
  }],
  ["GET", /^\/api\/v1\/patients$/, (request, user) => {
    if (!(isReceptionist(user) || user.roles.includes("hospital_admin"))) return forbidden();
    const q = request.url.searchParams.get("q")?.toLowerCase() ?? "";
    return page([state.patient, ...state.otherPatients].filter((item) => item.display_name.toLowerCase().includes(q)), request.url);
  }],
  ["GET", new RegExp(`^${OPS_ROOT}/control-room/summary$`), (_request, user) =>
    isOperations(user) ? ok(controlRoomSummary(state.surge.state, state.surge.changed_at)) : forbidden()],
  ["GET", new RegExp(`^${OPS_ROOT}/control-room/traces$`), (_request, user) =>
    isOperations(user) ? ok(traceList()) : forbidden()],
  ["GET", new RegExp(`^${OPS_ROOT}/control-room/traces/([0-9a-f]{32})$`), (_request, user, match) => {
    if (!isOperations(user)) return forbidden();
    const spans = traceSpans(match[1]);
    return spans ? ok(spans) : error(404, "not_found", "Trace not found.");
  }],
  ["GET", new RegExp(`^${OPS_ROOT}/surge-mode$`), (_request, user) =>
    user.roles.includes("hospital_admin") ? ok(state.surge, state.surge.version) : forbidden()],
  ["POST", new RegExp(`^${OPS_ROOT}/surge-mode$`), (request, user) => {
    if (!user.roles.includes("hospital_admin")) return forbidden();
    const body = request.body as { active?: boolean; reason_code?: string; override?: boolean };
    if (typeof body.active !== "boolean" || !body.reason_code) return error(422, "validation_failed", "Operation and reason are required.");
    Object.assign(state.surge, {
      state: body.active ? "SURGE" : "RECOVERY",
      version: state.surge.version + 1,
      changed_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      expires_at: body.active ? null : state.minutes(10),
      reason_code: body.reason_code,
    });
    return ok(state.surge, state.surge.version);
  }],
  ["GET", /^\/api\/v1\/appointments\/(\d+)\/queue$/, (_request, _user, match) => {
    const stamp = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    if (match[1] === "5101") {
      const queue: OwnQueue = {
        entry: { id: "9301", appointment_id: "5101", doctor_id: "8001", local_date: state.day(0), token_number: 3, state: "waiting", position: 2, version: 1 },
        waiting_count: 4, in_consultation_count: 1, queue_version: 1, observed_at: stamp,
      };
      return ok(queue, 1);
    }
    const checked = state.checkinEntries.get(match[1]);
    const workflow = state.workflows.find((item) => item.appointment_id === match[1]);
    if (!checked || !workflow) return error(404, "not_found", "No queue entry for this appointment.");
    const queue: OwnQueue = {
      entry: { id: checked.id, appointment_id: match[1], doctor_id: workflow.doctor_id, local_date: state.day(0), token_number: checked.token_number, state: "waiting", position: 1, version: 1 },
      waiting_count: 1, in_consultation_count: 0, queue_version: 1, observed_at: stamp,
    };
    return ok(queue, 1);
  }],
  ["GET", /^\/api\/v1\/appointments\/(\d+)\/workflow$/, (_request, _user, match) => {
    const workflow = state.workflows.find((item) => item.appointment_id === match[1]);
    if (!workflow) return error(404, "not_found", "No workflow for this appointment.");
    return ok(workflow satisfies Workflow, workflow.version);
  }],
  ["POST", /^\/api\/v1\/appointments\/(\d+)\/check-in-links$/, (request, _user, match) => {
    const workflow = state.workflows.find((item) => item.appointment_id === match[1]);
    if (!workflow) return error(404, "not_found", "No workflow for this appointment.");
    const stale = versionMatches(request, workflow.version);
    if (stale) return stale;
    if (workflow.state !== "booked") return error(409, "invalid_state", "This appointment is not waiting for check-in.");
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    const token = Array.from({ length: 22 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join("");
    state.checkinLinks.set(match[1], token);
    workflow.version += 1;
    const issue: TokenIssue = {
      link_id: nextId(), appointment_id: match[1], expires_at: state.minutes(10), token,
      landing_path: `/patient/check-in#appointment_id=${match[1]}&token=${token}`, version: 1,
    };
    return ok(issue, 1, 201);
  }],
  ["POST", /^\/api\/v1\/appointments\/(\d+)\/check-in$/, (request, _user, match) => {
    const workflow = state.workflows.find((item) => item.appointment_id === match[1]);
    if (!workflow) return error(404, "not_found", "No workflow for this appointment.");
    const stale = versionMatches(request, workflow.version);
    if (stale) return stale;
    const token = (request.body as { token?: string } | undefined)?.token;
    if (!token || state.checkinLinks.get(match[1]) !== token) return error(422, "token_invalid", "The check-in token is invalid.");
    state.checkinLinks.delete(match[1]);
    const entry = { id: nextId(), token_number: 5 };
    state.checkinEntries.set(match[1], entry);
    workflow.state = "checked_in";
    workflow.queue_entry_id = entry.id;
    workflow.version += 1;
    const result: CheckinResult = {
      workflow,
      queue_entry: { id: entry.id, appointment_id: match[1], doctor_id: workflow.doctor_id, local_date: state.day(0), token_number: entry.token_number, state: "waiting", position: 1, version: 1 },
    };
    return ok(result, workflow.version);
  }],
];

export function handleMockRequest(request: MockRequest): MockResponse {
  const path = request.url.pathname;
  const method = request.method.toUpperCase();

  if (path === "/api/v1/auth/csrf") return ok({ csrf_token: "mock-csrf-token", header_name: "X-CSRF-Token", expires_in: 3600 });
  if (path === "/api/v1/auth/login" && method === "POST") {
    const email = String((request.body as { email?: string })?.email ?? "").trim().toLowerCase();
    const user = users.find((candidate) => candidate.email === email);
    if (!user) return error(401, "invalid_credentials", "Use patient@, pharmacist@, doctor@ or admin@mock.test with any password.");
    return { ...ok(tokenFor(user)), headers: { "Set-Cookie": `${SESSION_COOKIE}=${user.id}; HttpOnly; Path=/; SameSite=Strict` } };
  }
  if (path === "/api/v1/auth/refresh" && method === "POST") {
    const user = sessionUser(request.headers.cookie);
    return user ? ok(tokenFor(user)) : error(401, "session_expired", "Sign in to continue.");
  }
  if (path === "/api/v1/auth/logout" && method === "POST") {
    return { status: 204, headers: { "Set-Cookie": `${SESSION_COOKIE}=; HttpOnly; Path=/; Max-Age=0; SameSite=Strict` } };
  }
  if (path === "/api/v1/auth/register" && method === "POST") {
    return error(409, "mock_registration_disabled", "Mock mode uses the fixed mock.test accounts.");
  }

  const user = userFromToken(request.headers.authorization);
  if (!user) return error(401, "unauthenticated", "Sign in to continue.");

  for (const [routeMethod, pattern, handler] of routes) {
    const match = path.match(pattern);
    if (match && routeMethod === method) {
      const key = method === "POST" ? request.headers["idempotency-key"] : undefined;
      if (!key) return handler(request, user, match);
      const fingerprint = `${user.id}:${path}:${JSON.stringify(request.body)}`;
      const previous = idempotency.get(key);
      if (previous) {
        return previous.fingerprint === fingerprint
          ? previous.response
          : error(422, "idempotency_key_reused", "This idempotency key was already used for a different command.");
      }
      const response = handler(request, user, match);
      if (response.status < 500) idempotency.set(key, { fingerprint, response: structuredClone(response) });
      return response;
    }
  }
  return error(404, "not_found", `No mock fixture for ${method} ${path}.`);
}
