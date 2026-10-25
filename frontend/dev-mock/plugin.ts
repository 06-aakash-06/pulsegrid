import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";
import { handleMockRequest } from "./handlers";

const RIBBON = `<div role="note" aria-label="Mock data mode" style="position:fixed;z-index:2147483647;right:-46px;bottom:22px;transform:rotate(-45deg);width:180px;padding:6px 0;background:#a51c18;color:#fff;font:700 12px/1 system-ui,sans-serif;letter-spacing:.12em;text-align:center;box-shadow:0 2px 6px #0005;pointer-events:none">MOCK DATA</div>`;
const LATENCY_MS = 90;

function readBody(request: IncomingMessage): Promise<unknown> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      try {
        resolve(text ? JSON.parse(text) : undefined);
      } catch {
        resolve(undefined);
      }
    });
  });
}

/** Serve-only fixture API for `npm run dev:mock`; it is never part of a production build. */
export function mockApiPlugin(): Plugin {
  return {
    name: "pulsegrid-dev-mock-api",
    apply: "serve",
    transformIndexHtml(html) {
      return html.replace("</body>", `${RIBBON}</body>`);
    },
    configureServer(server) {
      server.middlewares.use("/api", (request: IncomingMessage, response: ServerResponse) => {
        void (async () => {
          const url = new URL(`/api${request.url ?? ""}`, "http://mock.local");
          const headers = Object.fromEntries(
            Object.entries(request.headers).map(([key, value]) => [key, Array.isArray(value) ? value.join(",") : value]),
          );
          const body = await readBody(request);
          const result = await handleMockRequest({ method: request.method ?? "GET", url, headers, body });
          await new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
          response.statusCode = result.status;
          response.setHeader("Cache-Control", "no-store");
          response.setHeader("X-PulseGrid-Mock", "true");
          if (result.etag) response.setHeader("ETag", result.etag);
          if (headers["idempotency-key"]) response.setHeader("Idempotency-Key", headers["idempotency-key"]);
          for (const [key, value] of Object.entries(result.headers ?? {})) response.setHeader(key, value);
          if (result.body === undefined || result.status === 204) {
            response.end();
            return;
          }
          response.setHeader("Content-Type", "application/json");
          response.end(JSON.stringify(result.body));
        })();
      });
    },
  };
}
