import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiConfigurationError, ApiError } from "../api/client";
import type { RegistrationInput } from "../api/authApi";
import { Brand } from "../components/Brand";
import { useAuth } from "../auth/authContext";
import { workspaces } from "../navigation/workspaces";

function errorMessage(error: unknown): string {
  if (error instanceof ApiConfigurationError) return error.message;
  if (error instanceof ApiError) return error.message;
  return "The request could not be completed. Please try again later.";
}

export function LoginPage() {
  const { login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const roleHints = await login({ email, password });
      const from = typeof location.state === "object" && location.state !== null && "from" in location.state
        ? location.state.from
        : undefined;
      const requestedPath = typeof from === "string" && from.startsWith("/") ? from : undefined;
      const matchingWorkspace = requestedPath
        ? workspaces.find((item) =>
            item.roles.some((role) => roleHints.includes(role)) &&
            (requestedPath === item.basePath || requestedPath.startsWith(`${item.basePath}/`)),
          )
        : undefined;
      const workspace = matchingWorkspace ?? workspaces.find((item) => item.roles.some((role) => roleHints.includes(role)));
      if (workspace) {
        navigate(matchingWorkspace ? requestedPath! : `${workspace.basePath}/dashboard`, { replace: true });
      } else {
        setError("The identity service did not return a role for an available workspace.");
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthFrame title="Sign in" description="Use your PulseGrid account to open your workspace.">
      <form className="form-stack" onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="login-email">Email address</label>
        <input
          autoComplete="username"
          id="login-email"
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          required
          type="email"
          value={email}
        />
        <label className="field-label" htmlFor="login-password">Password</label>
        <input
          autoComplete="current-password"
          id="login-password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
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
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    const input: RegistrationInput = { display_name: displayName, email, password };
    try {
      await register(input);
      setSubmitted(true);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthFrame title="Create a patient account" description="Registration is for patient accounts. Staff roles are assigned by hospital administrators.">
      {submitted ? (
        <div className="form-message form-message--success" role="status">
          Your registration was accepted by the identity service. Sign in to continue.
        </div>
      ) : (
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="register-name">Display name</label>
          <input
            autoComplete="name"
            id="register-name"
            name="display_name"
            onChange={(event) => setDisplayName(event.target.value)}
            required
            type="text"
            value={displayName}
          />
          <label className="field-label" htmlFor="register-email">Email address</label>
          <input
            autoComplete="email"
            id="register-email"
            name="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label className="field-label" htmlFor="register-password">Password</label>
          <input
            autoComplete="new-password"
            id="register-password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
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
