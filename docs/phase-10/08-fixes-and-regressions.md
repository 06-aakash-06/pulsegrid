# Phase 10 fixes and regression evidence

## P10-01 — Redis admission Lua AOF replay (fixed)

Reproduced with separate pinned Redis containers, no network and synthetic key/value. Default ACL was `off` but denied the script's AOF rewrite effects (`MULTI`, `SELECT`, `HSET`, `PEXPIREAT`, `EXEC`, and expired-key `DEL`) during loading. The actual Redis replica surfaced AOF NOPERM during a restart. Minimal repair adds only offline replay primitives on the exact admission key prefix to disabled `default`; runtime admission-user permissions/credential remain unchanged. Dedicated before/after test proves persisted hash/expiry, no default authentication and namespace write denial. Real isolated/retained Redis restarts read AOF without NOPERM. Local commit `2775afb fix: preserve admission Lua state during Redis AOF replay`.

## P10-02 — Patient validation for a Doctor grant (fixed)

Before: Patient `POST /api/v1/records/access-grants` rejected a valid active Doctor grantee as 422; correlated request showed Records' delegated Patient could only ask staff-status about themself. Expected contract already allowed a patient to grant their historical records to an active Doctor. The Patient internal leaf now permits delegated self-patients to validate another target only when target is an active Doctor, while keeping current Patient role/profile/delegation checks. Other staff, disabled Doctors and non-patient delegation remain denied. Five PostgreSQL regression cases cover allowed Doctor, three invalid target cases and invalid actor. Before: 1 fail, 4 pass in focused selection; after: full affected Patient suite 205 passed. Deployed first in isolated Patient, then only the retained Patient image/container with preserved data and a rollback image tag; no migration. Browser grant creation, Doctor history 200 and browser revocation followed by Doctor history 404 pass. Commit `21e9e1c fix: validate Doctor grantees under delegated patient authority`.

## Configuration guard

Tempo's query/worker bounds and automatic 0.8 memory guard are verified against live `/status/config` and the completed ten-minute observation; the memory ceiling remains the existing 512 MiB. Measurements and Collector-loss limits are recorded in `02-runtime-stability.md`. Commit `3fff749 fix: bound Tempo resource concurrency` contains this configuration change. Do not call old restart causes eliminated.

The original consultation 504 and Surge 503 were reconstructed with exact correlation/trace evidence in `02-runtime-stability.md`. One later nonfinal helper observed a Surge 503 but did not preserve request/trace IDs; the corrected bounded probe returned NORMAL/200 for 8/8 reads and retrieved all eight traces. Neither bounded sample supports a root-cause fix or zero-error claim. No timeout was inflated and failure responses remain fail-closed.

The queue-recall first request returned 422 because this harness omitted the required audited `reason`. The corrected request passed; this was a harness-contract error, not a product defect. It is not counted as a product regression.
