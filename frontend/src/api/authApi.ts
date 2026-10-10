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
  login(input: LoginInput): Promise<TokenSet>;
  register(input: RegistrationInput): Promise<PatientProfile>;
  refresh(): Promise<TokenSet>;
  logout(): Promise<void>;
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
    async login(input) {
      return client.request<TokenSet>("/api/v1/auth/login", {
        method: "POST",
        body: input,
        headers: await requiredCsrfHeaders(),
        credentials: "include",
      });
    },
    async register(input) {
      return client.request<PatientProfile>("/api/v1/auth/register", {
        method: "POST",
        body: input,
      });
    },
    async refresh() {
      return client.request<TokenSet>("/api/v1/auth/refresh", {
        method: "POST",
        headers: await requiredCsrfHeaders(),
        credentials: "include",
      });
    },
    async logout() {
      await client.request<void>("/api/v1/auth/logout", {
        method: "POST",
        headers: await requiredCsrfHeaders(),
        credentials: "include",
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
