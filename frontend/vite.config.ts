import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";

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
    plugins: [react()],
    build: { rollupOptions: { output: { manualChunks(id) {
      if (id.includes("@zxing")) return "qr-decoder";
      if (id.includes("node_modules/qrcode")) return "qr-encoder";
    } } } },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      clearMocks: true,
    },
  };
});
