import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiConfigurationError, ApiError } from "../api/client";
import { createRegistrationAttempt, type RegistrationAttempt, type RegistrationInput } from "../api/authApi";
import { useAuth } from "../auth/authContext";
import { Brand } from "../components/Brand";
import {
  getWorkspaceForPath,
  getWorkspaceForRoleHints,
} from "../navigation/workspaces";

function validEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function requestErrorMessage(error: unknown, action: "login" | "register"): string {
  if (error instanceof ApiConfigurationError) return error.message;
  if (error instanceof ApiError) {
    if (error.code === "network_error" || error.status === 0) {
      return "Unable to reach the identity service. Check your connection and try again.";
    }
    if (action === "login" && error.status === 401) {
      return "The email address or password is incorrect.";
    }
    if (action === "register" && error.status === 409) {
      return "An account with this email address may already exist. Try signing in or use a different email address.";
    }
    return error.message + ((error.status === 429 || error.status === 503) && error.retryAfterSeconds !== undefined ? ` Wait ${error.retryAfterSeconds} seconds before retrying.` : "");
  }
  return "The request could not be completed. Please try again later.";
}

interface IntendedLocation {
  pathname?: unknown;
  search?: unknown;
  hash?: unknown;
}

function readIntendedLocation(state: unknown): { pathname: string; to: string } | undefined {
  if (typeof state !== "object" || state === null || !("from" in state)) return undefined;
  const from = state.from;
  const location = typeof from === "string" ? { pathname: from } : from as IntendedLocation;
  if (typeof location !== "object" || location === null || typeof location.pathname !== "string") {
    return undefined;
  }
  const pathname = location.pathname;
  if (!pathname.startsWith("/") || pathname.startsWith("//")) return undefined;
  const search = typeof location.search === "string" ? location.search : "";
  const hash = typeof location.hash === "string" ? location.hash : "";
  return { pathname, to: `${pathname}${search}${hash}` };
}

export function LoginPage() {
  const { login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => () => requestController.current?.abort(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const normalizedEmail = email.trim();
    const nextFieldErrors: { email?: string; password?: string } = {};
    if (!validEmail(normalizedEmail)) {
      nextFieldErrors.email = "Enter a valid email address.";
    }
    if (password.length === 0) {
      nextFieldErrors.password = "Enter your password.";
    }
    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) return;
    setIsSubmitting(true);
    const controller = new AbortController();
    requestController.current = controller;
    try {
      const roleHints = await login({ email: normalizedEmail, password }, controller.signal);
      const intended = readIntendedLocation(location.state);
      if (intended?.pathname === "/short-link" && (roleHints.includes("patient") || roleHints.includes("receptionist"))) {
        navigate("/short-link", { replace: true });
        return;
      }
      const intendedWorkspace = intended
        ? getWorkspaceForPath(intended.pathname, roleHints)
        : undefined;
      const workspace = intendedWorkspace ?? getWorkspaceForRoleHints(roleHints);
      if (workspace) {
        navigate(
          intendedWorkspace && intended
            ? intended.to
            : `${workspace.basePath}/dashboard`,
          { replace: true },
        );
      } else {
        navigate("/", { replace: true });
      }
    } catch (requestError) {
      if (!controller.signal.aborted) setError(requestErrorMessage(requestError, "login"));
    } finally {
      if (!controller.signal.aborted) setIsSubmitting(false);
      if (requestController.current === controller) requestController.current = null;
    }
  }

  return (
    <AuthFrame title="Sign in" description="Use your PulseGrid account to open your workspace.">
      <form aria-busy={isSubmitting} className="form-stack" noValidate onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="login-email">Email address</label>
        <input
          aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
          aria-invalid={Boolean(fieldErrors.email)}
          autoCapitalize="none"
          autoComplete="username"
          id="login-email"
          name="email"
          onChange={(event) => {
            setEmail(event.target.value);
            setFieldErrors((current) => ({ ...current, email: undefined }));
          }}
          required
          type="email"
          value={email}
        />
        <label className="field-label" htmlFor="login-password">Password</label>
        <div className="password-control">
          <input
            aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
            aria-invalid={Boolean(fieldErrors.password)}
            autoComplete="current-password"
            id="login-password"
            name="password"
            onChange={(event) => {
              setPassword(event.target.value);
              setFieldErrors((current) => ({ ...current, password: undefined }));
            }}
            required
            type={passwordVisible ? "text" : "password"}
            value={password}
          />
          <button
            aria-label={passwordVisible ? "Hide password" : "Show password"}
            aria-pressed={passwordVisible}
            className="password-toggle"
            onClick={() => setPasswordVisible((visible) => !visible)}
            type="button"
          >
            {passwordVisible ? "Hide" : "Show"}
          </button>
        </div>
        {fieldErrors.email ? <p className="field-error" id="login-email-error" role="alert">{fieldErrors.email}</p> : null}
        {fieldErrors.password ? <p className="field-error" id="login-password-error" role="alert">{fieldErrors.password}</p> : null}
        {error ? <p className="form-message form-message--error" role="alert">{error}</p> : null}
        <button className="button button--full" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="form-footnote">Access is granted only after the identity service responds successfully.</p>
      <p className="auth-switch">New to PulseGrid? <Link to="/register">Create a patient account</Link></p>
    </AuthFrame>
  );
}

