import { gsap } from "gsap";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { workspaces, type WorkspaceConfig } from "../navigation/workspaces";
import { useResource } from "../hospital/ui";
import { HospitalHeader } from "../design/HospitalHeader";
import {
  DepartmentIcon,
  departmentFor,
  departmentNames,
  departmentDescriptions,
  pageSubtitle,
} from "../design/DepartmentIcon";
const directoryOrder = [
  "reception",
  "consultation",
  "waiting",
  "pharmacy",
  "billing",
  "emergency",
  "records",
  "control",
  "appointments",
];
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
  const receptionScene = workspace.basePath === "/patient" && route === "dashboard";
  useEffect(() => {
    if (department === "emergency" || receptionScene || !window.matchMedia || !main.current)
      return;
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.fromTo(
        main.current,
        { opacity: 0.8, y: 8 },
        { opacity: 1, y: 0, duration: 0.3, clearProps: "all" },
      );
    });
    return () => media.revert();
  }, [location.pathname, department, receptionScene]);
  const allowed =
    state.status === "authenticated"
      ? workspaces.filter((w) =>
          w.roles.some((r) => state.roleHints.includes(r)),
        )
      : [];
  const referenceMode =
    (workspace.basePath === "/patient" && route === "dashboard") ||
    route === "doctors" || ["appointments","waiting","pharmacy","billing","emergency","records","control"].includes(department);
  // Only the patient workspace has the department-signboard directory; staff keep their own grouped pages.
  const referenceItems =
    referenceMode && workspace.basePath === "/patient"
      ? [
          "dashboard",
          "doctors",
          "queue",
          "pharmacy",
          "billing",
          "emergency",
          "records",
        ].map((path) => ({
          path,
          base: "/patient",
          department: departmentFor("/patient", path),
        }))
      : [];
  const navDepartment = (path: string) =>
    path === "appointments"
      ? "reception"
      : departmentFor(workspace.basePath, path);
  const preferred = [
    "dashboard",
    "doctors",
    "queue",
    "pharmacy",
    "billing",
    "emergency",
    "records",
    "control-room",
  ];
  const groups = directoryOrder
    .map((d) => ({
      department: d,
      items: workspace.navigation
        .filter((p) => navDepartment(p.path) === d)
        .sort(
          (a, b) =>
            (preferred.includes(a.path) ? 0 : 1) -
            (preferred.includes(b.path) ? 0 : 1),
        ),
    }))
    .filter((g) => g.items.length);
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
    <div className={`workspace-shell environment-${department}${referenceMode ? ' reference-departments' : ''}`}>
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
          {referenceItems.length ? (
            <>
              {referenceItems.map((item, index) => {
                const destination = `${item.base}/${item.path}`;
                const aliasActive =
                  location.pathname !== destination &&
                  (department === item.department || (department === "appointments" && item.department === "reception"));
                const content = (
                  <>
                    <span className="directory-number">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <DepartmentIcon department={item.department} />
                    <span className="directory-copy">
                      <strong>{departmentNames[item.department]}</strong>
                      <small>{departmentDescriptions[item.department]}</small>
                    </span>
                    <span className="directory-arrow" aria-hidden="true">
                      →
                    </span>
                  </>
                );
                return aliasActive ? (
                  <Link
                    key={item.department}
                    to={destination}
                    aria-label={departmentNames[item.department]}
                    aria-current="page"
                    className="workspace-nav-link workspace-nav-link--active"
                  >
                    {content}
                  </Link>
                ) : (
                  <NavLink
                    key={item.department}
                    end
                    to={destination}
                    aria-label={departmentNames[item.department]}
                    className={({ isActive }) =>
                      `workspace-nav-link${isActive ? " workspace-nav-link--active" : ""}`
                    }
                  >
                    {content}
                  </NavLink>
                );
              })}
            </>
          ) : (
            <>
              {" "}
              {groups.map((group, groupIndex) => (
                <div className="directory-department" key={group.department}>
                  {group.items.map((item, i) => (
                    <NavLink
                      aria-label={item.label}
                      end
                      key={item.path}
                      to={`${workspace.basePath}/${item.path}`}
                      className={({ isActive }) =>
                        `workspace-nav-link${isActive ? " workspace-nav-link--active" : ""}${i ? " directory-subroute" : ""}`
                      }
                    >
                      {(
                        <>
                          <span className="directory-number">
                            {String(groups.slice(0, groupIndex).reduce((n, g) => n + g.items.length, 0) + i + 1).padStart(2, "0")}
                          </span>
                          <DepartmentIcon
                            department={navDepartment(item.path)}
                          />
                        </>
                      )}
                      <span className="directory-copy">
                        <strong>{item.label}</strong>
                        {!i && <small>{pageSubtitle(workspace.basePath, item.path)}</small>}
                      </span>
                      <span className="directory-arrow" aria-hidden="true">
                        →
                      </span>
                    </NavLink>
                  ))}
                </div>
              ))}
            </>
          )}
        </nav>
        <div className="directory-help">
          <span aria-hidden="true">ⓘ</span>
          <div>
            <strong>Need help?</strong>
            <small>Synthetic hospital prototype</small>
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
        {referenceItems.length > 0 && (
          <details className="reference-directory-tools">
            <summary>More workspace tools</summary>
            {workspace.navigation
              .filter(
                (item) =>
                  !referenceItems.some(
                    (r) =>
                      `${r.base}/${r.path}` ===
                      `${workspace.basePath}/${item.path}`,
                  ),
              )
              .map((item) => (
                <NavLink
                  key={item.path}
                  to={`${workspace.basePath}/${item.path}`}
                >
                  {item.label}
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
      </aside>
      <div className="workspace-main" inert={menuOpen} aria-hidden={menuOpen || undefined}>
        <main
          ref={main}
          tabIndex={-1}
          id="hospital-main"
          className="workspace-content"
        >
          {logoutError && <p role="alert">{logoutError}</p>}
          {state.status === "authenticated" && <Outlet />}
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
