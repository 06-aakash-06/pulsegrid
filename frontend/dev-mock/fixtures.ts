import type {
  Batch,
  Dispensing,
  Doctor,
  Medicine,
  Prescription,
  Reservation,
  Specialty,
  Appointment,
  Consultation,
  Emergency,
  Grant,
  Invoice,
  MedicalRecord,
  Payment,
  Tariff,
} from "../src/hospital/models";
import type { PatientProfile } from "../src/api/authApi";
import type { Role } from "../src/auth/authContext";
import type { Workflow } from "../src/advanced/patient/contracts";
type WorkflowState = Workflow["state"];

// Synthetic fixtures for `npm run dev:mock`. Nothing here is real or clinical advice.

export interface MockUser {
  id: string;
  email: string;
  roles: Role[];
}

export const users: MockUser[] = [
  { id: "1001", email: "patient@mock.test", roles: ["patient"] },
  { id: "1002", email: "pharmacist@mock.test", roles: ["pharmacist"] },
  { id: "1003", email: "doctor@mock.test", roles: ["doctor"] },
  { id: "1004", email: "admin@mock.test", roles: ["hospital_admin"] },
  { id: "1005", email: "billing@mock.test", roles: ["billing_staff"] },
  { id: "1006", email: "emergency@mock.test", roles: ["emergency_staff"] },
  { id: "1007", email: "receptionist@mock.test", roles: ["receptionist"] },
  { id: "1008", email: "ops@mock.test", roles: ["ops"] },
];

