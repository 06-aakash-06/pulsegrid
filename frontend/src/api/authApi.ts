import {
  ApiConfigurationError,
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

export type CsrfHeadersProvider = () => HeadersInit | Promise<HeadersInit>;

export interface AuthApi {
  login(input: LoginInput, signal?: AbortSignal): Promise<TokenSet>;
  register(input: RegistrationInput, signal?: AbortSignal): Promise<PatientProfile>;
  refresh(signal?: AbortSignal): Promise<TokenSet>;
  logout(signal?: AbortSignal): Promise<void>;
}

export function createAuthApi(
  client: ApiClient = apiClient,
  getCsrfHeaders?: CsrfHeadersProvider,
): AuthApi {
  const requiredCsrfHeaders = async (): Promise<HeadersInit> => {
    if (!getCsrfHeaders) {
      throw new ApiConfigurationError(
        "Sign-in requires a configured CSRF header provider.",
      );
    }
    return getCsrfHeaders();
  };

  return {
    async login(input, signal) {
      return client.request<TokenSet>("/api/v1/auth/login", {
        method: "POST",
        body: input,
        headers: await requiredCsrfHeaders(),
        credentials: "include",
        signal,
      });
    },
    async register(input, signal) {
      return client.request<PatientProfile>("/api/v1/auth/register", {
        method: "POST",
        body: input,
        signal,
      });
    },
    async refresh(signal) {
      return client.request<TokenSet>("/api/v1/auth/refresh", {
        method: "POST",
        headers: await requiredCsrfHeaders(),
        credentials: "include",
        signal,
      });
    },
    async logout(signal) {
      await client.request<void>("/api/v1/auth/logout", {
        method: "POST",
        headers: await requiredCsrfHeaders(),
        credentials: "include",
        signal,
      });
    },
  };
}

export const authApi = createAuthApi(apiClient, () => {
  const provider = window.pulseGridSecurity?.getCsrfHeaders;
  if (!provider) {
    throw new ApiConfigurationError(
      "Sign-in is unavailable until the host configures CSRF protection.",
    );
  }
  return provider();
});
