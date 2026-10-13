# Phase 9 frontend audit

Baseline: `main`, `56fe35053e69802c2ac0bf582ff508623a1a2313`, clean tree. Single agent, same checkout. Existing React 19 / TypeScript / Vite 6 / React Router 7, memory-only auth with cookie refresh and serialized CSRF; no state framework or component library. Read README, AGENTS, Phase 3 contracts, Phase 4 component contracts, and Phase 7 observability design. Preserve API ownership, ETags and frozen idempotent command attempts.

## Complete route inventory

| Route | Owning role | Capabilities/backend | Reference/composition | Acceptance |
|---|---|---|---|---|
| `/patient/dashboard` | `patient` | Dashboard: Patient own profile or permitted demographic/account management | Reception; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/doctors` | `patient` | Find a doctor: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/appointments` | `patient` | Appointments: Doctor autocomplete; Appointment availability/book/list/detail/cancel/reschedule/short-link; reception workflows | Appointments; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/waitlist` | `patient` | Waitlist: Appointment workflows/check-in/queue/waitlist/offers/history | Waiting Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/check-in` | `patient` | QR check-in: Appointment workflows/check-in/queue/waitlist/offers/history | Waiting Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/queue` | `patient` | Live queue: Appointment workflows/check-in/queue/waitlist/offers/history | Waiting Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/journey` | `patient` | Patient journey: Records consultations/history/amendments/grants; Appointment journey/history | Medical Records; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/records` | `patient` | Medical records: Records consultations/history/amendments/grants; Appointment journey/history | Medical Records; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/prescriptions` | `patient` | Prescriptions: Pharmacy catalog/batches/reservations/dispensing; Records authorized prescription detail | Pharmacy; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/pharmacy` | `patient` | Pharmacy: Pharmacy catalog/batches/reservations/dispensing; Records authorized prescription detail | Pharmacy; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/billing` | `patient` | Billing: Billing invoice/charge/payment/tariff; insurance fixture refresh/estimates | Billing; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/patient/emergency` | `patient` | Emergency requests: Emergency requests/detail/priority/leases/transitions | Emergency; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/doctor/dashboard` | `doctor` | Dashboard: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/doctor/consultations` | `doctor` | Consultations: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/doctor/queue` | `doctor` | Queue management: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/doctor/prescriptions` | `doctor` | Prescription management: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/pharmacist/dashboard` | `pharmacist` | Dashboard: Pharmacy catalog/batches/reservations/dispensing; Records authorized prescription detail | Pharmacy; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/pharmacist/inventory` | `pharmacist` | Inventory: Pharmacy catalog/batches/reservations/dispensing; Records authorized prescription detail | Pharmacy; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/pharmacist/prescriptions` | `pharmacist` | Prescription fulfillment: Pharmacy catalog/batches/reservations/dispensing; Records authorized prescription detail | Pharmacy; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/billing/dashboard` | `billing_staff` | Dashboard: Billing invoice/charge/payment/tariff; insurance fixture refresh/estimates | Billing; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/billing/invoices` | `billing_staff` | Invoices: Billing invoice/charge/payment/tariff; insurance fixture refresh/estimates | Billing; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/billing/payments` | `billing_staff` | Payment management: Billing invoice/charge/payment/tariff; insurance fixture refresh/estimates | Billing; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/billing/insurance` | `billing_staff` | Insurance estimates: Billing invoice/charge/payment/tariff; insurance fixture refresh/estimates | Billing; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/emergency/dashboard` | `emergency_staff` | Dashboard: Emergency requests/detail/priority/leases/transitions | Emergency; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/emergency/requests` | `emergency_staff` | Emergency management: Emergency requests/detail/priority/leases/transitions | Emergency; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/dashboard` | `hospital_admin` | Dashboard: Patient own profile or permitted demographic/account management | Reception; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/staff` | `hospital_admin` | Staff and roles: Patient own profile or permitted demographic/account management | Reception; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/doctors` | `hospital_admin` | Doctor directory: Doctor profiles/specialties/proposals; Appointment decisions/availability; Records authoring for doctor | Consultation; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/control-room` | `hospital_admin` | Control Room: Patient ops proxy → Prometheus/Tempo; health, alerts, rates, traces, Surge Mode | Control Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/traces` | `hospital_admin` | Trace Explorer: Patient ops proxy → Prometheus/Tempo; health, alerts, rates, traces, Surge Mode | Control Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/admin/settings` | `hospital_admin` | Administration: No generic settings write API; offer links to real staff/directory/monitoring management | Reception; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/receptionist/dashboard` | `receptionist` | Dashboard: Patient own profile or permitted demographic/account management | Reception; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/receptionist/appointments` | `receptionist` | Appointment coordination: Doctor autocomplete; Appointment availability/book/list/detail/cancel/reschedule/short-link; reception workflows | Appointments; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/ops/dashboard` | `ops` | Control Room: Patient ops proxy → Prometheus/Tempo; health, alerts, rates, traces, Surge Mode | Control Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |
| `/ops/traces` | `ops` | Trace Explorer: Patient ops proxy → Prometheus/Tempo; health, alerts, rates, traces, Surge Mode | Control Room; adapt approved parent composition | Role gate; owner loading/error/empty/detail; existing form review/version/retry; responsive navigation |

Public `/`: reception entrance/sign-in/account creation. `/login`: credential validation/password reveal/CSRF/session/return destination. `/register`: validated demographics and frozen anonymous idempotency retry, successful registration does not authenticate. `/short-link`: authenticated fixed resolver with no arbitrary redirect, fragment secret lifecycle. Workspace root paths redirect to dashboard; unknown root/workspace paths show 404. Unauthorized/checking/no-role states retain existing access components.

## Complete interaction inventory from existing implementation

- `frontend/src/advanced/patient/PatientFulfillmentPanel.tsx`: ReservationStatus, PatientFulfillmentPanel.
- `frontend/src/advanced/patient/WaitlistOffers.tsx`: WaitlistOffers.
- `frontend/src/advanced/patient/hooks.tsx`: PatientGate.
- `frontend/src/advanced/patient/pages.tsx`: RetryButton, WaitlistCount, PatientWaitlistPage, PatientCheckinPage, PatientQueuePage, JourneyTimeline, PatientJourneyPage.
- `frontend/src/advanced/shared/CheckinQr.tsx`: CheckinQr.
- `frontend/src/advanced/shared/WorkflowHistory.tsx`: WorkflowHistory.
- `frontend/src/components/RouteAccess.tsx`: SessionLoading, RequireRole, NotFoundPage.
- `frontend/src/hospital/HospitalPage.tsx`: HospitalPage.
- `frontend/src/hospital/billingEmergency.tsx`: BillingPage, Tariffs, EmergencyPage, InsurancePage.
- `frontend/src/hospital/patientDoctor.tsx`: ProfileEditor, PatientDashboard, Demographics, StaffManagement, AvailabilityPicker, Booking, DoctorDirectory, Appointments, ScheduleForm, DoctorManagement, DoctorDashboard.
- `frontend/src/hospital/pharmacy.tsx`: MedicineCatalog, StockAdjustment, Reserve, Fulfillment.
- `frontend/src/hospital/records.tsx`: PrescriptionItems, ClinicalFacts, ConsultationEditor, Consultations, History, Grants, RecordsPage, PrescriptionDetail, Prescriptions.
- `frontend/src/hospital/staffAdvanced/CheckinScanner.tsx`: CheckinScanner.
- `frontend/src/hospital/staffAdvanced/DoctorQueuePage.tsx`: DoctorQueuePage.
- `frontend/src/hospital/staffAdvanced/JourneyTools.tsx`: StaffJourneyTools.
- `frontend/src/hospital/staffAdvanced/QueueTransitions.tsx`: QueueTransitions.
- `frontend/src/hospital/staffAdvanced/ReceptionWorkflowPanel.tsx`: CheckinPanel, ReceptionWorkflowPanel.
- `frontend/src/hospital/staffAdvanced/StaffFulfillmentPanel.tsx`: FulfillmentStatusLookup, StockVerification, StaffFulfillmentPanel.
- `frontend/src/hospital/staffAdvanced/StaffRoleGate.tsx`: StaffRoleGate.
- `frontend/src/hospital/ui.tsx`: Panel, Resource, Collection, CollectionPage, Inputs, CommandForm, Lookup, Facts, Selected.
- `frontend/src/ops/ControlRoom.tsx`: MetricCard, TrendChart, EmptyRows, ControlRoom, ComponentList, TraceExplorer.
- `frontend/src/pages/AuthPages.tsx`: LoginPage, RegistrationPage, AuthFrame.
- `frontend/src/pages/HomePage.tsx`: HomePage.
- `frontend/src/pages/PlaceholderPage.tsx`: PlaceholderPage.
- `frontend/src/phase4/AdmissionFeedback.tsx`: AdmissionFeedback.
- `frontend/src/phase4/AppointmentShortLinkPanel.tsx`: ShortLinkEntry, AppointmentShortLinkPanel.
- `frontend/src/phase4/Autocomplete.tsx`: Autocomplete, DoctorAutocomplete, MedicineAutocomplete.
- `frontend/src/phase4/InsurancePanels.tsx`: EstimateCard, InsuranceEstimatePanel, InsuranceRefreshPanel.
- `frontend/src/phase4/ShortLinkLanding.tsx`: ShortLinkLanding.

All commands retain inline review/confirm/keep-editing, pending disablement, explicit ambiguous retry, success and missing/stale-ETag handling. Lists retain bounded cursor pagination and filter reset. Detail lookup forms, patient profile/account roles, schedule interval editing/proposal decisions/reconcile, record finalize/amend/revoke/grants, stock adjustment, reservation release/revalidate/dispense, manual charges/simulated decline, insurance provider refresh, emergency claim/release/priority/transitions, queue enrollment/no-show/skip/recall/call-next/discharge/history, QR issue/scan/manual fallback, short-link resolve and expiry, rate-limit Retry-After, trace lookup and Surge confirmation are covered by these components. No hidden modal/drawer/detail route exists outside the listed sources; review is inline, scanner is mounted in its workflow.

## Foundation and deployment inspection

`api/client.ts` preserves bearer refresh and error/request metadata. `authContext.tsx` role hints are navigation hints only; eight roles: patient, doctor, pharmacist, billing_staff, emergency_staff, hospital_admin, receptionist, ops. JWT exposes subject/roles, not a display name; staff header uses actual subject ID instead of invented name. Patient reception obtains display_name from owner profile. `vite.config.ts` proxies `/api` and `/s/` to gateway, splits QR encoder/decoder; retain these and lazy HospitalPage. Dockerfile serves production static build via nginx; no container/config/database changes needed. Existing CSS imports occur within lazily loaded workflows, requiring global design overrides that remain effective after imports.

## Unsupported reference features

No notification feed, global entity search, doctor photography/ratings, lab/imaging/vitals/bed/CCTV APIs, emergency treatment/orders/admission, guest walk-in creation, retail upload/cart/prices, invoice draft/discount or estimated waiting-time service. Header search indexes only permitted routes and points to existing department search. Notifications show honest absence without a fake badge. Existing identity/profile, demographic booking and technical monitoring provide supported alternatives.
