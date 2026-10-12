# Phase 4.8 frontend handoff

Base: 45273ea7fd1ea53e335942b6c38f2d81d38856ee

Agent 8 exports these unmounted components from src/phase4/index.ts:

- DoctorAutocomplete and MedicineAutocomplete; use DoctorAutocomplete with kind="specialty" for specialty search.
- AppointmentShortLinkPanel and ShortLinkLanding.
- InsuranceEstimatePanel and InsuranceRefreshPanel.
- AdmissionFeedback.

## Coordinator mounting

- Mount DoctorAutocomplete and DoctorAutocomplete with kind="specialty" beside the directory search in DoctorDirectory in patientDoctor.tsx, used by /patient/doctors. Doctor selection during booking can also be mounted in the existing Appointments component in that file, used by /patient/appointments.
- Mount MedicineAutocomplete in MedicineCatalog in pharmacy.tsx, used by /patient/pharmacy and /pharmacist/inventory. It can also be used in the existing doctor prescription workflow if that workflow needs catalog selection.
- Mount AppointmentShortLinkPanel beside appointment rows/details in Appointments in patientDoctor.tsx, used by /patient/appointments and /receptionist/appointments. Pass the visible appointment ID, useAuth().api, and current role hints. Mount ShortLinkLanding at the literal /short-link route in App.tsx before workspace routes and outside patient-only route gates. Pass authState, role hints, and useAuth().api; preserve the existing /s/ same-origin gateway route.
- Mount InsuranceEstimatePanel beside the selected invoice in BillingPage in billingEmergency.tsx, used by /patient/billing and /billing/invoices. Supply provider and policy choices only from coordinator-approved synthetic configuration; the current contracts do not expose a patient provider/policy discovery route.
- Mount InsuranceRefreshPanel in the existing /billing/insurance workspace page declared in workspaces.ts and map it in HospitalPage.tsx for Billing staff or administrators. The component uses the provider-list response ETag for the frozen refresh If-Match; if the owner API does not return one, refresh stays disabled.
- Mount AdmissionFeedback beside owner-operation errors in Appointments, PatientCheckinPage, MedicineCatalog, BillingPage, and ReceptionWorkflowPanel. Use the exact owner operation error and pass an explicit safe retry callback where the action supports one. The component does not retry requests automatically.

The components use only the Phase 4 frozen endpoints plus existing workflow and invoice reads. No routing, auth provider, layout, page, package, or lockfile was changed here.

## Integration notes

- Short-link paths and aliases stay in component memory until copied or followed. The landing clears the fragment before resolving, requires an authenticated patient/reception role hint, validates the service-returned fixed destination, and never issues or redeems a QR credential.
- Autocomplete cancels pending requests, drops out-of-order responses, and displays whether the owner served trie or database results. Medicine stock and price are not displayed.
- Estimates are labeled simulated, include freshness and version provenance, and do not represent coverage approval.
- The current shared ApiClient converts non-2xx responses to ApiError without attaching response headers. The local feedback adapter reads Retry-After when an injected error exposes it as retryAfter, retryAfterSeconds, or headers; with the current client, 429 copy uses the safe generic wait message. Coordinator can expose that metadata compatibly without changing these components.
