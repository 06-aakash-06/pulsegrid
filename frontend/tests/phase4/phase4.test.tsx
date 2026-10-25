import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ApiClient, ApiRequestOptions, ApiResponse } from "../../src/api/client";
import {
  AdmissionFeedback,
  AppointmentShortLinkPanel,
  DoctorAutocomplete,
  InsuranceEstimatePanel,
  InsuranceRefreshPanel,
  MedicineAutocomplete,
  ShortLinkLanding,
} from "../../src/phase4";
import type {
  InsuranceEstimate,
  InsuranceEstimatePage,
  InsuranceProviderPage,
  InsuranceRefreshRun,
  InsuranceRunStatus,
  ShortLinkResolution,
  SuggestionPage,
} from "../../src/phase4/contracts";

type Handler = (path: string, options?: ApiRequestOptions) => Promise<ApiResponse<unknown>>;

function response<T>(data: T, status = 200, etag: string | null = null): ApiResponse<T> {
  return { data, status, etag, headers: new Headers(etag ? { ETag: etag } : {}) };
}

function createMockApi(handler: Handler) {
  const calls: { path: string; options?: ApiRequestOptions }[] = [];
  const api: ApiClient = {
    async request<T>(path: string, options?: ApiRequestOptions): Promise<T> {
      calls.push({ path, options });
      return (await handler(path, options)).data as T;
    },
    async requestWithMetadata<T>(path: string, options?: ApiRequestOptions): Promise<ApiResponse<T>> {
      calls.push({ path, options });
      return await handler(path, options) as ApiResponse<T>;
    },
  };
  return { api, calls };
}

function suggestionPage(label: string, kind: "doctor" | "specialty" | "medicine", source: "trie" | "database" = "trie"): SuggestionPage {
  return {
    items: [{ id: "21", kind, label }],
    index_version: 4,
    source,
  };
}

