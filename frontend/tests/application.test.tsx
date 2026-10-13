import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PulseGridRoutes } from "../src/app/App";
import { AuthProvider, type Role } from "../src/auth/authContext";
import { ApiError } from "../src/api/client";
import type { AuthApi } from "../src/api/authApi";
import { workspaces } from "../src/navigation/workspaces";

function renderPath(path: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <PulseGridRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
}

function tokenForRole(role: Role): string {
  const payload = btoa(JSON.stringify({ roles: [role] }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `header.${payload}.signature`;
}

function authClientFor(role: Role): AuthApi {
  return {
    login: async () => ({ access_token: tokenForRole(role), token_type: "Bearer", expires_in: 600 }),
    register: async () => ({ id: "1", user_id: "2", display_name: "Synthetic Test", version: 1 }),
    refresh: async () => { throw new ApiError("No saved session.", 401, "unauthorized"); },
    logout: async () => undefined,
  };
}

async function signInAs(role: Role) {
  render(
    <AuthProvider client={authClientFor(role)}>
      <MemoryRouter initialEntries={["/login"]}>
        <PulseGridRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
  fireEvent.change(await screen.findByLabelText("Email address"), { target: { value: "synthetic@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("application routes", () => {
  it("renders the public landing page and navigates to sign in", async () => {
    renderPath("/");
    expect(screen.getByRole("heading", { name: "One place for care and hospital operations." })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Sign in to PulseGrid" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("redirects workspace routes to sign in when no session exists", async () => {
    renderPath("/patient/dashboard");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders the patient registration form without claiming registration succeeded", async () => {
    renderPath("/register");
    expect(await screen.findByRole("heading", { name: "Create a patient account" })).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a not-found state for unknown paths", () => {
    renderPath("/unknown");
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it.each([
    ["patient", "Patient workspace"],
    ["doctor", "Doctor workspace"],
    ["pharmacist", "Pharmacy workspace"],
    ["billing_staff", "Billing workspace"],
    ["emergency_staff", "Emergency workspace"],
    ["hospital_admin", "Administration"],
    ["receptionist", "Reception workspace"],
    ["ops", "Operations control room"],
  ] as const)("renders the %s workspace shell after an identity response", async (role, workspaceName) => {
    await signInAs(role);
    expect(await screen.findAllByText(workspaceName)).not.toHaveLength(0);
    expect(await screen.findByRole("heading", { name: workspaces.find(w=>w.roles.includes(role))!.pages[0].title })).toBeInTheDocument();
  });

  it("supports keyboard-visible responsive navigation interaction", async () => {
    await signInAs("patient");
    const menu = await screen.findByRole("button", { name: "Open navigation menu" });
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("link", { name: "Consultation" }));
    expect(await screen.findByRole("heading", { name: "Consultation" })).toBeInTheDocument();
  });

  it("restores a valid refresh-cookie session and redirects away from login", async () => {
    const restoredClient: AuthApi = {
      ...authClientFor("patient"),
      refresh: async () => ({ access_token: tokenForRole("patient"), token_type: "Bearer", expires_in: 600 }),
    };
    render(
      <AuthProvider client={restoredClient}>
        <MemoryRouter initialEntries={["/login"]}>
          <PulseGridRoutes />
        </MemoryRouter>
      </AuthProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Reception" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("preserves the requested workspace destination through login", async () => {
    render(
      <AuthProvider client={authClientFor("patient")}>
        <MemoryRouter initialEntries={["/patient/appointments?view=upcoming"]}>
          <PulseGridRoutes />
        </MemoryRouter>
      </AuthProvider>,
    );

    fireEvent.change(await screen.findByLabelText("Email address"), { target: { value: "synthetic@example.test" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Appointments", level: 1 })).toBeInTheDocument();
  });

  it.each(workspaces)("renders each configured page in the $name workspace", async ({ roles: workspaceRoles, pages }) => {
    await signInAs(workspaceRoles[0]);
    const initialHeading = workspaces.find(w=>w.roles.includes(workspaceRoles[0]))!.pages[0].title;
    expect(await screen.findByRole("heading", { name: initialHeading })).toBeInTheDocument();
    for (const page of pages) {
      const directory=screen.getByRole("complementary",{name:"Hospital directory"});
      const destination=within(directory).getAllByRole("link").find(link=>link.getAttribute("href")===`${workspaces.find(w=>w.roles.includes(workspaceRoles[0]))!.basePath}/${page.path}`);
      expect(destination).toBeDefined();
      fireEvent.click(destination!);
      expect(await screen.findByRole("heading", { name: page.title, level: 1 })).toBeInTheDocument();
    }
  });
});

describe("Phase 4 authentication handoff", () => {
  it.each(["patient", "receptionist"] as Role[])("returns %s to the fixed short-link route", async role => {
    render(<AuthProvider client={authClientFor(role)}><MemoryRouter initialEntries={[{pathname:"/login",state:{from:"/short-link"}}]}><PulseGridRoutes /></MemoryRouter></AuthProvider>);
    fireEvent.change(await screen.findByLabelText("Email address"),{target:{value:"synthetic@example.test"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"test-only-password"}});
    fireEvent.click(screen.getByRole("button",{name:"Sign in"}));
    expect(await screen.findByRole("heading",{name:"Secure appointment link"})).toBeInTheDocument();
    expect(screen.queryByRole("heading",{name:"Reception"})).not.toBeInTheDocument();
  });
  it("shows Retry-After on identity admission rejection", async () => {
    const client={...authClientFor("patient"),login:async()=>{throw new ApiError("Rate limited.",429,"rate_limited",undefined,7)}};
    render(<AuthProvider client={client}><MemoryRouter initialEntries={["/login"]}><PulseGridRoutes /></MemoryRouter></AuthProvider>);
    fireEvent.change(await screen.findByLabelText("Email address"),{target:{value:"synthetic@example.test"}});
    fireEvent.change(screen.getByLabelText("Password"),{target:{value:"test-only-password"}});
    fireEvent.click(screen.getByRole("button",{name:"Sign in"}));
    expect(await screen.findByText(/Wait 7 seconds before retrying/)).toBeInTheDocument();
  });
});
