import { gsap } from "gsap";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { workspaces, type WorkspaceConfig } from "../navigation/workspaces";
import { HospitalHeader } from "../design/HospitalHeader";
import {
  DepartmentIcon,
  departmentFor,
  departmentNames,
  departmentDescriptions,
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
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const route = location.pathname.split("/").at(-1) ?? "dashboard";
  const department = departmentFor(workspace.basePath, route);
  useEffect(() => {
    if (department === "emergency" || !window.matchMedia || !main.current)
      return;
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.fromTo(
        main.current,
        { opacity: 0.8, y: 8 },
        { opacity: 1, y: 0, duration: 0.35, clearProps: "all" },
      );
    });
    return () => media.revert();
  }, [location.pathname, department]);
  const allowed =
    state.status === "authenticated"
      ? workspaces.filter((w) =>
          w.roles.some((r) => state.roleHints.includes(r)),
        )
      : [];
  const referenceMode =
    (workspace.basePath === "/patient" && route === "dashboard") ||
    route === "doctors" || ["appointments","waiting","pharmacy","billing","emergency","records","control"].includes(department);
  const patientWorkspace = allowed.find((w) => w.basePath === "/patient");
  const referenceItems =
    referenceMode && patientWorkspace
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
          department: navDepartmentForPatient(path),
        }))
      : [];
  function navDepartmentForPatient(path: string) {
    return departmentFor("/patient", path);
  }
  if (referenceMode && allowed.some((w) => w.basePath === "/admin")) {
    referenceItems.push({
      path: "control-room",
      base: "/admin",
      department: "control",
    });
    if (workspace.basePath === "/admin") {
      const consultation = referenceItems.find(
        (i) => i.department === "consultation",
      );
      if (consultation) consultation.base = "/admin";
    }
  }
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
    setMenuOpen(false);
    window.scrollTo?.({ top: 0, behavior: "instant" });
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
              {referenceItems.map((item) => (
                <NavLink
                  key={item.department}
                  end
                  to={`${item.base}/${item.path}`}
                  aria-label={departmentNames[item.department]}
                  className={({ isActive }) =>
                    `workspace-nav-link${isActive || department === item.department || (department === "appointments" && item.department === "reception") ? " workspace-nav-link--active" : ""}`
                  }
                >
                  <span className="directory-number">
                    {String(
                      directoryOrder.indexOf(item.department) + 1,
                    ).padStart(2, "0")}
                  </span>
                  <DepartmentIcon department={item.department} />
                  <span className="directory-copy">
                    <strong>{departmentNames[item.department]}</strong>
                    <small>{departmentDescriptions[item.department]}</small>
                  </span>
                  <span className="directory-arrow" aria-hidden="true">
                    →
                  </span>
                </NavLink>
              ))}
            </>
          ) : (
            <>
              {" "}
              {groups.map((group) => (
                <div className="directory-department" key={group.department}>
                  {group.items.map((item, i) => (
                    <NavLink
                      aria-label={item.label}
                      end
                      key={item.path}
                      to={`${workspace.basePath}/${item.path}`}
                      onClick={() => setMenuOpen(false)}
                      className={({ isActive }) =>
                        `workspace-nav-link${isActive ? " workspace-nav-link--active" : ""}${i ? " directory-subroute" : ""}`
                      }
                    >
                      {!i && (
                        <>
                          <span className="directory-number">
                            {String(
                              directoryOrder.indexOf(group.department) + 1,
                            ).padStart(2, "0")}
                          </span>
                          <DepartmentIcon
                            department={navDepartment(item.path)}
                          />
                        </>
                      )}
                      <span className="directory-copy">
                        <strong>
                          {i
                            ? item.label
                            : departmentNames[navDepartment(item.path)]}
                        </strong>
                        <small>
                          {i
                            ? ""
                            : departmentDescriptions[navDepartment(item.path)]}
                        </small>
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
      <div className="workspace-main">
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
