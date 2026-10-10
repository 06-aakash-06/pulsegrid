import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { authApi, type AuthApi, type LoginInput, type RegistrationInput, type TokenSet } from "../api/authApi";

export const roles = [
  "patient",
  "doctor",
  "receptionist",
  "pharmacist",
  "billing_staff",
  "emergency_staff",
  "hospital_admin",
  "ops",
] as const;

export type Role = (typeof roles)[number];

export type AuthState =
  | { status: "anonymous" }
  | {
      status: "authenticated";
      accessToken: string;
      expiresAt: number;
      roleHints: Role[];
    };

export interface AuthContextValue {
  state: AuthState;
  login(input: LoginInput): Promise<Role[]>;
  register(input: RegistrationInput): ReturnType<AuthApi["register"]>;
  refresh(): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isRole(value: unknown): value is Role {
  return typeof value === "string" && roles.includes(value as Role);
}

function readRoleHints(accessToken: string): Role[] {
  try {
    const encodedPayload = accessToken.split(".")[1];
    if (!encodedPayload) return [];
    const base64 = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const payload = JSON.parse(atob(padded)) as { roles?: unknown };
    if (!Array.isArray(payload.roles)) return [];
    return [...new Set(payload.roles.filter(isRole))];
  } catch {
    return [];
  }
}

function validateTokenSet(tokenSet: TokenSet): void {
  if (
    tokenSet.token_type !== "Bearer" ||
    typeof tokenSet.access_token !== "string" ||
    tokenSet.access_token.length === 0 ||
    !Number.isFinite(tokenSet.expires_in) ||
    tokenSet.expires_in <= 0
  ) {
    throw new Error("The identity service returned an invalid session response.");
  }
}

function toAuthState(tokenSet: TokenSet): AuthState {
  validateTokenSet(tokenSet);
  return {
    status: "authenticated",
    accessToken: tokenSet.access_token,
    expiresAt: Date.now() + tokenSet.expires_in * 1000,
    roleHints: readRoleHints(tokenSet.access_token),
  };
}

export interface AuthProviderProps {
  children: ReactNode;
  client?: AuthApi;
}

export function AuthProvider({ children, client = authApi }: AuthProviderProps) {
  const [state, setState] = useState<AuthState>({ status: "anonymous" });

  useEffect(() => {
    if (state.status !== "authenticated") return;
    const remaining = state.expiresAt - Date.now();
    if (remaining <= 0) {
      setState({ status: "anonymous" });
      return;
    }
    const timeout = window.setTimeout(() => setState({ status: "anonymous" }), remaining);
    return () => window.clearTimeout(timeout);
  }, [state]);

  const login = useCallback(async (input: LoginInput) => {
    const tokenSet = await client.login(input);
    const nextState = toAuthState(tokenSet);
    setState(nextState);
    return nextState.status === "authenticated" ? nextState.roleHints : [];
  }, [client]);

  const register = useCallback((input: RegistrationInput) => client.register(input), [client]);

  const refresh = useCallback(async () => {
    try {
      const tokenSet = await client.refresh();
      setState(toAuthState(tokenSet));
    } catch (error) {
      setState({ status: "anonymous" });
      throw error;
    }
  }, [client]);

  const logout = useCallback(async () => {
    try {
      await client.logout();
    } finally {
      setState({ status: "anonymous" });
    }
  }, [client]);

  const value = useMemo(() => ({ state, login, register, refresh, logout }), [state, login, register, refresh, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
