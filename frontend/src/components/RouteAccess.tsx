import { Brand } from "./Brand";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth, type Role } from "../auth/authContext";
import { getWorkspaceForRoleHints } from "../navigation/workspaces";
import { EmptyState } from "./EmptyState";

interface RequireRoleProps {
  roles: Role[];
}

export function SessionLoading() {
  return (
    <main className="access-page" role="status" aria-live="polite">
      <div className="session-loading">
        <span aria-hidden="true" className="loading-indicator" />
        <p>Checking your session…</p>
      </div>
    </main>
  );
}

export function RequireRole({ roles }: RequireRoleProps) {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "checking") return <SessionLoading />;

  if (state.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (!roles.some((role) => state.roleHints.includes(role))) {
    const workspace = getWorkspaceForRoleHints(state.roleHints);
    if (workspace) {
      return <Navigate replace to={`${workspace.basePath}/dashboard`} />;
    }
    return (
      <main className="access-page">
        <EmptyState
          title="No workspace is available for this account"
          message="The identity service did not return a role for a configured workspace. Contact an administrator to review the account."
        />
      </main>
    );
  }

  return <Outlet />;
}

export function NotFoundPage() {
  return (
    <main className="access-page">
      <Brand/>
      <EmptyState
        title="Page not found"
        message="The address may be incorrect. Use the hospital directory or return to Reception to continue."
      />
    </main>
  );
}