export function RegistrationPage() {
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [syntheticContact, setSyntheticContact] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const registrationAttempt = useRef<{ input: RegistrationInput; attempt: RegistrationAttempt } | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const requestController = useRef<AbortController | null>(null);

  useEffect(() => () => requestController.current?.abort(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const nextErrors: Record<string, string> = {};
    const normalizedName = displayName.trim();
    const normalizedEmail = email.trim();
    if (!normalizedName) nextErrors.displayName = "Enter your display name.";
    if (!validEmail(normalizedEmail)) nextErrors.email = "Enter a valid email address.";
    if (!password) nextErrors.password = "Enter a password.";
    if (!passwordConfirmation) nextErrors.passwordConfirmation = "Confirm your password.";
    else if (password !== passwordConfirmation) nextErrors.passwordConfirmation = "Passwords do not match.";
    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setIsSubmitting(true);
    const controller = new AbortController();
    requestController.current = controller;
    const input: RegistrationInput = {
      display_name: normalizedName,
      email: normalizedEmail,
      password,
      ...(dateOfBirth ? { date_of_birth: dateOfBirth } : {}),
      ...(syntheticContact.trim() ? { synthetic_contact: syntheticContact.trim() } : {}),
    };
    try {
      if (!registrationAttempt.current || JSON.stringify(registrationAttempt.current.input) !== JSON.stringify(input)) {
        registrationAttempt.current = { input, attempt: createRegistrationAttempt() };
      }
      await register(input, controller.signal, registrationAttempt.current.attempt);
      registrationAttempt.current = null;
      if (!controller.signal.aborted) setSubmitted(true);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status >= 400 && requestError.status < 500) {
        registrationAttempt.current = null;
      }
      if (!controller.signal.aborted) setError(requestErrorMessage(requestError, "register"));
    } finally {
      if (!controller.signal.aborted) setIsSubmitting(false);
      if (requestController.current === controller) requestController.current = null;
    }
  }

  return (
    <AuthFrame title="Create a patient account" description="Registration is for patient accounts. Staff roles are assigned by hospital administrators.">
      {submitted ? (
        <div className="form-message form-message--success" role="status">
          Your registration was accepted by the identity service. <Link to="/login">Sign in to continue.</Link>
        </div>
      ) : (
        <form aria-busy={isSubmitting} className="form-stack" noValidate onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="register-name">Display name</label>
          <input
            aria-describedby={fieldErrors.displayName ? "register-name-error" : undefined}
            aria-invalid={Boolean(fieldErrors.displayName)}
            autoComplete="name"
            id="register-name"
            name="display_name"
            onChange={(event) => {
              setDisplayName(event.target.value);
              setFieldErrors((current) => {
                const next = { ...current };
                delete next.displayName;
                return next;
              });
              setError(null);
            }}
            required
            type="text"
            value={displayName}
          />
          {fieldErrors.displayName ? <p className="field-error" id="register-name-error" role="alert">{fieldErrors.displayName}</p> : null}

          <label className="field-label" htmlFor="register-email">Email address</label>
          <input
            aria-describedby={fieldErrors.email ? "register-email-error" : undefined}
            aria-invalid={Boolean(fieldErrors.email)}
            autoCapitalize="none"
            autoComplete="email"
            id="register-email"
            name="email"
            onChange={(event) => {
              setEmail(event.target.value);
              setFieldErrors((current) => {
                const next = { ...current };
                delete next.email;
                return next;
              });
              setError(null);
            }}
            required
            type="email"
            value={email}
          />
          {fieldErrors.email ? <p className="field-error" id="register-email-error" role="alert">{fieldErrors.email}</p> : null}

          <label className="field-label" htmlFor="register-dob">Date of birth <span className="field-optional">Optional</span></label>
          <input
            autoComplete="bday"
            id="register-dob"
            name="date_of_birth"
            onChange={(event) => setDateOfBirth(event.target.value)}
            type="date"
            value={dateOfBirth}
          />

          <label className="field-label" htmlFor="register-contact">Synthetic contact <span className="field-optional">Optional</span></label>
          <input
            autoComplete="off"
            id="register-contact"
            name="synthetic_contact"
            onChange={(event) => setSyntheticContact(event.target.value)}
            type="text"
            value={syntheticContact}
          />

          <label className="field-label" htmlFor="register-password">Password</label>
          <input
            aria-describedby={fieldErrors.password ? "register-password-error" : undefined}
            aria-invalid={Boolean(fieldErrors.password)}
            autoComplete="new-password"
            id="register-password"
            name="password"
            onChange={(event) => {
              setPassword(event.target.value);
              setFieldErrors((current) => {
                const next = { ...current };
                delete next.password;
                return next;
              });
              setError(null);
            }}
            required
            type="password"
            value={password}
          />
          {fieldErrors.password ? <p className="field-error" id="register-password-error" role="alert">{fieldErrors.password}</p> : null}

          <label className="field-label" htmlFor="register-password-confirmation">Confirm password</label>
          <input
            aria-describedby={fieldErrors.passwordConfirmation ? "register-password-confirmation-error" : undefined}
            aria-invalid={Boolean(fieldErrors.passwordConfirmation)}
            autoComplete="new-password"
            id="register-password-confirmation"
            name="password_confirmation"
            onChange={(event) => {
              setPasswordConfirmation(event.target.value);
              setFieldErrors((current) => {
                const next = { ...current };
                delete next.passwordConfirmation;
                return next;
              });
              setError(null);
            }}
            required
            type="password"
            value={passwordConfirmation}
          />
          {fieldErrors.passwordConfirmation ? <p className="field-error" id="register-password-confirmation-error" role="alert">{fieldErrors.passwordConfirmation}</p> : null}
          {error ? <p className="form-message form-message--error" role="alert">{error}</p> : null}
          <button className="button button--full" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Submitting…" : "Create account"}
          </button>
        </form>
      )}
      <p className="form-footnote">Use synthetic information only. Registration does not sign you in automatically.</p>
      <p className="auth-switch">Already registered? <Link to="/login">Sign in</Link></p>
    </AuthFrame>
  );
}

interface AuthFrameProps {
  title: string;
  description: string;
  children: ReactNode;
}

function AuthFrame({ title, description, children }: AuthFrameProps) {
  return (
    <main className="auth-page">
      <div className="auth-topbar"><Brand /></div>
      <section className="auth-card" aria-labelledby="auth-title">
        <p className="eyebrow">Patient and staff access</p>
        <h1 id="auth-title">{title}</h1>
        <p className="auth-description">{description}</p>
        {children}
      </section>
      <p className="auth-legal">Synthetic educational prototype · Not for real clinical use</p>
    </main>
  );
}
