import { ApiError } from "../../api/client";
import { errorMessage, id } from "../ui";

export { errorMessage, id };

export function currentLocalDate(): string {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function idempotencyKey(): string {
  if (typeof crypto === "undefined" || typeof crypto.randomUUID !== "function") {
    throw new Error("Secure command identifiers are unavailable. Reload this page before retrying.");
  }
  return crypto.randomUUID();
}

export function isAmbiguousCommandFailure(error: unknown): boolean {
  return error instanceof ApiError &&
    (error.status === 0 || error.status >= 500 || error.code === "invalid_response");
}

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 409 || error.status === 412);
}

export function validateCheckinToken(value: string): string {
  const token = value.trim();
  if (!/^[0-9A-Za-z]{22}$/.test(token)) {
    throw new Error("Enter the 22-character check-in token from the patient's QR code or message.");
  }
  return token;
}

export interface ScannedCheckin {
  appointmentId: string;
  token: string;
}

export function parseCheckinQr(rawValue: string, origin = window.location.origin): ScannedCheckin {
  let url: URL;
  try {
    url = new URL(rawValue, origin);
  } catch {
    throw new Error("This QR code is not a PulseGrid check-in link.");
  }
  if (url.origin !== origin || url.pathname !== "/patient/check-in" || url.search) {
    throw new Error("This QR code is not a same-origin PulseGrid check-in link.");
  }
  const fragment = url.hash.startsWith("#") ? url.hash.slice(1) : "";
  const params = new URLSearchParams(fragment);
  const appointmentIds = params.getAll("appointment_id");
  const tokens = params.getAll("token");
  if (appointmentIds.length !== 1 || tokens.length !== 1 || [...params.keys()].length !== 2) {
    throw new Error("This QR code is missing a valid appointment or token.");
  }
  return {
    appointmentId: id(appointmentIds[0]),
    token: validateCheckinToken(tokens[0]),
  };
}

export function appendQueueQuery(
  path: string,
  query: Record<string, string | undefined>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value) params.set(key, value);
  }
  return params.size ? `${path}?${params.toString()}` : path;
}

export function scheduleLocalTime(value: string): string {
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(instant) + " UTC";
}
