# Vercel and Render deployment preparation

This repository is prepared for a Vercel-hosted React frontend and a separately hosted backend. No cloud project, domain, managed database, or deployment has been provisioned or tested. The current deployment boundary is deliberately a runbook, not a claim of production readiness.

## Frontend on Vercel

Create a Vercel project with `frontend/` as its root directory. Use the committed lockfile, `npm ci`, and the normal `npm run build` command. Do not select `build:demo`; that command injects development mocks. `frontend/vercel.ts` fails closed unless `PULSEGRID_BACKEND_ORIGIN` is a bare HTTPS origin, then rewrites `/api/*` and `/s/*` requests to the backend gateway and sends the remaining paths to the SPA entrypoint. Set the origin in Vercel project environment settings for each deployment environment; it is a server-side routing value and must not use a `VITE_` prefix.

The browser keeps API calls same-origin at the Vercel URL. This lets the existing CSRF and HttpOnly refresh-cookie flow remain same-site while Vercel proxies the request. Keep the backend origin stable, enable TLS, set Patient `AUTH_ORIGINS` to the exact Vercel origin, and set `AUTH_ALLOW_HTTP=false`. The Patient service enforces secure cookies and exact-origin CSRF checks in that configuration. Never place database, signing, service-auth, Redis or RabbitMQ credentials in Vercel frontend variables or the generated bundle. `/api` and `/s` rewrite caching is disabled by the Vercel headers in the config.

## Backend and data services on Render

Use a public HTTPS edge/gateway for the browser-facing API and keep the seven FastAPI domains private to the Render service network. Configure services in the same Render region and use their private addresses for service-to-service calls. Deploy the existing service Dockerfiles and keep their migration job, readiness, telemetry and internal service-auth behavior. Only the gateway should accept public application traffic; do not expose internal domain APIs or datastore ports.

Provision PostgreSQL with seven isolated service databases and their existing owner/migration users. A shared PostgreSQL cluster can host the seven logical databases only while database grants continue to enforce each service's ownership boundary. Set each service's own connection and migration variables through Render secret environment settings. Run each service's existing Alembic migration as an explicit release/pre-deploy operation and require success before its API receives traffic.

Provision Redis-compatible storage only after verifying the Phase 4 ACL, Lua, sorted-set and connection/TLS requirements against the provider's exact service. The local Compose Redis behavior is not assumed to be a drop-in provider configuration. Keep admission and cache credentials distinct. Provision RabbitMQ as a private, durable broker with persistent storage and stable private credentials if using a self-hosted container; validate its queue durability, management, backup and restart behavior before enabling event workers. A single persistent broker instance is a single-instance deployment, not high availability. Do not use ephemeral container storage for PostgreSQL, Redis persistence, RabbitMQ, or any other durable state.

Keep all application and dependency credentials in Render's secret environment configuration. Configure exact service origins, signed user/service keys, database users, Redis ACL credentials, RabbitMQ credentials, telemetry export endpoints, bounded connection pools and timeouts. Do not pass secrets as Docker build arguments or commit a populated `.env`. Apply database backups and a tested restore procedure before a public demo, and keep outbox/inbox reconciliation enabled. Frontend redeploys must never run database reset or seed commands.

## Initial administrator and seed gate

The Phase 11 reset and seed helpers intentionally accept loopback development targets only. They use the existing Patient first-administrator bootstrap, then create identities and all domain data through the owning APIs. They must not be pointed at Render or a public URL. The shared local demo password in ignored `secrets/phase11/credentials.json` is only for the local demo and must never be reused for hosted accounts.

Before a hosted fictional dataset can be seeded, provision a one-time hospital administrator through a reviewed, private operator procedure, issue eight separate strong credentials outside Git, and adapt/run the owner-API seed workflow with an explicit deployment-target guard and resumable private state. The repository does not provide or test that hosted bootstrap procedure yet; do not weaken the local-only guard or expose a bootstrap route to make a deploy pass. This is the remaining deployment decision/gate.

## Provider references

- [Vercel project configuration](https://vercel.com/docs/project-configuration) and [TypeScript configuration files](https://vercel.com/docs/project-configuration/vercel-ts)
- [Vercel rewrites](https://vercel.com/docs/routing/rewrites)
- [Render private networking](https://render.com/docs/private-network), [private services](https://render.com/docs/private-services), and [web services](https://render.com/docs/web-services)
- [Render Postgres and Key Value service types](https://render.com/docs/service-types), [persistent disks](https://render.com/docs/disks), and [Docker services](https://render.com/docs/docker)

These provider documents describe available platform behavior. They do not establish that this application has been deployed, configured, or accepted on either provider.
