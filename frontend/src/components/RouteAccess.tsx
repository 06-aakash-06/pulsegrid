import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth, type Role } from "../auth/authContext";
import { EmptyState } from "./EmptyState";

interface RequireRoleProps {
  roles: Role[];
}

export function RequireRole({ roles }: RequireRoleProps) {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "anonymous") {
    return (
      <main className="access-page">
        <EmptyState
          title="Sign in to continue"
          message="A signed-in account is required to open this workspace."
          action={<Link className="button button--small" to="/login" state={{ from: location.pathname }}>Go to sign in</Link>}
        />
      </main>
    );
  }

  if (!roles.some((role) => state.roleHints.includes(role))) {
    return (
      <main className="access-page">
        <EmptyState
          title="This workspace is not available for this account"
          message="Workspace visibility uses role hints from the access token. The owning API remains responsible for every access decision."
          action={<Link className="text-link" to="/">Return to PulseGrid home</Link>}
        />
      </main>
    );
  }

  return <Outlet />;
}

export function NotFoundPage() {
  return (
    <main className="access-page">
      <EmptyState
        title="Page not found"
        message="The address may be incorrect or this page may not be part of the current application foundation."
        action={<Link className="text-link" to="/">Return to PulseGrid home</Link>}
      />
    </main>
  );
}
