# System inventory and final runtime boundary

25 October 2026; local `main` `99fd31bce9001e48e7521b69d14551bae6d90dda`. Read this with the [scope decisions](00-scope-reconstruction.md) and [check boundaries](03-baseline-results.md).

## Services and API surface

Seven FastAPI owner packages share one PostgreSQL instance using separate logical databases and credentials. The live deployment has two Doctor API processes and one process for each other domain. All eight readiness requests returned 200 and reported their database available. This is a point-in-time dependency check, not a business-workflow test.

Live `/openapi.json` was retrieved directly from each domain container. Counts are method/path operations; they exclude hidden `/metrics` and framework documentation routes, include health and private paths, and count the Doctor schema once. Private routes are inventoried, not exposed by the gateway. Source hashes for all 223 Python files inside the seven service packages match their corresponding running container package files; installed libraries and component packages were not covered by that comparison.

| Domain | Operations | Public API | Internal API | Health | Short resolver |
|---|---:|---:|---:|---:|---:|
| patient | 21 | 14 | 5 | 2 | 0 |
| doctor | 16 | 12 | 2 | 2 | 0 |
| appointment | 50 | 40 | 7 | 2 | 1 |
| records | 18 | 13 | 3 | 2 | 0 |
| pharmacy | 21 | 16 | 3 | 2 | 0 |
| billing | 16 | 13 | 1 | 2 | 0 |
| emergency | 10 | 8 | 0 | 2 | 0 |

**Total: 152 operations.** Exact method/path evidence: [mounted OpenAPI inventory](evidence/live-openapi-inventory.json). A literal-decorator source count was not used because many routes use composed prefixes, f-strings and registration hooks.

| Domain | Owner implementation and persistence |
|---|---|
| Patient | `services/patient/patient_service/`: authentication, management, users/profiles/roles/refresh sessions, audit/outbox |
| Doctor | `services/doctor/doctor_service/`: profiles/specialties/proposals, revisions, cache projections and autocomplete |
| Appointment | `services/appointment/appointment_service/`: accepted schedules/slots/bookings; feature modules for waitlist/offers/check-in/queues/journeys/short links/Surge/Control Room; inbox/reconciliation |
| Records | `services/records/records_service/`: consultation drafts/finalization, immutable records/amendments, prescriptions/grants, clinical-hold coordination |
| Pharmacy | `services/pharmacy/pharmacy_service/`: catalog, batch inventory/movements, prescription allowances, reservations/dispensings, fulfillment snapshots and event publication |
| Billing | `services/billing/billing_service/`: tariffs, invoices/items/payments/source imports, insurance providers/rules/runs/estimates and event publication |
| Emergency | `services/emergency/emergency_service/`: requests, history, claim leases and authorized state transitions |

Every service has its own packaging, migrations and tests. The isolated live verification subsequently checked all seven actual Alembic heads, schema/constraint expectations, audit digests/chain heads and runtime-role restrictions, including 42 denied foreign-database connections. See [current evidence](evidence/schema-audit-isolation.json).

## Frontend route inventory

React/TypeScript/Vite mounts eight role workspaces and **35 workspace pages**, plus `/`, `/login`, `/register`, `/short-link`, base-path redirects and not-found handlers. `/s/{alias}` is a backend navigation resolver. Source: `frontend/src/app/App.tsx`, `navigation/workspaces.ts`, and `hospital/HospitalPage.tsx`.

| Role workspace | Routes |
|---|---|
| `/patient` | `/patient/dashboard`, `/patient/doctors`, `/patient/appointments`, `/patient/waitlist`, `/patient/check-in`, `/patient/queue`, `/patient/journey`, `/patient/records`, `/patient/prescriptions`, `/patient/pharmacy`, `/patient/billing`, `/patient/emergency` |
| `/doctor` | `/doctor/dashboard`, `/doctor/consultations`, `/doctor/queue`, `/doctor/prescriptions` |
| `/pharmacist` | `/pharmacist/dashboard`, `/pharmacist/inventory`, `/pharmacist/prescriptions` |
| `/billing` | `/billing/dashboard`, `/billing/invoices`, `/billing/payments`, `/billing/insurance` |
| `/emergency` | `/emergency/dashboard`, `/emergency/requests` |
| `/admin` | `/admin/dashboard`, `/admin/staff`, `/admin/doctors`, `/admin/control-room`, `/admin/traces`, `/admin/settings` |
| `/receptionist` | `/receptionist/dashboard`, `/receptionist/appointments` |
| `/ops` | `/ops/dashboard`, `/ops/traces` |