function estimate(overrides: Partial<InsuranceEstimate> = {}): InsuranceEstimate {
  return {
    id: "701",
    invoice_id: "501",
    invoice_version: 6,
    provider_id: "301",
    policy_code: "SYNTHETIC-CARE",
    rules_id: "401",
    rule_revision: 3,
    source_run_id: "601",
    currency: "INR",
    eligible_minor: 125000,
    estimate_minor: 75000,
    calculated_at: "2026-10-12T07:30:00Z",
    freshness_state: "stale",
    is_simulated: true,
    version: 1,
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("Phase 4 autocomplete", () => {
  it("loads doctor suggestions, exposes the source, and selects with keyboard", async () => {
    const { api, calls } = createMockApi(async () => response(suggestionPage("Dr. Asha Rao", "doctor")));
    const onSelect = vi.fn();
    render(<DoctorAutocomplete api={api} roleHints={["patient"]} onSelect={onSelect} />);

    const input = screen.getByRole("combobox", { name: "Doctor" });
    fireEvent.change(input, { target: { value: "Asha" } });
    expect(await screen.findByText("Dr. Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("Indexed suggestions")).toBeInTheDocument();
    expect(calls[0].path).toBe("/api/v1/doctors/autocomplete?prefix=Asha&limit=10&kinds=doctor");
    expect(calls[0].options?.referrerPolicy).toBe("no-referrer");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith({ id: "21", kind: "doctor", label: "Dr. Asha Rao" });
    expect(input).toHaveValue("Dr. Asha Rao");
  });

  it("uses the specialty kind on the frozen doctor autocomplete endpoint", async () => {
    const { api, calls } = createMockApi(async () => response(suggestionPage("Cardiology", "specialty", "database")));
    const onSelect = vi.fn();
    render(<DoctorAutocomplete api={api} roleHints={["patient"]} kind="specialty" onSelect={onSelect} />);

    fireEvent.change(screen.getByRole("combobox", { name: "Specialty" }), { target: { value: "card" } });
    fireEvent.click(await screen.findByRole("option", { name: /Cardiology specialty/ }));
    expect(calls[0].path).toBe("/api/v1/doctors/autocomplete?prefix=card&limit=10&kinds=specialty");
    expect(screen.queryByText("Cardiology")).not.toBeInTheDocument();
    expect(onSelect).toHaveBeenCalledWith({ id: "21", kind: "specialty", label: "Cardiology" });
  });

  it("searches medicines with a limit of ten and shows an empty state", async () => {
    const { api, calls } = createMockApi(async () => response({
      items: [],
      index_version: null,
      source: "database",
    } satisfies SuggestionPage));
    render(<MedicineAutocomplete api={api} roleHints={["patient"]} onSelect={() => undefined} />);

    fireEvent.change(screen.getByRole("combobox", { name: "Medicine" }), { target: { value: "met" } });
    expect(await screen.findByText("No medicine suggestions found.")).toBeInTheDocument();
    expect(screen.getByText("Current database search")).toBeInTheDocument();
    expect(calls[0].path).toBe("/api/v1/pharmacy/medicines/autocomplete?prefix=met&limit=10");
  });

  it("announces loading while a debounced suggestion request is pending", async () => {
    const pending = deferred<ApiResponse<unknown>>();
    const { api, calls } = createMockApi(() => pending.promise);
    render(<MedicineAutocomplete api={api} roleHints={["patient"]} onSelect={() => undefined} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Medicine" }), { target: { value: "med" } });

    expect(await screen.findByText("Searching medicine suggestions…")).toBeInTheDocument();
    await waitFor(() => expect(calls).toHaveLength(1), { timeout: 1000 });
    pending.resolve(response(suggestionPage("Medicine result", "medicine")));
    expect(await screen.findByRole("option", { name: /Medicine result/ })).toBeInTheDocument();
  });

  it("does not display an older response after the query changes", async () => {
    const first = deferred<ApiResponse<unknown>>();
    const second = deferred<ApiResponse<unknown>>();
    const { api, calls } = createMockApi((path) => {
      if (path.includes("prefix=old")) return first.promise;
      return second.promise;
    });
    render(<DoctorAutocomplete api={api} roleHints={["patient"]} onSelect={() => undefined} />);
    const input = screen.getByRole("combobox", { name: "Doctor" });
    fireEvent.change(input, { target: { value: "old" } });
    await waitFor(() => expect(calls).toHaveLength(1), { timeout: 1000 });
    const oldSignal = calls[0].options?.signal;

    fireEvent.change(input, { target: { value: "new" } });
    expect(screen.queryByRole("option", { name: /Old result/ })).not.toBeInTheDocument();
    await waitFor(() => expect(calls).toHaveLength(2), { timeout: 1000 });
    expect(oldSignal?.aborted).toBe(true);

    second.resolve(response(suggestionPage("New result", "doctor")));
    expect(await screen.findByRole("option", { name: /New result/ })).toBeInTheDocument();
    first.resolve(response(suggestionPage("Old result", "doctor")));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("option", { name: /Old result/ })).not.toBeInTheDocument();
  });

  it("shows a clear 429 response and supports explicit retry", async () => {
    let attempt = 0;
    const { api, calls } = createMockApi(async () => {
      attempt += 1;
      if (attempt === 1) throw { status: 429, code: "rate_limited", retryAfterSeconds: 30 };
      return response(suggestionPage("Recovery", "doctor"));
    });
    render(<DoctorAutocomplete api={api} roleHints={["patient"]} onSelect={() => undefined} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Doctor" }), { target: { value: "rec" } });
    expect(await screen.findByText(/rate limited\. Please wait about 30 seconds/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect(await screen.findByText("Recovery")).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });
});

describe("Phase 4 short links", () => {
  it("hides appointment links from other roles without making a request", () => {
    const { api, calls } = createMockApi(async () => response({}));
    render(<AppointmentShortLinkPanel api={api} roleHints={["doctor"]} appointmentId="51" />);
    expect(screen.getByText(/available to the patient and reception roles/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("creates, copies, and revokes a check-in navigation link with frozen headers", async () => {
    const { api, calls } = createMockApi(async (path, options) => {
      if (path.endsWith("/workflow")) {
        return response({ appointment_id: "51", patient_id: "11", doctor_id: "21", state: "booked", version: 3 }, 200, '"3"');
      }
      if (path.endsWith("/short-links") && options?.method === "POST") {
        return response({
          id: "801",
          appointment_id: "51",
          purpose: "check_in",
          short_path: "/s/0123456789012345678901",
          expires_at: "2026-10-13T12:00:00Z",
          version: 1,
        }, 201, '"1"');
      }
      if (path.endsWith("/revoke")) {
        return response({
          id: "801",
          appointment_id: "51",
          purpose: "check_in",
          expires_at: "2026-10-13T12:00:00Z",
          revoked: true,
          version: 2,
        }, 200, '"2"');
      }
      throw new Error("Unexpected API request: " + path);
    });
    const clipboardWrite = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: clipboardWrite },
    });
    render(<AppointmentShortLinkPanel api={api} roleHints={["patient"]} appointmentId="51" />);

    fireEvent.click(await screen.findByRole("button", { name: "Create secure check-in link" }));
    const shortLink = await screen.findByLabelText("Short link");
    expect(shortLink).toHaveValue(window.location.origin + "/s/0123456789012345678901");
    const creation = calls.find((call) => call.options?.method === "POST" && call.path.endsWith("/short-links"));
    expect(creation?.path).toBe("/api/v1/appointments/51/short-links");
    expect(creation?.options?.body).toEqual({ purpose: "check_in" });
    expect(creation?.options?.ifMatch).toBe('"3"');
    expect(creation?.options?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/i);
    expect(screen.getByText(/does not authorize check-in or issue a QR credential/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await waitFor(() => expect(clipboardWrite).toHaveBeenCalledWith(window.location.origin + "/s/0123456789012345678901"));
    fireEvent.click(screen.getByRole("button", { name: "Revoke link" }));
    await waitFor(() => expect(screen.queryByLabelText("Short link")).not.toBeInTheDocument());
    const revoke = calls.find((call) => call.path.endsWith("/revoke"));
    expect(revoke?.options?.ifMatch).toBe('"1"');
    expect(revoke?.options?.method).toBe("POST");
  });

  it("clears the alias from the address before resolving and navigates only to the fixed destination", async () => {
    const alias = "0123456789012345678901";
    window.history.replaceState(null, "", "/short-link#alias=" + alias);
    const { api, calls } = createMockApi(async (_path, options) => {
      expect(options?.referrerPolicy).toBe("no-referrer");
      return response({
        appointment_id: "51",
        purpose: "check_in",
        landing_path: "/patient/check-in#appointment_id=51",
        expires_at: "2026-10-13T12:00:00Z",
      } satisfies ShortLinkResolution);
    });
    const onNavigate = vi.fn();
    render(
      <MemoryRouter>
        <ShortLinkLanding api={api} roleHints={["patient"]} authState="authenticated" onNavigate={onNavigate} />
      </MemoryRouter>,
    );

    expect(window.location.hash).toBe("");
    expect(await screen.findByText("51")).toBeInTheDocument();
    expect(calls[0].path).toBe("/s/" + alias);
    fireEvent.click(screen.getByRole("button", { name: "Continue to appointment" }));
    expect(onNavigate).toHaveBeenCalledWith("/patient/check-in#appointment_id=51");
  });

  it("keeps an anonymous link in memory and does not call the resolution API", () => {
    window.history.replaceState(null, "", "/short-link#alias=0123456789012345678901");
    const { api, calls } = createMockApi(async () => response({}));
    render(
      <MemoryRouter>
        <ShortLinkLanding api={api} roleHints={[]} authState="anonymous" />
      </MemoryRouter>,
    );
    expect(window.location.hash).toBe("");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByText(/held only in this tab’s memory/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });
});

describe("Phase 4 insurance", () => {
  it("shows existing simulated estimate provenance and submits with invoice ETag", async () => {
    const current = estimate();
    const { api, calls } = createMockApi(async (path, options) => {
      if (path === "/api/v1/billing/invoices/501") return response({ id: "501", version: 6 }, 200, '"6"');
      if (path.includes("/insurance-estimates") && options?.method === "POST") {
        return response(estimate({ id: "702", freshness_state: "fresh" }), 201, '"1"');
      }
      if (path.includes("/insurance-estimates")) {
        return response({ items: [current], next_cursor: null } satisfies InsuranceEstimatePage);
      }
      throw new Error("Unexpected API request: " + path);
    });
    render(
      <InsuranceEstimatePanel
        api={api}
        roleHints={["patient"]}
        invoiceId="501"
        providerChoices={[{ id: "301", syntheticSlug: "synthetic-hospital-plan", policyCodes: ["SYNTHETIC-CARE"] }]}
      />,
    );

    expect(await screen.findByText("Source data stale")).toBeInTheDocument();
    expect(screen.getByText(/not an approval or a guarantee of payment/)).toBeInTheDocument();
    expect(screen.getByText("₹750.00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Request estimate" }));
    await screen.findByText("Source data current");

    const request = calls.find((call) => call.options?.method === "POST");
    expect(request?.path).toBe("/api/v1/billing/invoices/501/insurance-estimates");
    expect(request?.options?.body).toEqual({ provider_id: "301", policy_code: "SYNTHETIC-CARE" });
    expect(request?.options?.ifMatch).toBe('"6"');
    expect(request?.options?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("does not fetch patient estimates for an unauthorized role", () => {
    const { api, calls } = createMockApi(async () => response({}));
    render(<InsuranceEstimatePanel api={api} roleHints={["doctor"]} invoiceId="501" />);
    expect(screen.getByText(/available to the patient and Billing staff/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("refreshes only for Billing staff, reports 429 delay, and checks the run status", async () => {
    const providers: InsuranceProviderPage = {
      items: [{ id: "301", synthetic_slug: "synthetic-hospital-plan", last_success_at: null }],
      next_cursor: null,
    };
    const accepted: InsuranceRefreshRun = { run_id: "901", provider_id: "301", state: "pending", version: 1 };
    const complete: InsuranceRunStatus = {
      id: "901",
      provider_id: "301",
      state: "complete",
      pages_processed: 12,
      error_code: null,
      version: 2,
    };
    let refreshAttempt = 0;
    const { api, calls } = createMockApi(async (path, options) => {
      if (path.includes("/insurance/providers") && options?.method !== "POST") return response(providers, 200, '"provider-list-v1"');
      if (path.endsWith("/refresh")) {
        refreshAttempt += 1;
        if (refreshAttempt === 1) throw { status: 429, code: "rate_limited", retryAfterSeconds: 21 };
        return response(accepted, 202);
      }
      if (path.endsWith("/runs/901")) return response(complete);
      throw new Error("Unexpected API request: " + path);
    });
    render(<InsuranceRefreshPanel api={api} roleHints={["billing_staff"]} />);

    fireEvent.click(await screen.findByRole("button", { name: "Update insurance data" }));
    expect(await screen.findByRole("status")).toHaveTextContent("rate limited. Please wait about 21 seconds");
    fireEvent.click(screen.getByRole("button", { name: "Retry refresh request" }));
    expect(await screen.findByText(/Latest run: pending/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check update status" }));
    expect(await screen.findByText(/Latest run: complete · 12 pages processed/)).toBeInTheDocument();

    const refresh = calls.filter((call) => call.path.endsWith("/refresh"));
    expect(refresh).toHaveLength(2);
    expect(refresh[0].options?.ifMatch).toBe('"provider-list-v1"');
    expect(refresh[1].options?.idempotencyKey).toBe(refresh[0].options?.idempotencyKey);
    expect(calls.some((call) => call.path.endsWith("/runs/901"))).toBe(true);
  });

  it("does not reveal or load provider controls for patients", () => {
    const { api, calls } = createMockApi(async () => response({}));
    render(<InsuranceRefreshPanel api={api} roleHints={["patient"]} />);
    expect(screen.getByText(/available to Billing staff and hospital administrators/)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });
});

describe("Phase 4 rate-limit feedback", () => {
  it("formats safe 429 and 503 feedback with optional explicit retry", () => {
    render(
      <div>
        <AdmissionFeedback error={{ status: 429, retryAfterSeconds: 5 }} operationLabel="Search" onRetry={() => undefined} />
        <AdmissionFeedback error={{ status: 503 }} operationLabel="Billing" />
      </div>,
    );
    expect(screen.getByText(/Search is temporarily rate limited. Please wait about 5 seconds/)).toBeInTheDocument();
    expect(screen.getByText(/Billing is temporarily unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("reads a Retry-After header when the injected error retains response metadata", () => {
    render(<AdmissionFeedback error={{ status: 429, headers: new Headers({ "Retry-After": "8" }) }} operationLabel="Search" />);
    expect(screen.getByRole("status")).toHaveTextContent("Please wait about 8 seconds");
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
