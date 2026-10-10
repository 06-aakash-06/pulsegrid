import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { EmptyState } from "../components/EmptyState";
import { SessionLoading } from "../components/RouteAccess";
import { getWorkspaceForPath, getWorkspaceForRoleHints } from "../navigation/workspaces";

interface RedirectLocation {
  pathname?: unknown;
  search?: unknown;
  hash?: unknown;
}

function intendedPath(state: unknown): string | undefined {
  if (typeof state !== "object" || state === null || !("from" in state)) return undefined;
  const from = state.from;
  if (typeof from === "string") {
    return from.startsWith("/") && !from.startsWith("//") ? from : undefined;
  }
  if (typeof from !== "object" || from === null) return undefined;
  const location = from as RedirectLocation;
  if (typeof location.pathname !== "string") return undefined;
  if (!location.pathname.startsWith("/") || location.pathname.startsWith("//")) return undefined;
  const search = typeof location.search === "string" ? location.search : "";
  const hash = typeof location.hash === "string" ? location.hash : "";
  return `${location.pathname}${search}${hash}`;
}

export function AuthLayout() {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "checking") return <SessionLoading />;
  if (state.status === "authenticated") {
    const path = intendedPath(location.state);
    const intendedWorkspace = path ? getWorkspaceForPath(path.split(/[?#]/, 1)[0], state.roleHints) : undefined;
    const workspace = intendedWorkspace ?? getWorkspaceForRoleHints(state.roleHints);
    if (!workspace) {
      return (
        <main className="access-page">
          <EmptyState
            title="No workspace is available for this account"
            message="The identity service did not return a role for a configured workspace. Contact an administrator to review the account."
          />
        </main>
      );
    }
    return <Navigate replace to={intendedWorkspace && path ? path : `${workspace.basePath}/dashboard`} />;
  }

  return (
    <div className="auth-route-layout">
      <Outlet />
    </div>
  );
}
