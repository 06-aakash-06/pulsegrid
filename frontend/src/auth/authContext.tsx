import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  authApi,
  type AuthApi,
  type LoginInput,
  type RegistrationInput,
  type RegistrationAttempt,
  type TokenSet,
} from "../api/authApi";
import {
  ApiError,
  apiClient,
  createAuthenticatedApiClient,
  type ApiClient,
} from "../api/client";

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

export interface AuthenticatedUser {
  id?: string;
  roleHints: Role[];
}

export type AuthState =
  | { status: "checking" }
  | { status: "anonymous" }
  | {
      status: "authenticated";
      accessToken: string;
      expiresAt: number;
      user: AuthenticatedUser;
      roleHints: Role[];
    };

export interface AuthContextValue {
  state: AuthState;
  api: ApiClient;
  login(input: LoginInput, signal?: AbortSignal): Promise<Role[]>;
  register(input: RegistrationInput, signal?: AbortSignal, attempt?: RegistrationAttempt): ReturnType<AuthApi["register"]>;
  refresh(): Promise<void>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isRole(value: unknown): value is Role {
  return typeof value === "string" && roles.includes(value as Role);
}

interface TokenClaims {
  sub?: unknown;
  roles?: unknown;
}

function readClaims(accessToken: string): TokenClaims {
  try {
    const encodedPayload = accessToken.split(".")[1];
    if (!encodedPayload) return {};
    const base64 = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    return JSON.parse(atob(padded)) as TokenClaims;
  } catch {
    return {};
  }
}

function validateTokenSet(tokenSet: TokenSet): void {
  if (
    tokenSet === null ||
    typeof tokenSet !== "object" ||
    tokenSet.token_type !== "Bearer" ||
    typeof tokenSet.access_token !== "string" ||
    tokenSet.access_token.length === 0 ||
    !Number.isInteger(tokenSet.expires_in) ||
    tokenSet.expires_in <= 0
  ) {
    throw new ApiError(
      "The identity service returned an invalid session response.",
      502,
      "invalid_auth_response",
    );
  }
}

function toAuthState(tokenSet: TokenSet): AuthState {
  validateTokenSet(tokenSet);
  const claims = readClaims(tokenSet.access_token);
  const roleHints = Array.isArray(claims.roles)
    ? [...new Set(claims.roles.filter(isRole))]
    : [];
  const id = typeof claims.sub === "string" && claims.sub.length > 0
    ? claims.sub
    : undefined;

  return {
    status: "authenticated",
    accessToken: tokenSet.access_token,
    expiresAt: Date.now() + tokenSet.expires_in * 1000,
    user: { ...(id ? { id } : {}), roleHints },
    roleHints,
  };
}

function sessionEndedError(): ApiError {
  return new ApiError("Your session has expired. Sign in to continue.", 401, "session_expired");
}

function requireAuthenticatedState(state: AuthState): Extract<AuthState, { status: "authenticated" }> {
  if (state.status !== "authenticated") throw sessionEndedError();
  return state;
}

export interface AuthProviderProps {
  children: ReactNode;
  client?: AuthApi;
  apiClient?: ApiClient;
}

export function AuthProvider({
  children,
  client = authApi,
  apiClient: domainApiClient = apiClient,
}: AuthProviderProps) {
  const initialState: AuthState = { status: "checking" };
  const [state, setState] = useState<AuthState>(initialState);
  const stateRef = useRef<AuthState>(initialState);
  const sessionEpochRef = useRef(0);
  const refreshFlightRef = useRef<{ epoch: number; promise: Promise<AuthState> } | null>(null);
  const restorationRef = useRef<Promise<void> | null>(null);

  const updateState = useCallback((nextState: AuthState) => {
    stateRef.current = nextState;
    setState(nextState);
  }, []);

  const refreshSingleFlight = useCallback((expiredAccessToken?: string): Promise<AuthState> => {
    const currentState = stateRef.current;
    if (
      expiredAccessToken &&
      currentState.status === "authenticated" &&
      currentState.accessToken !== expiredAccessToken
    ) {
      return Promise.resolve(currentState);
    }
    if (expiredAccessToken && currentState.status !== "authenticated") {
      return Promise.reject(sessionEndedError());
    }

    const epoch = sessionEpochRef.current;
    const currentFlight = refreshFlightRef.current;
    if (currentFlight?.epoch === epoch) return currentFlight.promise;

    let request: Promise<AuthState>;
    request = client.refresh()
      .then((tokenSet) => {
        const nextState = toAuthState(tokenSet);
        if (sessionEpochRef.current !== epoch) throw sessionEndedError();
        updateState(nextState);
        return nextState;
      })
      .catch((error: unknown) => {
        if (sessionEpochRef.current === epoch) updateState({ status: "anonymous" });
        throw error;
      })
      .finally(() => {
        if (refreshFlightRef.current?.promise === request) refreshFlightRef.current = null;
      });
    refreshFlightRef.current = { epoch, promise: request };
    return request;
  }, [client, updateState]);

  const restoreSession = useCallback((): Promise<void> => {
    if (stateRef.current.status !== "checking") return Promise.resolve();
    if (restorationRef.current) return restorationRef.current;

    const restoration = refreshSingleFlight()
      .then(() => undefined)
      .catch(() => undefined);
    restorationRef.current = restoration;
    return restoration;
  }, [refreshSingleFlight]);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  const getAccessToken = useCallback(async (): Promise<string> => {
    if (stateRef.current.status === "checking") await restoreSession();
    const currentState = stateRef.current;
    if (currentState.status !== "authenticated") throw sessionEndedError();
    if (currentState.expiresAt <= Date.now()) {
      return requireAuthenticatedState(
        await refreshSingleFlight(currentState.accessToken),
      ).accessToken;
    }
    return currentState.accessToken;
  }, [refreshSingleFlight, restoreSession]);

  const refresh = useCallback(async () => {
    if (stateRef.current.status === "checking") await restoreSession();
    const currentState = stateRef.current;
    await refreshSingleFlight(
      currentState.status === "authenticated" ? currentState.accessToken : undefined,
    );
  }, [refreshSingleFlight, restoreSession]);

  const login = useCallback(async (input: LoginInput, signal?: AbortSignal) => {
    const epoch = ++sessionEpochRef.current;
    const tokenSet = await client.login(input, signal);
    if (sessionEpochRef.current !== epoch) throw sessionEndedError();
    const nextState = toAuthState(tokenSet);
    updateState(nextState);
    return requireAuthenticatedState(nextState).roleHints;
  }, [client, updateState]);

  const register = useCallback(
    (input: RegistrationInput, signal?: AbortSignal, attempt?: RegistrationAttempt) => client.register(input, signal, attempt),
    [client],
  );

  const logout = useCallback(async () => {
    ++sessionEpochRef.current;
    updateState({ status: "anonymous" });
    await client.logout();
  }, [client, updateState]);

  const authenticatedApi = useMemo(() => createAuthenticatedApiClient(domainApiClient, {
    getAccessToken,
    refreshAccessToken: async (expiredAccessToken) => requireAuthenticatedState(
      await refreshSingleFlight(expiredAccessToken),
    ).accessToken,
  }), [domainApiClient, getAccessToken, refreshSingleFlight]);

  useEffect(() => {
    if (state.status !== "authenticated") return;
    const timeout = window.setTimeout(
      () => void refreshSingleFlight(state.accessToken).catch(() => undefined),
      Math.max(0, state.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timeout);
  }, [state, refreshSingleFlight]);

  const value = useMemo(
    () => ({ state, api: authenticatedApi, login, register, refresh, logout }),
    [state, authenticatedApi, login, register, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
