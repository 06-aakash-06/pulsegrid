import { useState, type KeyboardEvent } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Brand } from "../components/Brand";
import { useAuth } from "../auth/authContext";
import type { WorkspaceConfig } from "../navigation/workspaces";

interface WorkspaceLayoutProps {
  workspace: WorkspaceConfig;
}

export function WorkspaceLayout({ workspace }: WorkspaceLayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const { state, logout } = useAuth();

  async function handleLogout() {
    setLogoutError(null);
    try {
      await logout();
    } catch {
      setLogoutError("The sign-out request could not be confirmed. This browser's access token was cleared, but the identity service did not confirm revocation.");
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && menuOpen) setMenuOpen(false);
  }

  return (
    <div className="workspace-shell" onKeyDown={handleKeyDown}>
      <aside className={`workspace-sidebar${menuOpen ? " workspace-sidebar--open" : ""}`}>
        <div className="sidebar-top"><Brand compact /></div>
        <div className="workspace-identity">
          <span className="workspace-identity-label">Workspace</span>
          <strong>{workspace.name}</strong>
        </div>
        <nav aria-label={`${workspace.roleLabel} navigation`} className="workspace-nav" id="workspace-navigation">
          <span className="nav-section-label">Menu</span>
          {workspace.navigation.map((item) => (
            <NavLink
              className={({ isActive }) => `workspace-nav-link${isActive ? " workspace-nav-link--active" : ""}`}
              end
              key={item.path}
              onClick={() => setMenuOpen(false)}
              to={`${workspace.basePath}/${item.path}`}
            >
              <span aria-hidden="true" className="nav-link-mark" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-status"><span aria-hidden="true" />API connection pending</div>
          <button className="sign-out-button" onClick={handleLogout} type="button">Sign out</button>
        </div>
      </aside>

      <div className="workspace-main">
        <header className="workspace-topbar">
          <button
            aria-expanded={menuOpen}
            aria-controls="workspace-navigation"
            aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
            className="menu-toggle"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            <span /><span /><span />
          </button>
          <p className="topbar-title">{workspace.name}</p>
          <div className="topbar-session">
            <span className="role-chip">{workspace.roleLabel}</span>
          </div>
        </header>
        <main className="workspace-content">
          {logoutError ? <p className="form-message form-message--error" role="alert">{logoutError}</p> : null}
          {state.status === "authenticated" ? <Outlet /> : null}
        </main>
      </div>
      {menuOpen ? <button aria-label="Close navigation menu" className="sidebar-scrim" onClick={() => setMenuOpen(false)} type="button" /> : null}
    </div>
  );
}
