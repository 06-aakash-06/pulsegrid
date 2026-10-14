import { DepartmentIcon, departmentFor, departmentDescriptions } from "../design/DepartmentIcon";
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
import { BillingPage, EmergencyPage, InsurancePage } from "./billingEmergency";
import { ControlRoom, TraceExplorer } from "../ops/ControlRoom";

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
  if (role === "/billing" && route === "insurance") content = <InsurancePage />;
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
    if (route === "control-room") content = <ControlRoom workspaceBasePath="/admin" />;
    if (route === "traces") content = <TraceExplorer />;
  }
  if (role === "/ops") {
    if (route === "dashboard") content = <ControlRoom workspaceBasePath="/ops" />;
    if (route === "traces") content = <TraceExplorer />;
  }
  if (role === "/receptionist")
    content =
      route === "dashboard" ? <Demographics /> : <><Appointments reception /><details className="receptionist-care"><summary>Check-in and journey operations</summary><ReceptionWorkflowPanel /></details></>;
  if (!content)
    return <PlaceholderPage page={page} workspaceName={workspace.name} />;
  if (role === "/ops" || (role === "/admin" && ["control-room", "traces"].includes(route)))
    return content;
  return (
    <div data-workspace={role} className={`page-stack department-page department-page--${departmentFor(role,route)} route-${route}`}>
      {route!=="doctors"&&<div className="page-heading">
        <DepartmentIcon department={departmentFor(role,route)}/>
        <div>
          <p className="eyebrow">{workspace.name}</p>
          <h1>{page.title}</h1>
          <p className="page-description">
            {role === "/patient" && route === "queue" ? "Check in. Follow your place in the queue." : departmentDescriptions[departmentFor(role,route)]}
          </p>
        </div>
      </div>
      }
      <div className={`department-workspace workspace-${departmentFor(role,route)}`}>{content}</div>
    </div>
  );
}
