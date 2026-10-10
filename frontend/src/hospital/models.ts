import type { PatientProfile } from "../api/authApi";
import type { Role } from "../auth/authContext";
export type { PatientProfile };
export type ID = string;
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}
export interface Versioned {
  id: ID;
  version: number;
}
export interface UserView extends Versioned {
  email: string;
  display_name: string;
  roles: Role[];
  state: "active" | "disabled";
  auth_version: number;
}
export interface Specialty extends Versioned {
  slug: string;
  name: string;
}
export interface Doctor extends Versioned {
  display_name: string;
  specialties: { id: ID; name: string }[];
  active: boolean;
}
export interface DoctorSelf {
  doctor: Doctor;
  staff_user_id: ID;
}
export interface Interval {
  starts_at: string;
  ends_at: string;
}
export interface Proposal extends Versioned {
  doctor_id: ID;
  revision: number;
  status: "pending" | "accepted" | "rejected";
  timezone: string;
  slot_minutes: number;
  intervals: Interval[];
  conflicts: ID[];
}
export interface Decision {
  proposal_id: ID;
  doctor_id: ID;
  revision: number;
  state: "accepted" | "rejected";
  reason_code: string | null;
  conflicting_appointment_ids: ID[];
  version: number;
}
export interface Slot extends Interval {
  id: ID;
  doctor_id: ID;
  state: "bookable" | "retired";
  revision: number;
}
export interface Availability {
  slots: Slot[];
  accepted_revision: number;
  observed_at: string;
}
export interface Appointment extends Versioned, Interval {
  journey_id: null;
  patient_id: ID;
  doctor_id: ID;
  slot_id: ID;
  state: "confirmed" | "cancelled";
}
export interface Content {
  summary: string;
  assessment: string;
  plan: string;
}
export interface Consultation extends Versioned {
  appointment_id: ID;
  patient_id: ID;
  doctor_id: ID;
  status: "draft" | "finalized";
  clinical_content: Content;
  revision: number;
}
export interface RecordSummary extends Versioned {
  consultation_id: ID;
  patient_id: ID;
  revision: number;
  created_at: string;
}
export interface MedicalRecord extends Versioned {
  consultation_id: ID;
  patient_id: ID;
  content: Content;
  revision: number;
  supersedes_id: ID | null;
}
export interface PrescriptionItemInput {
  medicine_id: ID;
  quantity: number;
  dosage: string;
  instructions: string;
}
export interface Prescription extends Versioned {
  consultation_id: ID;
  patient_id: ID;
  journey_id: null;
  revision: number;
  state: "issued" | "revoked";
  items: (PrescriptionItemInput & { id: ID })[];
}
export interface FinalizeResult {
  consultation: Consultation;
  record: MedicalRecord;
  prescription: Prescription | null;
}
export interface Grant extends Versioned {
  patient_id: ID;
  grantee_user_id: ID;
  scope: "records:read" | "prescriptions:read";
  expires_at: string;
}
export interface Medicine extends Versioned {
  sku: string;
  name: string;
  active: boolean;
  availability: "available" | "unavailable" | "unknown";
  catalog_version: number;
}
export interface Batch extends Versioned {
  medicine_id: ID;
  batch_code: string;
  expires_on: string;
  on_hand: number;
  reserved: number;
  available: number;
}
export interface Reservation extends Versioned {
  patient_id: ID;
  prescription_id: ID;
  state: "reserved" | "expired" | "released" | "dispensed";
  items: { prescription_item_id: ID; medicine_id: ID; quantity: number }[];
  expires_at: string;
}
export interface Dispensing extends Versioned {
  reservation_id: ID;
  prescription_id: ID;
  patient_id: ID;
  appointment_id: ID;
  items: {
    id: ID;
    prescription_item_id: ID;
    medicine_id: ID;
    quantity: number;
  }[];
  completed_at: string;
}
export interface Tariff extends Versioned {
  charge_code: string;
  revision: number;
  unit_amount_minor: number;
  currency: "INR";
}
export interface Invoice extends Versioned {
  journey_id: null;
  appointment_id: ID;
  patient_id: ID;
  status: "open" | "paid";
  items: {
    id: ID;
    charge_code: string;
    source_service: "records" | "pharmacy";
    source_item_id: ID;
    quantity: number;
    unit_amount_minor: number;
    tariff_revision: number;
  }[];
  total_minor: number;
  paid_minor: number;
  balance_minor: number;
  currency: "INR";
}
export interface Payment extends Versioned {
  invoice_id: ID;
  amount_minor: number;
  currency: "INR";
  status: "success" | "declined";
}
export interface Emergency extends Versioned {
  state:
    | "submitted"
    | "triaged"
    | "claimed"
    | "processing"
    | "resolved"
    | "cancelled";
  reported_urgency: "unspecified" | "urgent";
  assigned_priority: number | null;
  created_at: string;
  updated_at: string;
  patient_id?: ID;
  description?: string;
  synthetic_contact?: string | null;
  claimed_by_user_id?: ID | null;
  claim_expires_at?: string | null;
}
