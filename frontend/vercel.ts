// The public browser demo keeps all fictional data in each visitor's browser and has no gateway to proxy.
const demoDeploy = process.env.PULSEGRID_DEMO_DEPLOY?.trim() === "true";

function backendOrigin(): string {
  const configuredBackend = process.env.PULSEGRID_BACKEND_ORIGIN?.trim();
  if (!configuredBackend) {
    throw new Error(
      "Set PULSEGRID_BACKEND_ORIGIN to the HTTPS PulseGrid gateway origin in Vercel project settings, or PULSEGRID_DEMO_DEPLOY=true for the browser-only demo.",
    );
  }
  try {
    const parsed = new URL(configuredBackend);
    if (
      parsed.protocol !== "https:" ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      throw new Error("The backend must be a bare HTTPS origin without credentials or a path.");
    }
    return parsed.origin;
  } catch {
    throw new Error(
      "PULSEGRID_BACKEND_ORIGIN must be a valid HTTPS origin such as https://api.example.org.",
    );
  }
}

const spaFallback = { source: "/(.*)", destination: "/index.html" };

function gatewayConfig() {
  const origin = backendOrigin();
  return {
    buildCommand: "npm run build",
    headers: [
      {
        source: "/api/:path*",
        headers: [{ key: "x-vercel-enable-rewrite-caching", value: "0" }],
      },
      {
        source: "/s/:path*",
        headers: [{ key: "x-vercel-enable-rewrite-caching", value: "0" }],
      },
    ],
    rewrites: [
      { source: "/api/:path*", destination: `${origin}/api/:path*` },
      { source: "/s/:path*", destination: `${origin}/s/:path*` },
      spaFallback,
    ],
  };
}

export const config = {
  framework: "vite",
  installCommand: "npm ci",
  outputDirectory: "dist",
  ...(demoDeploy ? { buildCommand: "npm run build:demo", rewrites: [spaFallback] } : gatewayConfig()),
};
