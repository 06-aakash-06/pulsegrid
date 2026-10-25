import { DepartmentIcon, departmentFor, pageSubtitle } from "../design/DepartmentIcon";
import { PatientWaitlistPage, PatientCheckinPage, PatientQueuePage, PatientJourneyPage } from "../advanced/patient";
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
import { MedicineCatalog, PatientPharmacy, PharmacistPharmacy } from "./pharmacy";
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
  const title = role === "/pharmacist" && route === "dashboard" ? "Pharmacy" : page.title;
  const pharmacyRoom = (role === "/patient" && route === "pharmacy") || role === "/pharmacist";
  const subtitle = pageSubtitle(role, route);
  const signed =
    (role === "/patient" && ["records", "billing", "emergency", "appointments"].includes(route)) ||
    (role === "/receptionist" && route === "appointments") ||
    (role === "/doctor" && route === "consultations") ||
    (role === "/billing" && ["dashboard", "invoices", "payments"].includes(route)) ||
    role === "/emergency";
  let content;
  if (role === "/patient") {
    if (route === "dashboard") content = <PatientDashboard />;
    if (route === "doctors") content = <DoctorDirectory />;
    if (route === "appointments") content = <Appointments title={title} subtitle={subtitle} />;
    if (route === "waitlist") content = <><PatientWaitlistPage /><WaitlistOffers /></>;
    if (route === "check-in") content = <PatientCheckinPage />;
    if (route === "queue") content = <PatientQueuePage />;
    if (route === "journey") content = <PatientJourneyPage />;
    if (route === "records") content = <RecordsPage title={title} subtitle={subtitle} />;
    if (route === "prescriptions") content = <Prescriptions />;
    if (route === "pharmacy") content = <PatientPharmacy title={title} workspaceName={workspace.name} />;
    if (route === "billing") content = <BillingPage title={title} subtitle={subtitle} />;
    if (route === "emergency") content = <EmergencyPage title={title} subtitle={subtitle} />;
  }
  if (role === "/doctor") {
    if (route === "dashboard") content = <DoctorDashboard />;
    if (route === "consultations") content = <Consultations doctor title={title} subtitle="Consultation documents" />;
    if (route === "queue") content = <DoctorQueuePage />;
    if (route === "prescriptions")
      content = (
        <>
          <Prescriptions doctor />
          <MedicineCatalog />
        </>
      );
  }
  if (role === "/pharmacist") {
    if (route === "inventory" || route === "dashboard") content = <PharmacistPharmacy title={title} workspaceName={workspace.name} />;
    if (route === "prescriptions") content = <StaffFulfillmentPanel title={title} workspaceName={workspace.name} />;
  }
  if (
    role === "/billing" &&
    ["dashboard", "invoices", "payments"].includes(route)
  )
    content = <BillingPage staff title={title} subtitle={subtitle} />;
  if (role === "/emergency") content = <EmergencyPage staff title={title} subtitle={subtitle} />;
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
      route === "dashboard" ? <Demographics /> : <><Appointments reception title={title} subtitle={subtitle} /><details className="receptionist-care"><summary>Check-in and journey operations</summary><ReceptionWorkflowPanel /></details></>;
  if (!content)
    return <PlaceholderPage page={page} workspaceName={workspace.name} />;
  if (role === "/ops" || (role === "/admin" && ["control-room", "traces"].includes(route)))
    return content;
  return (
    <div data-workspace={role} className={`page-stack department-page department-page--${departmentFor(role,route)} route-${route}`}>
      {route!=="doctors"&&!pharmacyRoom&&!signed&&<div className="page-heading">
        <DepartmentIcon department={departmentFor(role,route)}/>
        <div>
          <p className="eyebrow">{workspace.name}</p>
          <h1>{title}</h1>
          <p className="page-description">
            {role === "/patient" && route === "queue" ? "Check in. Follow your place in the queue." : role === "/patient" && route === "check-in" ? "Check in for today's visit." : subtitle}
          </p>
        </div>
      </div>
      }
      <div className={`department-workspace workspace-${departmentFor(role,route)}`}>{content}</div>
    </div>
  );
}
