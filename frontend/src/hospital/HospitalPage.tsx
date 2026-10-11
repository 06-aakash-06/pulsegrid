import { PatientWaitlistPage, PatientCheckinPage, PatientQueuePage, PatientJourneyPage, PatientFulfillmentPanel } from "../advanced/patient";
import { WaitlistOffers } from "../advanced/patient/WaitlistOffers";
import { DoctorQueuePage, ReceptionWorkflowPanel, StaffFulfillmentPanel } from "./staffAdvanced";
import type { WorkspaceConfig, WorkspacePage } from "../navigation/workspaces";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import {
  Appointments,
  Demographics,
  DoctorDashboard,
  DoctorDirectory,
  PatientDashboard,
  StaffManagement,
} from "./patientDoctor";
import { Consultations, Prescriptions, RecordsPage } from "./records";
import { MedicineCatalog } from "./pharmacy";
import { BillingPage, EmergencyPage } from "./billingEmergency";

export function HospitalPage({
  workspace,
  page,
}: {
  workspace: WorkspaceConfig;
  page: WorkspacePage;
}) {
  const role = workspace.basePath;
  const route = page.path;
  let content;
  if (role === "/patient") {
    if (route === "dashboard") content = <PatientDashboard />;
    if (route === "doctors") content = <DoctorDirectory />;
    if (route === "appointments") content = <Appointments />;
    if (route === "waitlist") content = <><PatientWaitlistPage /><WaitlistOffers /></>;
    if (route === "check-in") content = <PatientCheckinPage />;
    if (route === "queue") content = <PatientQueuePage />;
    if (route === "journey") content = <PatientJourneyPage />;
    if (route === "records") content = <RecordsPage />;
    if (route === "prescriptions") content = <Prescriptions />;
    if (route === "pharmacy")
      content = (
        <>
          <MedicineCatalog />
          <PatientFulfillmentPanel />
        </>
      );
    if (route === "billing") content = <BillingPage />;
    if (route === "emergency") content = <EmergencyPage />;
  }
  if (role === "/doctor") {
    if (route === "dashboard") content = <DoctorDashboard />;
    if (route === "consultations") content = <Consultations doctor />;
    if (route === "queue") content = <DoctorQueuePage />;
    if (route === "prescriptions")
      content = (
        <>
          <MedicineCatalog />
          <Prescriptions doctor />
        </>
      );
  }
  if (role === "/pharmacist") {
    if (route === "inventory" || route === "dashboard")
      content = <MedicineCatalog staff inventory />;
    if (route === "prescriptions") content = <StaffFulfillmentPanel />;
  }
  if (
    role === "/billing" &&
    ["dashboard", "invoices", "payments"].includes(route)
  )
    content = <BillingPage staff />;
  if (role === "/emergency") content = <EmergencyPage staff />;
  if (role === "/admin") {
    if (route === "dashboard")
      content = (
        <>
          <Demographics admin />
          <MedicineCatalog staff />
        </>
      );
    if (route === "staff") content = <StaffManagement />;
    if (route === "doctors") content = <DoctorDirectory admin />;
  }
  if (role === "/receptionist")
    content =
      route === "dashboard" ? <Demographics /> : <><Appointments reception /><ReceptionWorkflowPanel /></>;
  if (!content)
    return <PlaceholderPage page={page} workspaceName={workspace.name} />;
  return (
    <div className="page-stack">
      <div className="page-heading">
        <div>
          <p className="eyebrow">{workspace.name}</p>
          <h1>{page.title}</h1>
          <p className="page-description">
            Synthetic hospital workspace. Data and actions are authorized by
            each owning service.
          </p>
        </div>
      </div>
      {content}
    </div>
  );
}
