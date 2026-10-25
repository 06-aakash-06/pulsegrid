import type { Tour } from "../types";

export const adminTour: Tour = {
  id: "admin",
  role: "hospital_admin",
  workspace: "/admin",
  roleLabel: "Administrator",
  title: "Run the hospital",
  goal: "Manage staff, review doctors, watch system health and preview Surge Mode.",
  summary: "You've seen how an administrator manages accounts and doctors, checks system health, previews Surge Mode and inspects a trace.",
  steps: [
    {
      id: "staff-nav", route: "/admin/dashboard", target: "nav-staff",
      title: "Open Staff & roles",
      body: "Every account and its roles are managed here.",
      advanceOn: { type: "route", value: "^/admin/staff" },
    },
    {
      id: "filter", target: "staff-filters",
      title: "Filter accounts",
      body: "Search by name or filter by role and state, then press Next.",
      behindTheScenes: "Roles live in the Patient service. Every other service checks them on each request, so removing a role takes effect immediately.",
      advanceOn: { type: "manual" },
    },
    {
      id: "open-account", target: "staff-open-account",
      title: "Open an account",
      body: "Open an account to see its roles and status.",
      advanceOn: { type: "click" },
    },
    {
      id: "doctors-nav", target: "nav-doctors",
      title: "Open Consultation",
      body: "Doctor profiles and specialties are managed from the directory.",
      advanceOn: { type: "route", value: "^/admin/doctors" },
    },
    {
      id: "doctors", target: "doctor-option",
      title: "The doctor list",
      body: "Open a doctor to manage their profile.",
      advanceOn: { type: "click" },
    },
    {
      id: "control-nav", target: "nav-control-room",
      title: "Open the Control Room",
      body: "Live health for every service.",
      advanceOn: { type: "route", value: "^/admin/control-room" },
    },
    {
      id: "surge", target: "surge-controls",
      prepare: (api) => api.openDisclosure("surge-controls"),
      title: "Surge Mode",
      body: "Surge Mode protects critical work when the hospital is overloaded. Look at the budgets, then press Next.",
      behindTheScenes: "Admission budgets are shared through Redis so every Appointment replica applies the same limit, but bookings are still decided in PostgreSQL.",
      advanceOn: { type: "manual" },
    },
    {
      id: "surge-review", target: "surge-review",
      title: "Review the change",
      body: "Review shows what would change. You'll cancel next, so nothing is applied.",
      advanceOn: { type: "visible", value: "surge-cancel" },
    },
    {
      id: "surge-cancel", target: "surge-cancel",
      title: "Cancel at review",
      body: "Keep editing cancels the change without applying it.",
      advanceOn: { type: "click" },
    },
    {
      id: "traces-nav", target: "nav-traces",
      title: "Open the Trace Explorer",
      body: "Traces show how one request travelled between services.",
      advanceOn: { type: "route", value: "^/admin/traces" },
    },
    {
      id: "trace", target: "ops-trace-option",
      title: "Open a trace",
      body: "Open a recent request to see which services it touched.",
      advanceOn: { type: "visible", value: "ops-trace-spans" },
    },
  ],
};
