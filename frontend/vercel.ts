const configuredBackend = process.env.PULSEGRID_BACKEND_ORIGIN?.trim();

if (!configuredBackend) {
  throw new Error(
    "Set PULSEGRID_BACKEND_ORIGIN to the HTTPS PulseGrid gateway origin in Vercel project settings.",
  );
}

let backendOrigin: string;
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
  backendOrigin = parsed.origin;
} catch {
  throw new Error(
    "PULSEGRID_BACKEND_ORIGIN must be a valid HTTPS origin such as https://api.example.org.",
  );
}

export const config = {
  framework: "vite",
  installCommand: "npm ci",
  buildCommand: "npm run build",
  outputDirectory: "dist",
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
    { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
    { source: "/s/:path*", destination: `${backendOrigin}/s/:path*` },
    { source: "/(.*)", destination: "/index.html" },
  ],
};
