import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PulseGridRoutes } from "../src/app/App";
import { createAuthApi } from "../src/api/authApi";
import { createApiClient } from "../src/api/client";
import { AuthProvider, useAuth, type Role } from "../src/auth/authContext";
import { useState } from "react";

type FetchHandler = (path: string, init: RequestInit) => Response | Promise<Response>;

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function errorResponse(status: number, code: string, message: string): Response {
  return jsonResponse({ error: { code, message, request_id: "00000000-0000-4000-8000-000000000001" } }, status);
}

function tokenFor(role: Role, subject = "12345"): string {
  const payload = btoa(JSON.stringify({ sub: subject, roles: [role] }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `header.${payload}.signature`;
}

function tokenSet(role: Role, expiresIn = 600) {
  return { access_token: tokenFor(role), token_type: "Bearer" as const, expires_in: expiresIn };
}

function tokenSetFor(accessToken: string, expiresIn = 600) {
  return { access_token: accessToken, token_type: "Bearer" as const, expires_in: expiresIn };
}

function setupApplication(
  handler: FetchHandler,
  initialPath = "/login",
  options: { patientServiceReady?: boolean } = {},
) {
  const fetcher = vi.fn<typeof fetch>(async (input, init = {}) => {
    const path = new URL(String(input), "http://pulsegrid.test").pathname;
    if (path === "/api/v1/patients/health/ready" && options.patientServiceReady !== false) {
      return jsonResponse({ status: "ready", service: "patient", application: "ready" });
    }
    return handler(path, init);
  });
  const rawClient = createApiClient({ fetcher });
  const client = createAuthApi(rawClient, () => ({ "X-CSRF-Test": "provided-by-host" }));
  const view = render(
    <AuthProvider client={client} apiClient={rawClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <PulseGridRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
  return { fetcher, rawClient, view };
}

function anonymousHandler(path: string): Response {
  if (path === "/api/v1/auth/refresh") {
    return errorResponse(401, "unauthorized", "No active session.");
  }
  return errorResponse(404, "not_found", "Not found.");
}

function fillLogin(email = "patient@example.test", password = "long synthetic passphrase") {
  fireEvent.change(screen.getByLabelText("Email address"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

function fillRegistration() {
  fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Synthetic Patient" } });
  fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "patient@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "long synthetic passphrase" } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "long synthetic passphrase" } });
}

describe("authentication pages", () => {
  afterEach(() => vi.useRealTimers());

  it("validates registration fields and password confirmation before sending", async () => {
    const { fetcher } = setupApplication(anonymousHandler, "/register");
    await screen.findByRole("heading", { name: "Create a patient account" });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Enter your display name.")).toBeInTheDocument();
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter a password.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "provided-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/register"))).toHaveLength(0);
  });

  it("submits documented registration fields and shows success only after a 201 response", async () => {
    let finishRegistration!: (response: Response) => void;
    const registrationResponse = new Promise<Response>((resolve) => { finishRegistration = resolve; });
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      if (path === "/api/v1/auth/register") return registrationResponse;
      return errorResponse(404, "not_found", "Not found.");
    }, "/register");

    await screen.findByRole("heading", { name: "Create a patient account" });
    fillRegistration();
    fireEvent.change(screen.getByLabelText("Date of birth Optional"), { target: { value: "2000-01-02" } });
    fireEvent.change(screen.getByLabelText("Contact number or email Optional"), { target: { value: "synthetic@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled();
    let registrationCall: typeof fetcher.mock.calls[number] | undefined;
    await waitFor(() => {
      registrationCall = fetcher.mock.calls.find(([url]) => String(url).includes("/auth/register"));
      expect(registrationCall).toBeDefined();
    });
    expect(registrationCall).toBeDefined();
    const requestInit = registrationCall?.[1] as RequestInit;
    expect(JSON.parse(String(requestInit.body))).toEqual({
      display_name: "Synthetic Patient",
      email: "patient@example.test",
      password: "long synthetic passphrase",
      date_of_birth: "2000-01-02",
      synthetic_contact: "synthetic@example.test",
    });
    expect(requestInit.credentials).toBe("omit");
    finishRegistration(jsonResponse({
      id: "1001",
      user_id: "1002",
      display_name: "Synthetic Patient",
      date_of_birth: "2000-01-02",
      synthetic_contact: "synthetic@example.test",
      version: 1,
    }, 201));

    expect(await screen.findByRole("status")).toHaveTextContent("Your registration was accepted by the identity service.");
    expect(fetcher.mock.calls.some(([url]) => String(url).includes("/auth/login"))).toBe(false);
  });

  it("handles duplicate-account responses without exposing a misleading success", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      if (path === "/api/v1/auth/register") return errorResponse(409, "email_unavailable", "Email unavailable.");
      return errorResponse(404, "not_found", "Not found.");
    }, "/register");
    await screen.findByRole("heading", { name: "Create a patient account" });
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An account with this email address may already exist.");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/register"))).toHaveLength(1);
  });

  it("explains when a static demo deployment has no Patient service and does not submit credentials", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      return new Response("<!doctype html><title>Page not found</title>", {
        status: 200,
        headers: { "content-type": "text/html" },
      });
    }, "/register", { patientServiceReady: false });
    await screen.findByRole("heading", { name: "Create a patient account" });
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "New accounts are unavailable on this deployment because the Patient service is not connected.",
    );
    expect(fetcher.mock.calls.some(([url]) => String(url).includes("/auth/register"))).toBe(false);
  });

  it("handles registration network errors", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      if (path === "/api/v1/auth/register") throw new TypeError("offline");
      return errorResponse(404, "not_found", "Not found.");
    }, "/register");
    await screen.findByRole("heading", { name: "Create a patient account" });
    fillRegistration();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach the identity service.");
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/register"))).toHaveLength(1);
  });

  it("keeps registration identifiers on retry and changes them when the form changes", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path.endsWith("/register")) throw new TypeError("offline");
      return anonymousHandler(path);
    }, "/register");
    await screen.findByRole("heading", { name: "Create a patient account" });
    fillRegistration();
    const submit = async () => {
      fireEvent.click(screen.getByRole("button", { name: "Create account" }));
      await screen.findByRole("alert");
      await waitFor(() => expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled());
    };
    await submit();
    await submit();
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New Synthetic Patient" } });
    await submit();
    const calls = fetcher.mock.calls.filter(([url]) => String(url).endsWith("/register"));
    expect(calls).toHaveLength(3);
    const headers = calls.map(([, init]) => new Headers(init?.headers));
    for (const field of ["Idempotency-Key", "X-Anonymous-Command-ID"]) {
      expect(headers[0].get(field)).toBe(headers[1].get(field));
      expect(headers[0].get(field)).not.toBe(headers[2].get(field));
    }
  });

  it("validates login, supports password visibility, and sends credentials to the documented endpoint", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      if (path === "/api/v1/auth/login") return jsonResponse(tokenSet("patient"));
      return errorResponse(404, "not_found", "Not found.");
    });
    await screen.findByRole("heading", { name: "Sign in" });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/login"))).toHaveLength(0);

    fillLogin();
    const password = screen.getByLabelText("Password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Reception" })).toBeInTheDocument();
    const loginCall = fetcher.mock.calls.find(([url]) => String(url).includes("/auth/login"));
    expect(loginCall?.[0]).toBe("/api/v1/auth/login");
    const loginInit = loginCall?.[1] as RequestInit;
    expect(JSON.parse(String(loginInit.body))).toEqual({ email: "patient@example.test", password: "long synthetic passphrase" });
    expect(loginInit.credentials).toBe("include");
    expect(new Headers(loginInit.headers).get("X-CSRF-Test")).toBe("provided-by-host");
  });

  it("shows a generic incorrect-credentials message and handles login network failure", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      if (path === "/api/v1/auth/login") return errorResponse(401, "unauthorized", "Credentials not accepted.");
      return errorResponse(404, "not_found", "Not found.");
    });
    await screen.findByRole("heading", { name: "Sign in" });
    fillLogin();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The email address or password is incorrect.");

    fetcher.mockImplementation(async (input) => {
      const path = new URL(String(input), "http://pulsegrid.test").pathname;
      if (path === "/api/v1/auth/login") throw new TypeError("offline");
      if (path === "/api/v1/auth/refresh") return errorResponse(401, "unauthorized", "No session.");
      return errorResponse(404, "not_found", "Not found.");
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach the identity service.");
  });
});

