import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { readFile } from "node:fs/promises";
import { mockApiPlugin } from "./dev-mock/plugin";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const gatewayUrl = env.PULSEGRID_GATEWAY_URL || "http://127.0.0.1:8080";
  return {
    server: {
      host: "127.0.0.1",
      proxy: {
        "/api": { target: gatewayUrl, changeOrigin: false },
        "/s/": { target: gatewayUrl, changeOrigin: false },
      },
    },
    plugins: [
      react(),
      ...(env.VITE_MOCK_API === "true" ? [mockApiPlugin()] : []),
      ...(env.VITE_DEMO_MOCK === "true"
        ? [{
            name: "pulsegrid-demo-mock-entry",
            apply: "build" as const,
            transformIndexHtml: {
              order: "pre" as const,
              handler: (html: string) =>
                html.replace(/<script type="module"/, '<script type="module" src="/dev-mock/browser-entry.ts"></script>\n    <script type="module"'),
            },
          }]
        : []),
      {
        name: "local-fictional-demo",
        apply: "serve",
        configureServer(server) {
          server.middlewares.use(
            "/__demo/hospital.json",
            async (_request, response) => {
              if (env.VITE_LOCAL_HOSPITAL_DEMO !== "true") {
                response.statusCode = 404;
                response.end();
                return;
              }
              try {
                response.setHeader("Content-Type", "application/json");
                response.setHeader("Cache-Control", "no-store");
                response.end(
                  await readFile(
                    new URL("./.demo/hospital.json", import.meta.url),
                    "utf8",
                  ),
                );
              } catch {
                response.statusCode = 404;
                response.end();
              }
            },
          );
        },
      },
    ],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("@zxing")) return "qr-decoder";
            if (id.includes("node_modules/qrcode")) return "qr-encoder";
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      clearMocks: true,
    },
  };
});
