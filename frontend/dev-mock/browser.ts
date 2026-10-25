import { clearMockSession, createDemoStore, MOCK_SESSION_KEY } from "./storage";

const SESSION_KEY = MOCK_SESSION_KEY;
const SESSION_COOKIE = /pulsegrid_mock_session=(\d*)/;
const LATENCY_MS = 90;

function readSession() {
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function writeSession(value: string | null) {
  try {
    if (value) window.localStorage.setItem(SESSION_KEY, value);
    else clearMockSession(window.localStorage);
  } catch {
    // Without storage the demo session simply ends on reload.
  }
}

/** Answers same-origin /api/* requests from the synthetic fixtures for the public demo build. */
export function installBrowserMock() {
  const realFetch = window.fetch.bind(window);
  const demoRequest = createDemoStore(() => window.localStorage);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : String(input), window.location.origin);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) return realFetch(input, init);
    // Clear before awaiting the fixture transaction/latency, so an immediate
    // reload cannot restore a session while sign-out is still in flight.
    if (url.pathname === "/api/v1/auth/logout" && (init?.method ?? request?.method ?? "GET").toUpperCase() === "POST") writeSession(null);
    const headers: Record<string, string | undefined> = {};
    new Headers(init?.headers ?? request?.headers).forEach((value, key) => { headers[key] = value; });
    const session = readSession();
    if (session) headers.cookie = `${SESSION_KEY}=${session}`;
    const rawBody = typeof init?.body === "string" ? init.body : request ? await request.text() : "";
    let body: unknown;
    try {
      body = rawBody ? JSON.parse(rawBody) : undefined;
    } catch {
      body = undefined;
    }
    const result = await demoRequest({ method: init?.method ?? request?.method ?? "GET", url, headers, body });
    await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
    const responseHeaders = new Headers({ "Cache-Control": "no-store", "X-PulseGrid-Mock": "true" });
    if (result.etag) responseHeaders.set("ETag", result.etag);
    if (headers["idempotency-key"]) responseHeaders.set("Idempotency-Key", headers["idempotency-key"]);
    for (const [key, value] of Object.entries(result.headers ?? {})) {
      if (key.toLowerCase() === "set-cookie") writeSession(SESSION_COOKIE.exec(value)?.[1] || null);
      else responseHeaders.set(key, value);
    }
    if (result.body === undefined || result.status === 204) return new Response(null, { status: result.status, headers: responseHeaders });
    responseHeaders.set("Content-Type", "application/json");
    return new Response(JSON.stringify(result.body), { status: result.status, headers: responseHeaders });
  };
}
