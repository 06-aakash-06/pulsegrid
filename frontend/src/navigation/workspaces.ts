import type { Role } from "../auth/authContext";

export interface WorkspacePage {
  path: string;
  title: string;
  description: string;
  emptyMessage: string;
}

export interface WorkspaceNavItem {
  path: string;
  label: string;
}

export interface WorkspaceConfig {
  basePath: string;
  name: string;
  roleLabel: string;
  roles: Role[];
  navigation: WorkspaceNavItem[];
  pages: WorkspacePage[];
}

function page(
  path: string,
  title: string,
  description: string,
  emptyMessage: string,
): WorkspacePage {
  return { path, title, description, emptyMessage };
}

function workspace(
  basePath: string,
  name: string,
  roleLabel: string,
  roles: Role[],
  pages: WorkspacePage[],
): WorkspaceConfig {
  return {
    basePath,
    name,
    roleLabel,
    roles,
    pages,
    navigation: pages.map(({ path, title }) => ({ path, label: title })),
  };
}

export const workspaces: WorkspaceConfig[] = [
  workspace("/patient", "Patient workspace", "Patient", ["patient"], [
    page("dashboard", "Dashboard", "A starting point for appointments and care updates.", "Your patient workspace will show service information after a secure connection is configured."),
    page("doctors", "Find a doctor", "Search the doctor directory when the service is available.", "Doctor search is not connected yet."),
    page("appointments", "Appointments", "Review and manage appointment information.", "Appointments will appear here when the appointment service is connected."),
    page("waitlist", "Waitlist", "Review waitlist requests and their current state.", "Waitlist information is not connected yet."),
    page("check-in", "QR check-in", "Use an appointment check-in link issued by the appointment service.", "Check-in links will appear after appointment integration. Opening a link will not check you in by itself."),
    page("queue", "Live queue", "See your own queue information and permitted position updates.", "Queue information is not connected yet."),
    page("journey", "Patient journey", "Review the appointment journey projection and its freshness.", "Journey stages will appear after appointment integration. Pending stages will remain explicit."),
    page("records", "Medical records", "Open records that the records service authorizes for your account.", "No records are loaded. Medical content is never fabricated in this preview."),
    page("prescriptions", "Prescriptions", "Review prescription information provided by the records service.", "Prescription information is not connected yet."),
    page("pharmacy", "Pharmacy", "Review medicine and reservation information from the pharmacy service.", "Pharmacy information is not connected yet."),
    page("billing", "Billing", "Review invoices and simulated payment status from the billing service.", "Billing information is not connected yet."),
    page("emergency", "Emergency requests", "Review an emergency request status when the service is connected.", "Emergency tracking is not connected yet. This preview does not submit or triage requests."),
  ]),
  workspace("/doctor", "Doctor workspace", "Doctor", ["doctor"], [
    page("dashboard", "Dashboard", "A starting point for assigned consultations and schedule updates.", "Doctor workspace data is not connected yet."),
    page("consultations", "Consultations", "Open consultation work assigned through the appointment service.", "Consultations are not connected yet. No patient information is shown in this preview."),
    page("queue", "Queue management", "Review assigned queue state from the appointment service.", "Queue information is not connected yet."),
    page("prescriptions", "Prescription management", "Author prescription changes through the records service.", "Prescription management is not connected yet. This page does not create prescriptions."),
  ]),
  workspace("/pharmacist", "Pharmacy workspace", "Pharmacist", ["pharmacist"], [
    page("dashboard", "Dashboard", "A starting point for pharmacy catalog and fulfillment work.", "Pharmacy workspace data is not connected yet."),
    page("inventory", "Inventory", "Review catalog and inventory details from the pharmacy service.", "Inventory is not connected yet. No stock totals are fabricated."),
    page("prescriptions", "Prescription fulfillment", "Use the minimum prescription context provided for pharmacy fulfillment.", "Prescription fulfillment is not connected yet. Dispensing remains unavailable."),
  ]),
  workspace("/billing", "Billing workspace", "Billing staff", ["billing_staff"], [
    page("dashboard", "Dashboard", "A starting point for invoice and payment work.", "Billing workspace data is not connected yet."),
    page("invoices", "Invoices", "Review invoice records owned by the billing service.", "Invoices are not connected yet."),
    page("payments", "Payment management", "Review simulated payment records and status.", "Payments are not connected yet. No payment is processed in this preview."),
    page("insurance", "Insurance estimates", "Review fixture-based estimates and their freshness when available.", "Insurance estimates are not connected yet. Estimates are informational, not coverage decisions."),
  ]),
  workspace("/emergency", "Emergency workspace", "Emergency staff", ["emergency_staff"], [
    page("dashboard", "Dashboard", "A starting point for emergency request work.", "Emergency operations are not connected yet."),
    page("requests", "Emergency management", "Review and update request state through the emergency service.", "Emergency requests are not connected yet. This preview does not assess urgency or dispatch help."),
  ]),
  workspace("/admin", "Administration", "Hospital administrator", ["hospital_admin"], [
    page("dashboard", "Dashboard", "A starting point for authorized hospital administration.", "Administration data is not connected yet."),
    page("staff", "Staff and roles", "Manage staff identity and role assignments through the patient service.", "Staff administration is not connected yet."),
    page("doctors", "Doctor directory", "Manage doctor profiles through the doctor service.", "Doctor administration is not connected yet."),
    page("settings", "Administration", "Review available hospital configuration interfaces.", "Administrative configuration is not connected yet."),
  ]),
];

export function getPageForPath(workspaceConfig: WorkspaceConfig, path: string): WorkspacePage | undefined {
  return workspaceConfig.pages.find((workspacePage) => workspacePage.path === path);
}
