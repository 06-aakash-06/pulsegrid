import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";
import { handleMockRequest, resetMockState } from "./handlers";

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
    configureServer(server) {
      // Lets local end-to-end checks start from the original sample hospital.
      server.middlewares.use("/__mock/reset", (request: IncomingMessage, response: ServerResponse) => {
        if (request.method !== "POST") {
          response.statusCode = 405;
          response.end();
          return;
        }
        resetMockState();
        response.statusCode = 204;
        response.end();
      });
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
