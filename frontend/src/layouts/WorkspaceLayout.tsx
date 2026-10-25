import { PageToolsProvider } from "../components/PageTools";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { workspaces, type WorkspaceConfig } from "../navigation/workspaces";
import { useResource } from "../hospital/ui";
import { HospitalHeader } from "../design/HospitalHeader";
import {
  DepartmentIcon,
  departmentFor,
  pageSubtitle,
} from "../design/DepartmentIcon";
export function WorkspaceLayout({ workspace }: { workspace: WorkspaceConfig }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const { state, logout } = useAuth();
  // Load owner-confirmed identity even when entering a department directly.
  useResource(state.status === "authenticated" && state.roleHints.includes("patient")
    ? "/api/v1/patients/me"
    : state.status === "authenticated" && state.roleHints.includes("doctor") ? "/api/v1/doctors/me" : null);
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const route = location.pathname.split("/").at(-1) ?? "dashboard";
  const department = departmentFor(workspace.basePath, route);
  const allowed =
    state.status === "authenticated"
      ? workspaces.filter((w) =>
          w.roles.some((r) => state.roleHints.includes(r)),
        )
      : [];
  async function handleLogout() {
    setLogoutError(null);
    try {
      await logout();
    } catch {
      setLogoutError(
        "The sign-out request could not be confirmed. This browser's access token was cleared, but the identity service did not confirm revocation.",
      );
    }
  }
  useEffect(() => {
    const fromDrawer = menuOpen;
    setMenuOpen(false);
    if (fromDrawer) requestAnimationFrame(() => main.current?.focus());
    window.scrollTo?.({ top: 0, behavior: "instant" });
    sidebar.current?.querySelector<HTMLElement>(".workspace-nav-link--active")?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    if (document.activeElement?.closest(".workspace-nav"))
      main.current?.focus();
  }, [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    sidebar.current?.querySelector<HTMLElement>("a, button")?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        previous?.focus();
      }
      if (e.key === "Tab") {
        const nodes = Array.from(
          sidebar.current?.querySelectorAll<HTMLElement>("a,button") ?? [],
        );
        const first = nodes[0],
          last = nodes.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [menuOpen]);
  return (
    <div className={`workspace-shell environment-${department}`}>
      <a className="skip-link" href="#hospital-main">
        Skip to workspace
      </a>
      <HospitalHeader
        roleLabel={workspace.roleLabel}
        onMenu={() => setMenuOpen(!menuOpen)}
        menuOpen={menuOpen}
        onLogout={() => void handleLogout()}
      />
      <aside
        ref={sidebar}
        className={`workspace-sidebar physical-directory${menuOpen ? " workspace-sidebar--open" : ""}`}
        aria-label="Hospital directory"
        {...(menuOpen ? { role: "dialog", "aria-modal": true } : {})}
      >
        <div className="directory-heading">
          <strong>PULSEGRID</strong>
          <span>GENERAL HOSPITAL</span>
        </div>
        <nav
          aria-label={`${workspace.roleLabel} navigation`}
          className="workspace-nav"
          id="workspace-navigation"
        >
          {workspace.navigation.map((item, index) => {
            const itemDepartment = departmentFor(workspace.basePath, item.path);
            const subtitle = pageSubtitle(workspace.basePath, item.path);
            const subroute = index > 0 && itemDepartment === departmentFor(workspace.basePath, workspace.navigation[index - 1].path);
            return <NavLink key={item.path} end to={`${workspace.basePath}/${item.path}`}
              aria-label={item.label}
              className={({ isActive }) => `workspace-nav-link${isActive ? " workspace-nav-link--active" : ""}${subroute ? " directory-subroute" : ""}`}>
              <span className="directory-number">{String(index + 1).padStart(2, "0")}</span>
              <DepartmentIcon department={itemDepartment} />
              <span className="directory-copy"><strong title={item.label}>{item.label}</strong><small title={subtitle}>{subtitle}</small></span>
              <span className="directory-arrow" aria-hidden="true">→</span>
            </NavLink>;
          })}
        </nav>
        <footer className="directory-footer">
        <div className="directory-help">
          <span aria-hidden="true">ⓘ</span>
          <div>
            <strong>Need help?</strong>
            <small>Use the hospital directory</small>
          </div>
        </div>
        {allowed.length > 1 && (
          <details className="workspace-switcher">
            <summary>Switch workspace</summary>
            {allowed.map((w) => (
              <NavLink key={w.basePath} to={`${w.basePath}/dashboard`}>
                {w.name}
              </NavLink>
            ))}
          </details>
        )}
        <span className="workspace-context">{workspace.name}</span>
        <button
          className="sign-out-button"
          type="button"
          onClick={() => void handleLogout()}
        >
          Sign out
        </button>
        </footer>
      </aside>
      <div className="workspace-main" inert={menuOpen} aria-hidden={menuOpen || undefined}>
        <main
          ref={main}
          tabIndex={-1}
          id="hospital-main"
          className="workspace-content"
        >
          {logoutError && <p role="alert">{logoutError}</p>}
          {state.status === "authenticated" && <PageToolsProvider key={location.pathname}><Outlet /></PageToolsProvider>}
        </main>
      </div>
      {menuOpen && (
        <button
          aria-label="Close navigation menu"
          className="sidebar-scrim"
          onClick={() => setMenuOpen(false)}
          type="button"
        />
      )}
    </div>
  );
}