const now = Date.now();
const minutes = (value: number) => new Date(now + value * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z");
const day = (offset: number) => new Date(now + offset * 86_400_000).toISOString().slice(0, 10);

export function createState() {
  const patient: PatientProfile = {
    id: "2001",
    user_id: "1001",
    display_name: "Asha Rao",
    date_of_birth: "1990-04-12",
    synthetic_contact: "asha.rao@example.test",
    version: 1,
  };

  const medicine = (
    id: string,
    sku: string,
    name: string,
    availability: Medicine["availability"],
    active = true,
  ): Medicine => ({ id, sku, name, active, availability, catalog_version: 1, version: 1 });

  const medicines: Medicine[] = [
    medicine("3001", "MOCK-PCM-500", "Paracetamol 500 mg tablets", "available"),
    medicine("3002", "MOCK-AMX-250", "Amoxicillin 250 mg capsules", "available"),
    medicine("3003", "MOCK-CTZ-10", "Cetirizine 10 mg", "unavailable"),
    medicine("3004", "MOCK-OMP-20", "Omeprazole 20 mg gastro-resistant capsules", "available"),
    medicine("3005", "MOCK-MET-500", "Metformin 500 mg", "unknown"),
    medicine("3006", "MOCK-ORS", "ORS", "available"),
    medicine("3007", "MOCK-IBU-400", "Ibuprofen 400 mg tablets", "unavailable"),
    medicine("3008", "MOCK-SAL-100", "Salbutamol 100 mcg inhaler", "available"),
    medicine("3009", "MOCK-VD3-1000", "Vitamin D3 1000 IU softgels", "unknown"),
    medicine("3010", "MOCK-AZI-500", "Azithromycin 500 mg", "available"),
    medicine("3011", "MOCK-LEV-50", "Levothyroxine 50 mcg", "available"),
    medicine("3012", "MOCK-CHX-02", "Chlorhexidine 0.2% mouthwash", "unknown"),
    medicine("3013", "MOCK-LOR-10", "Loratadine", "unavailable"),
    medicine("3014", "MOCK-PAN-40", "Pantoprazole 40 mg enteric-coated tablets", "available"),
  ];

  const batch = (
    id: string,
    medicine_id: string,
    batch_code: string,
    expires_on: string,
    on_hand: number,
    reserved: number,
  ): Batch => ({ id, medicine_id, batch_code, expires_on, on_hand, reserved, available: on_hand - reserved, version: 1 });

  const batches: Batch[] = [
    batch("4001", "3001", "PCM-2611-A", "2027-03-31", 120, 4),
    batch("4002", "3001", "PCM-2702-B", "2027-08-31", 60, 0),
    batch("4003", "3002", "AMX-2610-A", "2027-01-31", 45, 0),
    batch("4004", "3002", "AMX-2612-B", "2027-05-31", 30, 0),
    batch("4005", "3002", "AMX-2703-C", "2027-11-30", 15, 0),
    batch("4006", "3008", "SAL-2609-A", "2027-09-30", 8, 0),
    batch("4007", "3008", "SAL-2704-B", "2028-02-29", 12, 0),
    batch("4008", "3014", "PAN-2611-A", "2027-06-30", 90, 0),
    batch("4009", "3014", "PAN-2705-B", "2028-01-31", 40, 0),
  ];

  const prescriptions: Prescription[] = [
    {
      id: "6001", consultation_id: "5501", patient_id: patient.id, journey_id: null, revision: 1, state: "issued", version: 1,
      items: [
        { id: "6101", medicine_id: "3001", quantity: 10, dosage: "1 tablet every 6 hours when needed", instructions: "Do not take more than 4 tablets in 24 hours. Take with water." },
        { id: "6102", medicine_id: "3002", quantity: 15, dosage: "1 capsule three times a day", instructions: "Complete the full 5-day course even if you feel better." },
        { id: "6103", medicine_id: "3004", quantity: 7, dosage: "1 capsule once a day", instructions: "Take 30 minutes before breakfast." },
      ],
    },
    {
      id: "6002", consultation_id: "5502", patient_id: patient.id, journey_id: null, revision: 1, state: "issued", version: 1,
      items: [
        { id: "6104", medicine_id: "3008", quantity: 1, dosage: "2 puffs when needed", instructions: "Shake well before use. Contact the clinic if you need it more than 3 times a week." },
      ],
    },
    {
      id: "6003", consultation_id: "5503", patient_id: patient.id, journey_id: null, revision: 2, state: "revoked", version: 2,
      items: [
        { id: "6105", medicine_id: "3007", quantity: 10, dosage: "1 tablet twice a day after food", instructions: "Take after food. Stop if stomach pain occurs." },
      ],
    },
  ];

  const reservations: Reservation[] = [
    {
      id: "7001", patient_id: patient.id, prescription_id: "6001", state: "reserved",
      items: [{ prescription_item_id: "6101", medicine_id: "3001", quantity: 4 }],
      expires_at: minutes(25), version: 1,
    },
  ];

  const dispensings: Dispensing[] = [];

  const specialties: Specialty[] = [
    { id: "8101", slug: "general-medicine", name: "General Medicine", version: 1 },
    { id: "8102", slug: "pulmonology", name: "Pulmonology", version: 1 },
    { id: "8103", slug: "dermatology", name: "Dermatology", version: 1 },
    { id: "8104", slug: "cardiology", name: "Cardiology", version: 1 },
    { id: "8105", slug: "pediatrics", name: "Pediatrics", version: 1 },
  ];
  const doctor = (id: string, display_name: string, specialty: string): Doctor => {
    const found = specialties.find((item) => item.id === specialty)!;
    return { id, display_name, specialties: [{ id: found.id, name: found.name }], active: true, version: 1 };
  };
  const doctors: Doctor[] = [
    doctor("8001", "Dr. Meera Iyer", "8101"),
    doctor("8002", "Dr. Kabir Sethi", "8102"),
    doctor("8003", "Dr. Nisha Pillai", "8103"),
    doctor("8004", "Dr. Arjun Menon", "8104"),
    doctor("8005", "Dr. Farah Qureshi", "8105"),
    doctor("8006", "Dr. Vikram Rao", "8101"),
    doctor("8007", "Dr. Leela Thomas", "8104"),
    doctor("8008", "Dr. Sanjay Gupta", "8102"),
  ];
  const otherPatients: PatientProfile[] = [
    { id: "2002", user_id: "1102", display_name: "Rohan Mehta", date_of_birth: "1985-11-02", synthetic_contact: "rohan.mehta@example.test", version: 1 },
    { id: "2003", user_id: "1103", display_name: "Divya Nair", date_of_birth: "2001-06-21", version: 1 },
  ];
  const slotAt = (doctorId: string, daysFromToday: number, hhmm: string) => {
    const date = new Date(`${day(daysFromToday)}T${hhmm.slice(0, 2)}:${hhmm.slice(2)}:00Z`);
    const starts_at = date.toISOString().replace(/\.\d{3}Z$/, "Z");
    const ends_at = new Date(date.getTime() + 30 * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z");
    return { slot_id: `${doctorId.slice(-1)}${starts_at.slice(0, 10).replaceAll("-", "")}${hhmm}`, starts_at, ends_at };
  };
  const booked = (id: string, doctorId: string, daysFromToday: number, hhmm: string, state: Appointment["state"] = "confirmed"): Appointment => ({
    id, journey_id: null, patient_id: "2001", doctor_id: doctorId, ...slotAt(doctorId, daysFromToday, hhmm), state, version: 1,
  });

  const appointments: Appointment[] = [
    {
      id: "5101", journey_id: null, patient_id: patient.id, doctor_id: "8001", slot_id: "9101",
      starts_at: minutes(40), ends_at: minutes(55), state: "confirmed", version: 1,
    },
    booked("5107", "8004", 2, "1000"),
    booked("5108", "8005", 5, "1430"),
    booked("5109", "8002", -12, "0930"),
    booked("5110", "8003", -40, "1100"),
    booked("5111", "8006", 3, "1500", "cancelled"),
    {
      id: "5112", journey_id: null, patient_id: patient.id, doctor_id: "8002", slot_id: "9112",
      starts_at: minutes(25), ends_at: minutes(40), state: "confirmed", version: 1,
    },
  ];
  // Only today's visits have a check-in workflow; 5112 stays open for a manual check-in.
  const workflows = [
    { appointment_id: "5101", journey_id: "9401", patient_id: patient.id, doctor_id: "8001", state: "checked_in" as WorkflowState, checkin_window: { starts_at: minutes(-20), ends_at: minutes(40) }, queue_entry_id: "9301" as string | null, version: 2 },
    { appointment_id: "5112", journey_id: "9402", patient_id: patient.id, doctor_id: "8002", state: "booked" as WorkflowState, checkin_window: { starts_at: minutes(-35), ends_at: minutes(25) }, queue_entry_id: null as string | null, version: 1 },
  ];

  const at = (date: string) => `${date}Z`;
  const consultation = (id: string, appointment_id: string, doctor_id: string, status: Consultation["status"], summary: string, assessment: string, plan: string): Consultation => ({
    id, appointment_id, patient_id: patient.id, doctor_id, status, clinical_content: { summary, assessment, plan }, revision: 1, version: status === "draft" ? 1 : 2,
  });
  const consultations: Consultation[] = [
    consultation("5501", "5101", "8001", "finalized",
      "Routine review. Reports a mild frontal headache for two days, worse in the evenings, and a sore throat since the weekend. No fever recorded at home.",
      "Likely tension-type headache with an uncomplicated upper respiratory infection. No red-flag features reported.",
      "Paracetamol when needed for pain. Five-day amoxicillin course for the throat infection. Omeprazole for one week while on antibiotics. Review in one week if symptoms persist."),
    consultation("5502", "5102", "8002", "finalized",
      "Follow-up for intermittent wheeze on exertion over the past month. Uses no regular inhaler.",
      "Exercise-associated wheeze; spirometry not performed at this visit.",
      "Reliever inhaler as needed. Keep a symptom diary and return if needed more than three times a week."),
    consultation("5503", "5103", "8003", "finalized",
      "Presented with a painful ankle after a minor fall the previous day. Walking with a mild limp.",
      "Soft-tissue ankle sprain. No bony tenderness reported.",
      "Rest, ice and elevation. Short course of anti-inflammatory tablets after food. Prescription later revoked when the patient reported stomach discomfort."),
    consultation("5504", "5104", "8001", "finalized",
      "Annual check. No current complaints.",
      "Well adult review.",
      "No medication changes. Routine follow-up in twelve months."),
    consultation("5505", "5105", "8002", "finalized",
      "Dry cough for ten days after a cold. Sleeping well, eating normally.",
      "Post-viral cough, improving.",
      "Fluids and rest. Return if the cough lasts beyond three weeks or breathing becomes difficult."),
    consultation("5506", "5106", "8001", "draft",
      "Draft: patient reports improvement in headache since last visit.",
      "Draft assessment pending examination.",
      "Draft plan pending."),
  ];
  const record = (id: string, consultation_id: string, created: string, revision = 1, supersedes_id: string | null = null): MedicalRecord & { created_at: string } => {
    const source = consultations.find((item) => item.id === consultation_id)!;
    return { id, consultation_id, patient_id: patient.id, content: { ...source.clinical_content }, revision, supersedes_id, version: 1, created_at: at(created) };
  };
  const records = [
    record("5601", "5501", "2026-10-13T10:30:00"),
    record("5602", "5502", "2026-08-02T16:15:00"),
    record("5607", "5502", "2026-08-05T09:40:00", 2, "5602"),
    record("5603", "5503", "2026-06-14T11:20:00"),
    record("5604", "5504", "2026-03-05T09:00:00"),
    record("5605", "5505", "2026-01-10T14:10:00"),
  ];
  records[2].content.assessment = "Exercise-associated wheeze; spirometry not performed at this visit. Amended after review: peak-flow diary recommended before the next appointment.";
  const grants: Grant[] = [];

  const emergency = (id: string, state: Emergency["state"], reported_urgency: Emergency["reported_urgency"], assigned_priority: number | null, createdMinutesAgo: number, description: string, patient_id = patient.id, claimed_by_user_id: string | null = null, claimMinutes: number | null = null, contact: string | null = null): Emergency => ({
    id, state, reported_urgency, assigned_priority, created_at: minutes(-createdMinutesAgo), updated_at: minutes(-Math.max(1, Math.floor(createdMinutesAgo / 3))),
    patient_id, description, synthetic_contact: contact, claimed_by_user_id, claim_expires_at: claimMinutes === null ? null : minutes(claimMinutes), version: 1,
  });
  const emergencies: Emergency[] = [
    emergency("7101", "submitted", "urgent", null, 4, "sudden chest tightness while climbing stairs, now resting.", patient.id, null, null, "asha.rao@example.test"),
    emergency("7102", "submitted", "unspecified", null, 11, "dizziness after skipping lunch.", "2002"),
    emergency("7103", "triaged", "urgent", 1, 16, "difficulty breathing reported by a family member; speaking in short sentences.", "2003", null, null, "+91-90000-00003"),
    emergency("7104", "triaged", "urgent", 2, 23, "deep cut on the palm from a kitchen knife, bleeding controlled with pressure.", "2004"),
    emergency("7105", "triaged", "unspecified", 4, 38, "rash on both forearms since this morning, mildly itchy.", "2005"),
    emergency("7106", "claimed", "urgent", 2, 27, "high fever and vomiting in a young adult since last night; unable to keep fluids down.", "2006", "1099", 12, "+91-90000-00006"),
    emergency("7107", "processing", "unspecified", 3, 52, "twisted knee during football.", "2007", "1006", 9),
    emergency("7108", "resolved", "unspecified", 5, 140, "request for advice about a minor burn.", patient.id),
    emergency("7109", "cancelled", "urgent", null, 95, "test request cancelled by the patient.", patient.id),
  ];

  const tariff = (id: string, charge_code: string, revision: number, unit_amount_minor: number): Tariff => ({ id, charge_code, revision, unit_amount_minor, currency: "INR", version: 1 });
  const tariffs: Tariff[] = [
    tariff("9601", "consultation", 1, 50000),
    tariff("9602", "consultation", 2, 60000),
    tariff("9603", "medicine:3001", 1, 1800),
    tariff("9604", "medicine:3002", 1, 7500),
    tariff("9605", "medicine:3004", 1, 2200),
    tariff("9606", "medicine:3008", 1, 32000),
  ];
  type Line = Invoice["items"][number];
  const line = (id: string, charge_code: string, source_service: Line["source_service"], source_item_id: string, quantity: number, unit_amount_minor: number, tariff_revision: number): Line => ({ id, charge_code, source_service, source_item_id, quantity, unit_amount_minor, tariff_revision });
  const invoice = (id: string, appointment_id: string, items: Line[], paid_minor: number): Invoice => {
    const total_minor = items.reduce((sum, item) => sum + item.quantity * item.unit_amount_minor, 0);
    return { id, journey_id: null, appointment_id, patient_id: patient.id, status: paid_minor >= total_minor && total_minor > 0 ? "paid" : "open", items, total_minor, paid_minor, balance_minor: total_minor - paid_minor, currency: "INR", version: 1 };
  };
  const invoices: Invoice[] = [
    invoice("9701", "5101", [
      line("9711", "consultation", "records", "5501", 1, 60000, 2),
      line("9712", "medicine:3001", "pharmacy", "9811", 4, 1800, 1),
      line("9713", "medicine:3002", "pharmacy", "9812", 6, 7500, 1),
    ], 0),
    invoice("9702", "5102", [
      line("9721", "consultation", "records", "5502", 1, 50000, 1),
      line("9722", "medicine:3008", "pharmacy", "9821", 1, 32000, 1),
    ], 30000),
    invoice("9703", "5103", [line("9731", "consultation", "records", "5503", 1, 60000, 2)], 60000),
  ];
  const payments: Payment[] = [
    { id: "9751", invoice_id: "9702", amount_minor: 20000, currency: "INR", status: "declined", version: 1 },
    { id: "9752", invoice_id: "9702", amount_minor: 30000, currency: "INR", status: "success", version: 1 },
    { id: "9753", invoice_id: "9703", amount_minor: 60000, currency: "INR", status: "success", version: 1 },
  ];

  const queue = [
    { id: "9299", appointment_id: "5120", doctor_id: "8001", local_date: day(0), token_number: 1, state: "in_consultation" as const, position: null, version: 2, patient_id: "2002" },
    { id: "9300", appointment_id: "5121", doctor_id: "8001", local_date: day(0), token_number: 2, state: "waiting" as const, position: 1, version: 1, patient_id: "2003" },
    { id: "9301", appointment_id: "5101", doctor_id: "8001", local_date: day(0), token_number: 3, state: "waiting" as const, position: 2, version: 1, patient_id: patient.id },
    { id: "9302", appointment_id: "5122", doctor_id: "8001", local_date: day(0), token_number: 4, state: "waiting" as const, position: 3, version: 1, patient_id: "2002" },
  ];
  const waitlists = [
    { id: "9501", slot_id: "8" + day(1).replaceAll("-", "") + "0930", patient_id: patient.id, state: "waiting" as "waiting" | "promoted" | "withdrawn" | "skipped", joined_at: minutes(-90), promoted_appointment_id: null, skip_reason: null, version: 1 },
  ];
  const proposals = [
    { id: "8201", doctor_id: "8001", revision: 2, status: "accepted" as const, timezone: "Asia/Kolkata", slot_minutes: 30, intervals: [{ starts_at: `${day(1)}T09:00:00Z`, ends_at: `${day(1)}T12:00:00Z` }, { starts_at: `${day(1)}T14:00:00Z`, ends_at: `${day(1)}T17:00:00Z` }], conflicts: [], version: 2 },
    { id: "8202", doctor_id: "8001", revision: 3, status: "pending" as const, timezone: "Asia/Kolkata", slot_minutes: 30, intervals: [{ starts_at: `${day(8)}T09:00:00Z`, ends_at: `${day(8)}T12:00:00Z` }], conflicts: [], version: 1 },
  ];

  return {
    queue,
    workflows,
    checkinLinks: new Map<string, string>(),
    checkinEntries: new Map<string, { id: string; token_number: number }>(),
    waitlists,
    proposals,
    journeyVersion: 3,
    otherPatients,
    surge: { state: "NORMAL", version: 4, changed_at: minutes(-180), expires_at: null as string | null, reason_code: "planned_recovery" as string | null },
    consultations,
    records,
    grants,
    emergencies,
    tariffs,
    invoices,
    payments,
    patient,
    medicines,
    batches,
    prescriptions,
    reservations,
    dispensings,
    specialties,
    doctors,
    appointments,
    nextId: 100000,
    fulfillmentVersions: new Map<string, number>(),
    day,
    minutes,
  };
}

export type MockState = ReturnType<typeof createState>;
