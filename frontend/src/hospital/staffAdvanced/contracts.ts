export type ID = string;
export type QueueState =
  | "waiting"
  | "skipped"
  | "in_consultation"
  | "completed"
  | "cancelled"
  | "no_show";

export interface DoctorSelf {
  doctor: { id: ID; display_name: string; active: boolean; version: number };
  staff_user_id: ID;
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
  version: number;
}

export interface QueueEntry {
  patient_name?: string;
  id: ID;
  appointment_id: ID;
  doctor_id: ID;
  local_date: string;
  token_number: number;
  state: QueueState;
  position: number | null;
  version: number;
  patient_id: ID;
}

export interface StaffQueue {
  doctor_id: ID;
  local_date: string;
  items: QueueEntry[];
  next_cursor: string | null;
  waiting_count: number;
  in_consultation_count: number;
  version: number;
  observed_at: string;
}

export interface OwnQueue {
  entry: Omit<QueueEntry, "patient_id">;
  waiting_count: number;
  in_consultation_count: number;
  queue_version: number;
  observed_at: string;
}

export interface CheckinResult {
  workflow: Workflow;
  queue_entry: Omit<QueueEntry, "patient_id">;
}

export interface JourneySource {
  owner: "records" | "pharmacy" | "billing";
  resource_type: string;
  resource_id: ID;
  version: number;
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
  sources: JourneySource[];
  observed_at: string | null;
  pending_reason:
    | "awaiting_source"
    | "owner_unavailable"
    | "source_changed"
    | "unfilled"
    | "missing_invoice"
    | "missing_charges"
    | "unpaid"
    | "review_required"
    | null;
}

export interface Journey {
  id: ID;
  appointment_id: ID;
  patient_id: ID;
  state:
    | "active"
    | "ready"
    | "discharged"
    | "reopened"
    | "cancelled"
    | "no_show";
  stages: JourneyStage[];
  discharge_eligible: boolean;
  review_required: boolean;
  last_reconciled_at: string | null;
  version: number;
}

export interface Prescription {
  id: ID;
  consultation_id: ID;
  patient_id: ID;
  revision: number;
  state: "issued" | "revoked";
  items: {
    id: ID;
    medicine_id: ID;
    quantity: number;
    dosage?: string;
    instructions?: string;
  }[];
  version: number;
}

export interface Fulfillment {
  prescription_id: ID;
  appointment_id: ID;
  patient_id: ID;
  prescription_revision: number;
  prescription_state: "issued" | "revoked";
  items: {
    prescription_item_id: ID;
    medicine_id: ID;
    prescribed_quantity: number;
    reserved_quantity: number;
    dispensed_quantity: number;
    remaining_quantity: number;
  }[];
  reservations: { id: ID; state: "reserved" | "expired" | "released" | "dispensed"; version: number }[];
  dispensings: { id: ID; version: number; source_item_ids: ID[] }[];
  review_required: boolean;
  version: number;
  observed_at: string;
}

export interface Batch {
  id: ID;
  medicine_id: ID;
  batch_code: string;
  expires_on: string;
  on_hand: number;
  reserved: number;
  available: number;
  version: number;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}
