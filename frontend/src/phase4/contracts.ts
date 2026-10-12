import type { ApiClient } from "../api/client";
import type { Role } from "../auth/authContext";

export type ID = string;
export type SuggestionKind = "doctor" | "specialty" | "medicine";

export interface Suggestion {
  id: ID;
  kind: SuggestionKind;
  label: string;
}

export interface SuggestionPage {
  items: Suggestion[];
  index_version: number | null;
  source: "trie" | "database";
}

export interface Phase4ComponentProps {
  api: ApiClient;
  roleHints: readonly Role[];
}

export interface DoctorAutocompleteProps extends Phase4ComponentProps {
  kind?: "doctor" | "specialty";
  label?: string;
  placeholder?: string;
  id?: string;
  disabled?: boolean;
  onSelect(suggestion: Suggestion): void;
}

export interface MedicineAutocompleteProps extends Phase4ComponentProps {
  label?: string;
  placeholder?: string;
  id?: string;
  disabled?: boolean;
  onSelect(suggestion: Suggestion): void;
}

export type ShortLinkPurpose = "appointment" | "check_in";

export interface AppointmentWorkflow {
  appointment_id: ID;
  patient_id: ID;
  doctor_id: ID;
  state: string;
  version: number;
}

export interface ShortLink {
  id: ID;
  appointment_id: ID;
  purpose: ShortLinkPurpose;
  short_path: string;
  expires_at: string;
  version: number;
}

export interface RevokedShortLink {
  id: ID;
  appointment_id: ID;
  purpose: ShortLinkPurpose;
  expires_at: string;
  revoked: true;
  version: number;
}

export interface AppointmentShortLinkPanelProps extends Phase4ComponentProps {
  appointmentId: ID;
  onWorkflowChanged?(workflow: AppointmentWorkflow): void;
}

export type ShortLinkAuthState = "checking" | "anonymous" | "authenticated";

export interface ShortLinkResolution {
  appointment_id: ID;
  purpose: ShortLinkPurpose;
  landing_path: string;
  expires_at: string;
}

export interface ShortLinkLandingProps extends Phase4ComponentProps {
  authState: ShortLinkAuthState;
  onNavigate?(path: string): void;
}

export interface InsuranceEstimate {
  id: ID;
  invoice_id: ID;
  invoice_version: number;
  provider_id: ID;
  policy_code: string;
  rules_id: ID;
  rule_revision: number;
  source_run_id: ID;
  currency: "INR";
  eligible_minor: number;
  estimate_minor: number;
  calculated_at: string;
  freshness_state: "fresh" | "stale";
  is_simulated: true;
  version: number;
}

export interface InsuranceEstimatePage {
  items: InsuranceEstimate[];
  next_cursor: string | null;
}

export interface InsuranceProvider {
  id: ID;
  synthetic_slug: string;
  last_success_at: string | null;
  version?: number;
}

export interface InsuranceProviderPage {
  items: InsuranceProvider[];
  next_cursor: string | null;
}

export interface InsuranceProviderChoice {
  id: ID;
  syntheticSlug: string;
  policyCodes: string[];
}

export interface InsuranceEstimatePanelProps extends Phase4ComponentProps {
  invoiceId: ID;
  providerChoices?: readonly InsuranceProviderChoice[];
}

export interface InsuranceRefreshRun {
  run_id: ID;
  provider_id: ID;
  state: "pending";
  version: number;
}

export interface InsuranceRunStatus {
  id: ID;
  provider_id: ID;
  state: "pending" | "running" | "complete" | "partial" | "failed";
  pages_processed: number;
  error_code: string | null;
  version: number;
}

export interface InsuranceRefreshPanelProps extends Phase4ComponentProps {}

export interface AdmissionFeedbackProps {
  error: unknown;
  onRetry?(): void;
  retryLabel?: string;
  operationLabel?: string;
}
