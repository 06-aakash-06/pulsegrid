import { createDemoStore } from "./storage";

const SESSION_KEY = "pulsegrid_mock_session";
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
    else window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // Without storage the demo session simply ends on reload.
  }
}

function addRibbon() {
  const ribbon = document.createElement("div");
  ribbon.setAttribute("role", "note");
  ribbon.setAttribute("aria-label", "Mock data mode");
  ribbon.textContent = "MOCK DATA";
  ribbon.style.cssText = "position:fixed;z-index:2147483647;right:-46px;bottom:22px;transform:rotate(-45deg);width:180px;padding:6px 0;background:#a51c18;color:#fff;font:700 12px/1 system-ui,sans-serif;letter-spacing:.12em;text-align:center;box-shadow:0 2px 6px #0005;pointer-events:none";
  document.body.appendChild(ribbon);
}

/** Answers same-origin /api/* requests from the synthetic fixtures for the public demo build. */
export function installBrowserMock() {
  const realFetch = window.fetch.bind(window);
  const demoRequest = createDemoStore(() => window.localStorage);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : String(input), window.location.origin);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) return realFetch(input, init);
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
  if (document.body) addRibbon();
  else window.addEventListener("DOMContentLoaded", addRibbon);
}
