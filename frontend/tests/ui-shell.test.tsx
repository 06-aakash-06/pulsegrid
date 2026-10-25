import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/authContext";
import { LoginPage } from "../src/pages/AuthPages";
import { installBrowserMock } from "../dev-mock/browser";

const anonymous = {
  refresh: async () => { throw Error("No session"); },
  login: vi.fn(), register: vi.fn(), logout: vi.fn(),
};
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); localStorage.clear(); });
it.each(["VITE_MOCK_API", "VITE_DEMO_MOCK"])("demo buttons fill both fields under %s", async (flag) => {
  vi.stubEnv("VITE_MOCK_API", "false");vi.stubEnv("VITE_DEMO_MOCK", "false");vi.stubEnv(flag, "true");
  render(<AuthProvider client={anonymous}><MemoryRouter><LoginPage /></MemoryRouter></AuthProvider>);
  await screen.findByLabelText("Email address");
  for (const role of ["Patient","Receptionist","Doctor","Pharmacist","Billing","Emergency","Admin","Ops"]) {
    fireEvent.click(screen.getByRole("button", { name: role }));
    expect(screen.getByLabelText("Email address")).toHaveValue(`${role.toLowerCase()}@mock.test`);
    expect(screen.getByLabelText("Password")).toHaveValue("demo");
  }
});
it("clears persisted demo session as soon as sign-out starts and cannot refresh it", async () => {
  vi.stubGlobal("fetch", vi.fn());
  localStorage.setItem("pulsegrid_mock_session", "1001");
  installBrowserMock();
  const signout = window.fetch("/api/v1/auth/logout", {method:"POST"});
  expect(localStorage.getItem("pulsegrid_mock_session")).toBeNull();
  expect((await signout).status).toBe(204);
  expect((await window.fetch("/api/v1/auth/refresh", {method:"POST"})).status).toBe(401);
});
