import type {
  Batch,
  Dispensing,
  Doctor,
  Medicine,
  Prescription,
  Reservation,
  Specialty,
  Appointment,
} from "../src/hospital/models";
import type { PatientProfile } from "../src/api/authApi";
import type { Role } from "../src/auth/authContext";

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
  ];

  const doctors: Doctor[] = [
    { id: "8001", display_name: "Dr. Meera Iyer", specialties: [{ id: "8101", name: "General Medicine" }], active: true, version: 1 },
    { id: "8002", display_name: "Dr. Kabir Sethi", specialties: [{ id: "8102", name: "Pulmonology" }], active: true, version: 1 },
    { id: "8003", display_name: "Dr. Nisha Pillai", specialties: [{ id: "8103", name: "Dermatology" }], active: true, version: 1 },
  ];

  const appointments: Appointment[] = [
    {
      id: "5101", journey_id: null, patient_id: patient.id, doctor_id: "8001", slot_id: "9101",
      starts_at: minutes(40), ends_at: minutes(55), state: "confirmed", version: 1,
    },
  ];

  return {
    patient,
    medicines,
    batches,
    prescriptions,
    reservations,
    dispensings,
    specialties,
    doctors,
    appointments,
    nextId: 9500,
    fulfillmentVersions: new Map<string, number>(),
    day,
    minutes,
  };
}

export type MockState = ReturnType<typeof createState>;