describe("session lifecycle and protected API requests", () => {
  it("restores a valid cookie session and redirects unauthenticated protected routes to login", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return jsonResponse(tokenSet("doctor"));
      return errorResponse(404, "not_found", "Not found.");
    }, "/doctor/dashboard");
    expect(await screen.findByRole("heading", { name: "Consultation" })).toBeInTheDocument();
    const restorationCall = fetcher.mock.calls.find(([url]) => String(url).includes("/auth/refresh"));
    const restorationInit = restorationCall?.[1] as RequestInit;
    expect(restorationInit.credentials).toBe("include");
    expect(new Headers(restorationInit.headers).get("X-CSRF-Test")).toBe("provided-by-host");

    const anonymous = setupApplication(anonymousHandler, "/patient/appointments");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    anonymous.view.unmount();
  });

  it("clears local authentication after logout", async () => {
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return jsonResponse(tokenSet("patient"));
      if (path === "/api/v1/auth/logout") return new Response(null, { status: 204 });
      return errorResponse(404, "not_found", "Not found.");
    }, "/patient/dashboard");
    await screen.findByRole("heading", { name: "Reception" });
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    const logoutCall = fetcher.mock.calls.find(([url]) => String(url).includes("/auth/logout"));
    const logoutInit = logoutCall?.[1] as RequestInit;
    expect(logoutInit.credentials).toBe("include");
    expect(new Headers(logoutInit.headers).get("X-CSRF-Test")).toBe("provided-by-host");
  });

  it("clears local authentication after a failed logout response", async () => {
    setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") return jsonResponse(tokenSet("patient"));
      if (path === "/api/v1/auth/logout") return errorResponse(503, "unavailable", "Sign out is unavailable.");
      return errorResponse(404, "not_found", "Not found.");
    }, "/patient/dashboard");
    await screen.findByRole("heading", { name: "Reception" });
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("keeps the session anonymous when startup refresh fails", async () => {
    setupApplication(anonymousHandler, "/patient/dashboard");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Reception" })).not.toBeInTheDocument();
  });

  it("refreshes an expired access token and maintains the workspace session", async () => {
    let refreshCount = 0;
    const { fetcher } = setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") {
        refreshCount += 1;
        return refreshCount === 1
          ? errorResponse(401, "unauthorized", "No session.")
          : jsonResponse(tokenSet("patient", 600));
      }
      if (path === "/api/v1/auth/login") return jsonResponse(tokenSet("patient", 1));
      return errorResponse(404, "not_found", "Not found.");
    });
    await screen.findByRole("heading", { name: "Sign in" });
    fillLogin();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("heading", { name: "Reception" });

    await waitFor(() => expect(refreshCount).toBe(2), { timeout: 2500 });
    expect(screen.getByRole("heading", { name: "Reception" })).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes("/auth/refresh"))).toHaveLength(2);
  });

  it("returns to sign in when refresh fails after access-token expiry", async () => {
    let refreshCount = 0;
    setupApplication((path) => {
      if (path === "/api/v1/auth/refresh") {
        refreshCount += 1;
        return errorResponse(401, "unauthorized", "Refresh session expired.");
      }
      if (path === "/api/v1/auth/login") return jsonResponse(tokenSet("patient", 1));
      return errorResponse(404, "not_found", "Not found.");
    });
    await screen.findByRole("heading", { name: "Sign in" });
    fillLogin();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("heading", { name: "Reception" });

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(refreshCount).toBe(2);
    expect(screen.queryByRole("heading", { name: "Reception" })).not.toBeInTheDocument();
  });

  it("shares one refresh across simultaneous 401 responses and retries each request once", async () => {
    let refreshCount = 0;
    let releaseRefresh!: (response: Response) => void;
    const pendingRefresh = new Promise<Response>((resolve) => { releaseRefresh = resolve; });
    const expiredAccessToken = tokenFor("patient", "expired-user");
    const freshAccessToken = tokenFor("patient", "fresh-user");
    const fetcher = vi.fn<typeof fetch>(async (input, init = {}) => {
      const path = new URL(String(input), "http://pulsegrid.test").pathname;
      const headers = new Headers(init.headers);
      if (path === "/api/v1/auth/refresh") {
        refreshCount += 1;
        if (refreshCount === 1) return jsonResponse(tokenSetFor(expiredAccessToken));
        return pendingRefresh;
      }
      if (path === "/api/v1/private") {
        return headers.get("Authorization") === `Bearer ${freshAccessToken}`
          ? jsonResponse({ ok: true })
          : errorResponse(401, "unauthorized", "Expired access token.");
      }
      return errorResponse(404, "not_found", "Not found.");
    });
    const rawClient = createApiClient({ fetcher });
    const auth = createAuthApi(rawClient, () => ({ "X-CSRF-Test": "provided-by-host" }));

    function ConcurrentRequests() {
      const { api } = useAuth();
      const [result, setResult] = useState("idle");
      return (
        <>
          <button
            onClick={() => {
              setResult("pending");
              void Promise.all([
                api.request("/api/v1/private"),
                api.request("/api/v1/private"),
              ]).then(() => setResult("complete"));
            }}
            type="button"
          >
            Request twice
          </button>
          <p role="status">{result}</p>
        </>
      );
    }

    render(
      <AuthProvider client={auth} apiClient={rawClient}>
        <ConcurrentRequests />
      </AuthProvider>,
    );
    await screen.findByRole("button", { name: "Request twice" });
    fireEvent.click(screen.getByRole("button", { name: "Request twice" }));
    await waitFor(() => expect(refreshCount).toBe(2));
    expect(refreshCount).toBe(2);

    releaseRefresh(jsonResponse(tokenSetFor(freshAccessToken)));
    expect(await screen.findByText("complete")).toBeInTheDocument();
    const protectedCalls = fetcher.mock.calls.filter(([url]) => String(url).includes("/api/v1/private"));
    expect(protectedCalls).toHaveLength(4);
    expect(protectedCalls.filter(([, init]) => new Headers(init?.headers).get("Authorization") === `Bearer ${freshAccessToken}`)).toHaveLength(2);
  });
});
