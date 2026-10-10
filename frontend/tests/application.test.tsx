import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { PulseGridRoutes } from "../src/app/App";
import { AuthProvider, type Role } from "../src/auth/authContext";
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
    refresh: async () => ({ access_token: tokenForRole(role), token_type: "Bearer", expires_in: 600 }),
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
  fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "synthetic@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "test-only-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("application routes", () => {
  it("renders the public landing page and navigates to sign in", () => {
    renderPath("/");
    expect(screen.getByRole("heading", { name: "One place for care and hospital operations." })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Sign in to PulseGrid" }));
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("keeps workspace routes behind a real session", () => {
    renderPath("/patient/dashboard");
    expect(screen.getByRole("heading", { name: "Sign in to continue" })).toBeInTheDocument();
  });

  it("renders the patient registration form without claiming registration succeeded", () => {
    renderPath("/register");
    expect(screen.getByRole("heading", { name: "Create a patient account" })).toBeInTheDocument();
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
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("No service data is connected")).toBeInTheDocument();
  });

  it("supports keyboard-visible responsive navigation interaction", async () => {
    await signInAs("patient");
    const menu = await screen.findByRole("button", { name: "Open navigation menu" });
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(screen.getByRole("link", { name: "Find a doctor" }));
    expect(await screen.findByRole("heading", { name: "Find a doctor" })).toBeInTheDocument();
  });

  it.each(workspaces)("renders each configured page in the $name workspace", async ({ roles: workspaceRoles, pages }) => {
    await signInAs(workspaceRoles[0]);
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    for (const page of pages) {
      fireEvent.click(screen.getByRole("link", { name: page.title }));
      expect(await screen.findByRole("heading", { name: page.title })).toBeInTheDocument();
    }
  });
});
