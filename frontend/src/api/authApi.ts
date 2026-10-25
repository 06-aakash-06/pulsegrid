import {
  ApiConfigurationError,
  ApiError,
  apiClient,
  type ApiClient,
} from "./client";

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegistrationInput extends LoginInput {
  display_name: string;
  date_of_birth?: string;
  synthetic_contact?: string;
}

export interface TokenSet {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
}

export interface PatientProfile {
  id: string;
  user_id: string;
  display_name: string;
  date_of_birth?: string;
  synthetic_contact?: string;
  version: number;
}

export interface RegistrationAttempt {
  idempotencyKey: string;
  anonymousCommandId: string;
}
export function createRegistrationAttempt(): RegistrationAttempt {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return {
    idempotencyKey: crypto.randomUUID(),
    anonymousCommandId: btoa(String.fromCharCode(...bytes))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""),
  };
}
export type CsrfHeadersProvider = () => HeadersInit | Promise<HeadersInit>;
export interface AuthApi {
  login(input: LoginInput, signal?: AbortSignal): Promise<TokenSet>;
  register(input: RegistrationInput, signal?: AbortSignal, attempt?: RegistrationAttempt): Promise<PatientProfile>;
  refresh(signal?: AbortSignal): Promise<TokenSet>;
  logout(signal?: AbortSignal): Promise<void>;
}

/** Fetch the signed token from the response, never from the HttpOnly cookie. */
export function createCsrfHeadersProvider(client: ApiClient): CsrfHeadersProvider {
  return async () => {
    const result = await client.request<{ csrf_token: string; header_name: string; expires_in: number }>(
      "/api/v1/auth/csrf", { credentials: "include", referrerPolicy: "origin" },
    );
    if (!result || result.header_name !== "X-CSRF-Token" ||
        typeof result.csrf_token !== "string" || !result.csrf_token ||
        !Number.isInteger(result.expires_in) || result.expires_in <= 0) {
      throw new ApiConfigurationError("The identity service returned invalid CSRF protection.");
    }
    return { "X-CSRF-Token": result.csrf_token };
  };
}

export function createAuthApi(
  client: ApiClient = apiClient,
  getCsrfHeaders?: CsrfHeadersProvider,
): AuthApi {
  const requiredCsrfHeaders = async (): Promise<HeadersInit> => {
    if (!getCsrfHeaders) {
      throw new ApiConfigurationError("Sign-in requires a configured CSRF header provider.");
    }
    return getCsrfHeaders();
  };
  // Pair CSRF initialization and mutation; serialize cookie rotation across same-origin tabs.
  let flight: Promise<unknown> = Promise.resolve();
  const serialized = <T,>(operation: () => Promise<T>): Promise<T> => {
    const run = () => typeof navigator !== "undefined" && navigator.locks
      ? navigator.locks.request("pulsegrid-auth-cookie", operation)
      : operation();
    const result = flight.then(run, run);
    flight = result.catch(() => undefined);
    return result;
  };
  const requirePatientService = async (signal?: AbortSignal): Promise<void> => {
    try {
      const readiness = await client.request<{
        status?: unknown;
        service?: unknown;
        application?: unknown;
      }>("/api/v1/patients/health/ready", { signal });
      if (
        readiness?.status !== "ready" ||
        readiness.service !== "patient" ||
        readiness.application !== "ready"
      ) {
        throw new ApiError(
          "Patient account registration is unavailable because the Patient service is not ready.",
          503,
          "identity_service_unavailable",
        );
      }
    } catch (error) {
      if (signal?.aborted) throw error;
      if (error instanceof ApiError && (error.code === "network_error" || error.code === "identity_service_unavailable")) {
        throw error;
      }
      throw new ApiError(
        "Patient account registration is unavailable because this deployment is not connected to the Patient service.",
        503,
        "identity_service_unavailable",
      );
    }
  };
  return {
    login: (input, signal) => serialized(async () => client.request<TokenSet>("/api/v1/auth/login", {
      method: "POST",
      body: input,
      headers: await requiredCsrfHeaders(),
      credentials: "include",
      signal,
    })),
    async register(input, signal, attempt = createRegistrationAttempt()) {
      await requirePatientService(signal);
      return client.request<PatientProfile>("/api/v1/auth/register", {
        method: "POST",
        body: input,
        signal,
        idempotencyKey: attempt.idempotencyKey,
        headers: { "X-Anonymous-Command-ID": attempt.anonymousCommandId },
      });
    },
    refresh: (signal) => serialized(async () => client.request<TokenSet>("/api/v1/auth/refresh", {
      method: "POST",
      headers: await requiredCsrfHeaders(),
      credentials: "include",
      signal,
    })),
    logout: (signal) => serialized(async () => {
      await client.request<void>("/api/v1/auth/logout", {
        method: "POST",
        headers: await requiredCsrfHeaders(),
        credentials: "include",
        signal,
      });
    }),
  };
}

const browserCsrfProvider = createCsrfHeadersProvider(apiClient);
if (typeof window !== "undefined") {
  window.pulseGridSecurity ??= { getCsrfHeaders: browserCsrfProvider };
}
export const authApi = createAuthApi(apiClient, () =>
  window.pulseGridSecurity!.getCsrfHeaders(),
);
