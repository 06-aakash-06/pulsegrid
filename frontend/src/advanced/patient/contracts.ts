export type ID = string;
export type Version = number;

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export interface PatientProfile {
  id: ID;
  display_name?: string;
}

export interface Appointment {
  id: ID;
  journey_id: null;
  patient_id: ID;
  doctor_id: ID;
  slot_id: ID;
  starts_at: string;
  ends_at: string;
  state: "confirmed" | "cancelled";
  version: Version;
}

export interface Waitlist {
  id: ID;
  slot_id: ID;
  patient_id: ID;
  state: "waiting" | "promoted" | "withdrawn" | "skipped";
  joined_at: string;
  promoted_appointment_id: ID | null;
  skip_reason:
    | null
    | "inactive_patient"
    | "patient_overlap"
    | "slot_retired"
    | "window_closed"
    | "offer_expired";
  version: Version;
}

export interface WaitlistSlot {
  slot_id: ID;
  waiting_count: number;
  promotion_pending: boolean;
  accepted_revision: Version;
  observed_at: string;
}

export interface Workflow {
  appointment_id: ID;
  journey_id: ID;
  patient_id: ID;
  doctor_id: ID;
  state:
    | "booked"
    | "checked_in"
    | "in_consultation"
    | "completed"
    | "cancelled"
    | "no_show";
  checkin_window: { starts_at: string; ends_at: string };
  queue_entry_id: ID | null;
  version: Version;
}

export interface TokenIssue {
  link_id: ID;
  appointment_id: ID;
  expires_at: string;
  token: string;
  landing_path: string;
  version: Version;
}

export interface QueueEntry {
  id: ID;
  appointment_id: ID;
  doctor_id: ID;
  local_date: string;
  token_number: number;
  state:
    | "waiting"
  | "skipped"
    | "in_consultation"
    | "completed"
    | "cancelled"
    | "no_show";
  position: number | null;
  version: Version;
}

export interface OwnQueue {
  entry: QueueEntry;
  waiting_count: number;
  in_consultation_count: number;
  queue_version: Version;
  observed_at: string;
}

export interface CheckinResult {
  workflow: Workflow;
  queue_entry: QueueEntry;
}

export interface Source {
  owner: "records" | "pharmacy" | "billing";
  resource_type: string;
  resource_id: ID;
  version: Version;
  observed_at: string;
}

export interface JourneyStage {
  name:
    | "appointment"
    | "check_in"
    | "consultation"
    | "prescription"
    | "pharmacy"
    | "billing";
  state: "pending" | "complete" | "skipped" | "reopened";
  sources: Source[];
  observed_at: string | null;
  pending_reason:
    | null
    | "awaiting_source"
    | "owner_unavailable"
    | "source_changed"
    | "unfilled"
    | "missing_invoice"
    | "missing_charges"
    | "unpaid"
    | "review_required";
}

export interface Journey {
  id: ID;
  appointment_id: ID;
  patient_id: ID;
  state: "active" | "ready" | "discharged" | "reopened" | "cancelled" | "no_show";
  stages: JourneyStage[];
  discharge_eligible: boolean;
  review_required: boolean;
  last_reconciled_at: string | null;
  version: Version;
}

export interface Prescription {
  id: ID;
  consultation_id: ID;
  patient_id: ID;
  journey_id: null;
  revision: Version;
  state: "issued" | "revoked";
  items: {
    id: ID;
    medicine_id: ID;
    quantity: number;
    dosage: string;
    instructions: string;
  }[];
  version: Version;
}

export interface Fulfillment {
  prescription_id: ID;
  appointment_id: ID;
  patient_id: ID;
  prescription_revision: Version;
  prescription_state: "issued" | "revoked";
  items: {
    prescription_item_id: ID;
    medicine_id: ID;
    prescribed_quantity: number;
    reserved_quantity: number;
    dispensed_quantity: number;
    remaining_quantity: number;
  }[];
  reservations: {
    id: ID;
    state: "reserved" | "expired" | "released" | "dispensed";
    version: Version;
  }[];
  dispensings: { id: ID; version: Version; source_item_ids: ID[] }[];
  review_required: boolean;
  version: Version;
  observed_at: string;
}

export interface Reservation {
  id: ID;
  patient_id: ID;
  prescription_id: ID;
  state: "reserved" | "expired" | "released" | "dispensed";
  items: { prescription_item_id: ID; medicine_id: ID; quantity: number }[];
  expires_at: string;
  version: Version;
}

export interface Dispensing {
  id: ID;
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
  version: Version;
}
