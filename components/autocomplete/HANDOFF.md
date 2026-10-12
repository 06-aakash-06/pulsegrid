# Agent 7 handoff: Trie autocomplete

Base: `45273ea7fd1ea53e335942b6c38f2d81d38856ee`

Component package: `components/autocomplete/`, import name `pulsegrid_autocomplete`.

Shared package runtime dependencies: none; Python `>=3.12`. Doctor and Pharmacy adapters use only their current owner APIs/models/helpers and existing FastAPI/SQLAlchemy dependencies.

## Exports

- `Suggestion`, `Trie`, `IndexSnapshot`, `normalize_label`, `normalize_prefix`, `normalize_kinds`, `rank_suggestions`.
- `IndexLimits`, `IndexRegistry`, `build_snapshot`, async `rebuild`, `refresh_index`, and `refresh_loop`.
- Owner adapter `create_router(ports)`, `register_routes(app, ports)`, `read_revision(session)`, `load_snapshot(session)`, `prefix_query(session, normalized_prefix, kinds, limit)`, `filter_visible(session, suggestions)`, `schema_spec()`, `register_tables(metadata)`, and `health(ports=None)`.

`Trie.insert` upserts by `(kind,id)`, so using the same identity with a new label removes the old prefix path before inserting the new one. `Trie.remove(kind,id)` removes an exact source ID. `IndexSnapshot` seals the trie. Rebuilds construct a new snapshot away from route reads, compare source revision before and after loading and again before publish, retry a revision race at most twice, then atomically replace the registry pointer. A live snapshot is never mutated.

The compressed radix trie stores at most 20 ordered candidates per explicit node and kind. Search normalizes with NFKC, casefold, strip, and whitespace collapse, then ranks by `(normalized_label, kind, numeric_id)`. Duplicate `(kind,id)` values are suppressed. Snapshot admission defaults to 100,000 entries and a 64 MiB approximate Python-object estimate; the limit is configurable through the owner ports' `IndexLimits`. Above either limit, refresh marks the index degraded and routes use the owner DB fallback.

## Owner route integration

The coordinator owns entrypoint mounting and both revision migrations. Do not import the feature from current API routers until the reviewed migration and wheel/package wiring are ready.

1. Add `pulsegrid-autocomplete` to each owner image/package build from this directory, pinned to the reviewed artifact version. Keep the package isolated from all service ORM models.
2. Construct one `IndexRegistry` per Doctor and Pharmacy process. Supply an owner-local ports object with `index_registry`, `index_limits`, `observer`, `owner`, `authorize`, `read_session`, and the four owner storage functions.
3. Implement `authorize(request, roles, resource_id, write)` by calling that service's existing `authenticated_user` verifier. Preserve the current authenticated-directory behavior for all current user roles; do not add public routes or trust request headers. Authorization executes before parsing/search.
4. Make `read_session()` return an owner DB read-only, repeatable-read snapshot. Bind `read_revision`, `load_snapshot`, `prefix_query`, and `filter_visible` from the matching `doctor_service.features.autocomplete.storage` or `pharmacy_service.features.autocomplete.storage` module. Never share a session or query the other service database.
5. Mount Doctor `/api/v1/doctors/autocomplete` before its existing `/api/v1/doctors/{doctor_id}` literal collision. Mount Pharmacy `/api/v1/pharmacy/medicines/autocomplete` before `/api/v1/pharmacy/medicines/{medicine_id}`. `register_routes` only adds paths to the supplied app; it does not modify the production app or add auth.
6. Start `refresh_loop(ports, stop_event)` in each owner's app lifespan. It performs an immediate initial build and then polls every five seconds. Stop and await the task during shutdown. A missing, stale, degraded, oversized, or revalidation-mismatched index runs `prefix_query`; owner DB errors continue through existing safe 503 handling. Responses have `Cache-Control: no-store`, and DB fallback has `index_version: null`.
7. Keep the user-visible routes and private metrics/health behind existing owner authentication and gateway policy. Metrics use only `owner`, `outcome`, and `backend` labels; prefixes, IDs, labels, and user data are never labels.

The revision migrations are coordinator-owned. The SQL adapters expect one row in `directory_revision` or `catalog_revision`, with `singleton BOOLEAN PRIMARY KEY CHECK(singleton)` and `revision BIGINT NOT NULL CHECK(revision >= 1)`. Seed revision 1. Doctor changes to `doctors`, `specialties`, and `doctor_specialties` bump the directory revision in the same transaction. Pharmacy changes to medicine names, active state, or catalog fields bump catalog revision in the same transaction; inventory-only writes do not. Runtime credentials need SELECT on the revision row and only the source tables listed by `schema_spec()`; migration/trigger ownership stays with the coordinator.

Doctor fallback reads active doctor names and the currently public specialty list. Pharmacy fallback reads active medicine names only. The frozen NFKC/casefold behavior cannot be reproduced portably by PostgreSQL's current `lower()`/stored normalized column, so the exact DB fallback fetches the active owner projection and applies the shared normalizer in Python. This is intentionally correctness-preserving and must be included in the coordinator's endpoint benchmark; no stock/price, staff contact, inactive, prescription, or patient fields enter the suggestion response.

## Verification and benchmark commands

Pure component tests can run without installing service dependencies:

```sh
PYTHONPATH=components/autocomplete/src python3 -m unittest discover -s components/autocomplete/tests -v
```

Owner route tests require the service's existing test extras and should run from each service root:

```sh
cd services/doctor && python -m pytest tests/phase4_autocomplete
cd services/pharmacy && python -m pytest tests/phase4_autocomplete
```

Synthetic algorithm benchmark commands and limits are documented in `experiments/phase4/autocomplete/README.md`. It includes trie, sorted prefix-range, and bounded CPU scan measurements. The HTTP + real PostgreSQL revision/revalidation benchmark is coordinator integration work because these routers are intentionally unmounted here.