`hospital/HospitalPage.tsx` dispatches functional panels. `/admin/settings` deliberately renders an administration directory with links and explicit absence of a separate settings API. Old `emptyMessage` strings in navigation configuration are scaffold metadata, not proof that the mounted page is unconnected. Doctor clinical history/amendments mount indirectly inside `/doctor/prescriptions`. Profile editing is inside Reception's profile disclosure rather than a separate `/profile` route.

## Infrastructure and actual component integration

| Component | Current arrangement | Boundary |
|---|---|---|
| PostgreSQL | Shared instance, seven domain databases, per-service runtime/migration roles | Prototype shared failure domain; no cross-owner SQL |
| Redis admission | Dedicated Redis token-bucket and Surge state | Admission, not business correctness |
| Redis cache | `cache_a` and `cache_b`, Doctor projection cache, ring epoch and 128 virtual nodes per configured node | Placement/fallback, not cache replication |
| RabbitMQ | Native broker plus Pharmacy/Billing outbox publishers and Appointment inbox consumer | Two active event paths; retries/DLQ; fresh owner reconciliation |
| Traefik | Existing private owner routing and `/s/` resolver | Public API only; service internals use private DNS |
| Synthetic insurance fixtures | Three fixture hosts on reviewed internal networking | No arbitrary real provider crawling |
| Prometheus/blackbox | API/replica scraping and readiness probes | Observational, not write authority |
| Grafana | Version-controlled dashboards; Prometheus/Tempo sources | Infrastructure resource dashboard explicitly reports missing exporter |
| OTel Collector/Tempo | Optional trace pipeline and bounded queries | Tempo readiness does not establish stability |
| Locust/experiment harnesses | Existing `experiments/phase4/` and `experiments/phase8/` scripts/results | Measurements retain original configuration/trial limitations |
| Snowflake | Appointment short links and Billing insurance resources | Existing domain IDs retained |
| Autocomplete | Doctor names/specialties and Pharmacy medicines | Owner revisions, bounded trie and DB fallback |

Existing retained listeners are 5173/8080. The audit created a separate `pulsegrid-audit-20261025` Compose project on 19173/18880 with distinct networks/volumes; all shared binds were read-only. Bounded failures targeted only that project. After isolated validation, only retained Appointment was recreated to apply its repair, and the existing consumer received narrowly scoped DLX write permission. Unrelated `sdrecord-*` containers were untouched. No volume was removed. [Isolation](evidence/isolation-manifest.json), [repair application](evidence/retained-repair-application.json).

## Recent changes that alter the audit baseline

Since `698d31c`, merged changes rebuild Pharmacy/Billing/Emergency/Records/Control Room surfaces, introduce appointment tabs and richer physical navigation, add mock/demo execution modes, refine focus/reduced-motion/layout behavior, and repair stale selected states and review/confirmation flows. Later audit fixes and registration repairs are present through merge `99fd31b`.

`frontend/vite.config.ts` separates normal gateway-backed development/build, `VITE_MOCK_API` development middleware, and `VITE_DEMO_MOCK` browser-local static demo. The demo has synthetic browser-local persistence; it is not a deployed seven-service backend. Current real Patient registration retains Argon2id, while demo password verification is a separate browser implementation. Evidence obtained in one mode must not be attributed to the other.

## Baseline findings and limits

- Frontend: 159 tests pass; normal production build and its TypeScript check pass. Old README/checkpoint totals of 142/150/158 are historical.
- Running services: 8/8 readiness checks pass; sampled Doctor, Records and Control Room unauthenticated requests return 401.
- Monitoring: Prometheus, Grafana and Tempo readiness/health endpoints return 200. Tempo has a 512 MiB memory cap, current restart count 4 and recent scheduler warnings/errors. Long-term stability is unresolved.
- The runtime campaign reproduced and repaired real waitlist and broker defects; [the issue register](04-issue-register.md) has before/after evidence. It executed complete synthetic journeys, backend/DB/security suites and bounded cache/broker recovery. Physical QR, exhaustive control/viewport coverage and sustained telemetry stability remain open.
- `contracts/` is absent at this checkout. Markdown phase contracts and executable service schemas currently provide the interface specification. The originally proposed directory layout must not be reported as an existing executable contract suite.
- Deferred/uncertain product targets and deliberate reference omissions are recorded separately in the [gap register](04-issue-register.md).

Final retained checks: 8/8 readiness HTTP 200; all 223 service package files match checkout after deployment; both selected broker queues have one consumer and zero backlog/DLQ messages. See [final retained health](evidence/final-retained-health.json). A point-in-time healthy stack is not a soak result.
