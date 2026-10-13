export type Department =
  | "reception"
  | "consultation"
  | "appointments"
  | "waiting"
  | "pharmacy"
  | "billing"
  | "emergency"
  | "records"
  | "control";
const paths: Record<Department, string> = {
  reception:
    "M8 20v-2a4 4 0 0 1 8 0v2M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4 20h16",
  consultation:
    "M5 3v5a5 5 0 0 0 10 0V3M3 3h4M13 3h4M10 13v3a5 5 0 0 0 10 0v-3M20 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4",
  appointments:
    "M7 2v4M17 2v4M3 9h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2M7 13h3v3H7zM14 13h3",
  waiting:
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M17 10a2 2 0 1 0 0-4M2 20v-3a5 5 0 0 1 10 0v3M14 14a4 4 0 0 1 7 3v3M6 20h11",
  pharmacy: "M8 20a5 5 0 0 1-7-7L13 1a5 5 0 0 1 7 7ZM7 7l7 7M15 4l2 2",
  billing: "M5 2h10l4 4v16H5ZM14 2v5h5M8 11h8M8 15h8M8 19h4",
  emergency: "M9 2h6v7h7v6h-7v7H9v-7H2V9h7Z",
  records: "M3 5h6l2 2h10v14H3ZM6 2h10l3 3M7 11h10M7 15h10M7 18h6",
  control: "M3 3h18v13H3ZM8 21h8M12 16v5M5 11h3l2-5 3 8 2-5h4",
};
export function DepartmentIcon({
  department,
  className = "",
}: {
  department: Department;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      className={`department-icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[department]} />
    </svg>
  );
}
export function departmentFor(base: string, path: string): Department {
  if (base === "/ops" || ["control-room", "traces"].includes(path))
    return "control";
  if (path === "appointments") return "appointments";
  if (["queue", "check-in", "waitlist"].includes(path)) return "waiting";
  if (
    base === "/pharmacist" ||
    ["pharmacy", "inventory", "prescriptions"].includes(path)
  )
    return "pharmacy";
  if (base === "/billing" || path === "billing") return "billing";
  if (base === "/emergency" || path === "emergency") return "emergency";
  if (path === "records" || path === "journey" || path === "consultations") return "records";
  if (base === "/doctor" || path === "doctors") return "consultation";
  return "reception";
}
export const departmentNames: Record<Department, string> = {
  reception: "Reception",
  consultation: "Consultation",
  appointments: "Appointments",
  waiting: "Waiting Room",
  pharmacy: "Pharmacy",
  billing: "Billing",
  emergency: "Emergency",
  records: "Medical Records",
  control: "Control Room",
};
export const departmentDescriptions: Record<Department, string> = {
  reception: "Appointments & check-in",
  consultation: "Doctors & patient care",
  appointments: "Book. Manage. Reschedule.",
  waiting: "Live queue & status",
  pharmacy: "Prescriptions & medicines",
  billing: "Invoices & payments",
  emergency: "Urgent care requests",
  records: "Patient history",
  control: "System health & operations",
};
