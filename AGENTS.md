# Repository-wide agent instructions

## Scope and source of truth

PulseGrid is a synthetic, single-hospital educational prototype. Read README and the relevant docs before changing code. Phase 1.1 is documentation-only; do not implement functionality, install dependencies, start containers, create a remote or push during this phase. Current user authorization overrides this file; do not assume future roadmap phases are automatically authorized. Stop after the requested phase.

## Architecture and ownership

- Preserve seven independent FastAPI domains: patient, doctor, appointment, records, pharmacy, billing, emergency. React/TypeScript is the browser application. Stack: PostgreSQL, Redis, RabbitMQ, Traefik, Compose, Locust, Prometheus/Grafana, OpenTelemetry. No Kubernetes or unnecessary new technologies.
- Each service owns its schema, migrations, credentials and models. Never query another service's DB, use cross-database joins/FDWs/dblink, share ORM entities or bypass owner APIs/events. Ref IDs are not DB foreign keys or permission grants.
- Appointment owns accepted operational schedules, booking/waitlist/check-in/queue and journey projection. Doctor owns schedule proposals. Records authors clinical records/prescriptions; Pharmacy owns stock/fulfillment; Billing owns money; Emergency owns request triage; Patient owns identity/roles.
- Use atomic PostgreSQL transactions, locks and constraints for bookings, waitlist promotions, stock, payments and audit chains. Redis/cache/distributed locks never enforce booking correctness. Preserve documented lock ordering and idempotency under replicas.
- Mutation + outbox + audit + persisted idempotency response is one local transaction. Consumer inbox + effects + outgoing outbox is one local transaction; ack after commit. At-least-once delivery, no claims of broker exactly-once or global transactions.
- Never hold database locks across network calls. Use bounded deadlines, safe retries, circuit breakers and explicit pending/degraded states. Document source-version gaps and compensation/reconciliation.

## Naming and layout

Python files/functions/variables use snake_case, classes PascalCase; TypeScript values camelCase, components/types PascalCase. Singular lowercase service directories. REST/event fields use snake_case. APIs `/api/v1/<domain>`, internal `/internal/v1`; events `<domain>.<entity>.<action>.v1`. IDs serialize as decimal strings, timestamps UTC RFC 3339, currency as integer minor units plus code.

`services/<domain>/` owns domain code/migrations/workers/unit tests and package configuration. `frontend/` owns UI/client/config/UI tests, never authority or secrets. `contracts/` owns reviewed OpenAPI/event schemas. `infra/` owns deployment/configuration/secrets references, not business models. `tests/` owns cross-service tests; `experiments/` owns load/chaos/algorithm evaluation. `docs/` and root files are coordinated shared ownership. Do not create implementation directories until the applicable phase.

## API and compatibility

Validate identity, role and resource scope in every service. Use idempotency keys for retryable POST commands, If-Match for aggregate mutations, ETag for versions, stable bounded pagination and common safe error envelopes. Carry request/correlation IDs and W3C tracing through HTTP/events. Use service authentication plus delegated user scope on internal calls; no trusted public actor headers.

Additive optional API/event fields may remain v1; breaking removal, renaming, changed meaning or narrowed values requires a new version and documented migration. Keep old consumers supported until explicit retirement. Dual-published events preserve stable business effect identities. Never silently change enums, money units, status semantics or ownership. Update contract docs/schema and consumer checks in the same change. Avoid universal shared runtime domain packages that force lockstep deployment.

## Tests and verification

Use proportionate tests: unit tests for algorithms/state machines; PostgreSQL integration tests for actual locks/unique/exclusion constraints; contract/auth tests for cross-service interfaces; end-to-end tests for journeys; measured Locust experiments for performance. Mocked DB tests cannot prove concurrency correctness. Meaningful failure tests include duplicate/out-of-order events, broker outage/replay, cache outage, rollback/restart IDs, stale versions and token revocation. Synthetic-only chaos requires an explicit authorized scope, stop condition and recovery check.

Run only checks appropriate to the authorized phase. Phase 1.1 verifies files/links, architecture consistency, Git branch/commit/clean tree and absence of implementation artifacts; it does not claim runtime tests or Mermaid render verification unless actually executed. Always report exact checks run, pass/fail and skipped/unavailable checks. Never invent throughput, latency, collision, recovery or clinical validation results. Distinguish proposed settings from measured values.

## Security

Synthetic data exclusively. Never commit secrets, .env credentials, signing keys, real patient records, raw tokens or payment credentials. Hash passwords with a maintained Argon2id implementation; hash random refresh/short-link/tracking tokens at rest. Verify JWT issuer/audience/expiry/algorithm, apply RBAC plus ownership/care assignment/grants, and check current authority on privileged writes. Audit sensitive access and mutation; redact clinical content and secrets from logs/traces/metrics. Restrict crawler to synthetic allowlisted fixture hosts and bounded fetches. Do not imply clinical certification, emergency dispatch reliability, predictive triage or infrastructure HA.

## Documentation and changes

Keep Mermaid source diagrams, entity/constraint/API/event/state details and roadmap aligned. Label proposals and incomplete features explicitly. Explain trade-offs and degraded states in plain language. Document architecture decisions and compatibility impact before changing boundaries. Update relevant docs alongside behavior changes, except when concurrent ownership requires handing the change to the designated integrator.

Make focused changes within the request. Preserve existing content and conventions; do not redesign, reformat unrelated files, delete others' work or add unrelated dependencies/artifacts. Inspect working tree before editing/committing. Do not commit, publish or push without user authorization; Phase 1.1 explicitly authorizes its initial local documentation commit only. No remote is authorized.

## Parallel Git worktrees

When concurrent work is explicitly authorized, assign disjoint file ownership and a common reviewed base commit. Work on distinct ordinary branches; do not put `codex` in user-facing branch names. Only main's integrator changes shared root/docs/contracts/infra paths unless ownership is explicitly delegated. Agents inspect their own status, stage only owned files and report branch/base/latest commit and checks. Never reset/clean another worktree, overwrite another agent's changes, commit their files, or merge partial work without scoped authorization.

After Phase 1.1, Agent A owns only `services/{patient,doctor,appointment,records,pharmacy,billing,emergency}/`; Agent B owns only `frontend/`. Their colocated tests/metadata/READMEs remain in those paths. They both start from the same Phase 1.1 commit. Neither scaffold task starts until requested. Shared executable contracts and infrastructure are later integrator work.
