import type { ReactNode } from "react";
import { useAuth } from "../../auth/authContext";
import type { Role } from "../../auth/authContext";

export function StaffRoleGate({
  role,
  children,
}: {
  role: Role;
  children: ReactNode;
}) {
  const { state } = useAuth();
  if (state.status === "checking") {
    return <p role="status">Checking your staff session…</p>;
  }
  if (state.status !== "authenticated" || !state.roleHints.includes(role)) {
    return <p role="alert">This workspace requires the {role.replaceAll("_", " ")} role. The owning service still checks current authority for every request.</p>;
  }
  return <>{children}</>;
}
