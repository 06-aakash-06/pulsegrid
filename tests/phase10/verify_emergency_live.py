"""Exercise the Emergency lifecycle through owner APIs on fictional fixtures."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sys
import uuid

from prepare_acceptance import ROOT, BASE, AcceptanceActor, isolated


def main():
    isolated()
    fixture = ROOT / "secrets/phase10/fixture.json"
    state = json.loads(fixture.read_text())
    resources = state["resources"]
    run_id = uuid.UUID(state["run"])
    actors = {}
    for role in ("patient", "other", "doctor", "emergency_staff"):
        actor = AcceptanceActor(BASE, state["actors"][role])
        actor.login()
        actors[role] = actor

    def key(name):
        return str(uuid.uuid5(run_id, "emergency-live-" + name))

    def save_fixture():
        fixture.write_text(json.dumps(state, indent=2))
        fixture.chmod(0o600)

    patient = actors["patient"]
    other = actors["other"]
    doctor = actors["doctor"]
    staff = actors["emergency_staff"]
    patient_id = patient.data["profile"]["id"]
    base_path = "/api/v1/emergencies"
    evidence = {"isolated_project": "pulsegrid-audit-20261025", "checks": []}
    evidence_path = ROOT / "docs/phase-10/evidence/emergency-live.json"
    prior_evidence = (
        json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    )

    def record(label, status, **details):
        evidence["checks"].append({"check": label, "status": status, **details})

    def submit(label, description):
        resource_key = label + "_request"
        body = {
            "patient_id": patient_id,
            "description": description,
            "reported_urgency": "urgent",
            "synthetic_contact": "Phase10 synthetic contact",
        }
        if resource_key not in resources:
            resources[resource_key] = patient.call(
                "POST", base_path, body, key=key(label + "-submit"), codes=(201,)
            )[0]
            save_fixture()
        return resources[resource_key]

    main_request = submit("lifecycle", "Fictional Phase10 Emergency lifecycle")
    request_id = main_request["id"]
    request_path = f"{base_path}/{request_id}"
    repeated = patient.call(
        "POST",
        base_path,
        {
            "patient_id": patient_id,
            "description": "Fictional Phase10 Emergency lifecycle",
            "reported_urgency": "urgent",
            "synthetic_contact": "Phase10 synthetic contact",
        },
        key=key("lifecycle-submit"),
        codes=(201,),
    )[0]
    assert repeated["id"] == request_id
    record("patient submission and idempotent replay", "PASS", state=main_request["state"])

    staff.call("GET", base_path + "?limit=100")
    patient_detail, etag, _ = patient.call("GET", request_path)
    assert patient_detail["id"] == request_id
    _, _, cross_patient_status = other.call("GET", request_path, codes=(404,))
    _, _, unauthorized_status = doctor.call(
        "PATCH",
        request_path + "/priority",
        {"assigned_priority": 1, "reason": "Unauthorized synthetic check"},
        etag,
        codes=(403,),
    )
    record(
        "patient ownership and staff-role authorization",
        "PASS",
        other_patient_status=cross_patient_status,
        doctor_priority_status=unauthorized_status,
    )

    if patient_detail["state"] == "submitted":
        prioritized = staff.call(
            "PATCH",
            request_path + "/priority",
            {"assigned_priority": 2, "reason": "Synthetic triage acceptance"},
            etag,
        )[0]
    else:
        prioritized, etag, _ = staff.call("GET", request_path)
    assert prioritized["state"] in {"triaged", "claimed", "processing", "resolved"}
    assert prioritized["assigned_priority"] == 2
    _, _, stale_status = staff.call(
        "PATCH",
        request_path + "/priority",
        {"assigned_priority": 3, "reason": "Stale synthetic version check"},
        f'"{main_request["version"]}"',
        codes=(412,),
    )
    record("priority assignment and stale ETag rejection", "PASS", stale_status=stale_status)

    current, current_etag, _ = staff.call("GET", request_path)
    if current["state"] == "triaged":
        claimed = staff.call(
            "POST",
            request_path + "/claim",
            {},
            current_etag,
            key("lifecycle-claim"),
        )[0]
    else:
        claimed = current
    assert claimed["state"] in {"claimed", "processing", "resolved"}
    _, _, wrong_actor_status = doctor.call(
        "POST",
        request_path + "/transitions",
        {"state": "processing", "reason": "Unauthorized synthetic transition"},
        claimed.get("version") and f'"{claimed["version"]}"',
        key("unauthorized-processing"),
        codes=(403,),
    )
    record("claim and processing-role authorization", "PASS", doctor_transition_status=wrong_actor_status)

    claimed, claimed_etag, _ = staff.call("GET", request_path)
    if claimed["state"] == "claimed":
        processing_body = {"state": "processing", "reason": "Synthetic staff began processing"}
        processing_key = key("lifecycle-processing")
        processing = staff.call(
            "POST", request_path + "/transitions", processing_body,
            claimed_etag, processing_key,
        )[0]
        replay = staff.call(
            "POST", request_path + "/transitions", processing_body,
            claimed_etag, processing_key,
        )[0]
        assert replay == processing
    else:
        processing, _, _ = staff.call("GET", request_path)
    assert processing["state"] in {"processing", "resolved"}
    processing, processing_etag, _ = staff.call("GET", request_path)
    if processing["state"] == "processing":
        resolved = staff.call(
            "POST",
            request_path + "/transitions",
            {"state": "resolved", "reason": "Synthetic Emergency request resolved"},
            processing_etag,
            key("lifecycle-resolve"),
        )[0]
    else:
        resolved = processing
    assert resolved["state"] == "resolved"
    history = staff.call("GET", request_path + "/history?limit=100")[0]
    lifecycle_states = [item["new_state"] for item in history["items"]]
    assert lifecycle_states == ["submitted", "triaged", "claimed", "processing", "resolved"]
    record("claim, processing, resolution and audited history", "PASS", states=lifecycle_states)

    cancel_request = submit("cancellation", "Fictional Phase10 cancellation")
    cancel_path = f"{base_path}/{cancel_request['id']}"
    cancel_detail, cancel_etag, _ = patient.call("GET", cancel_path)
    if cancel_detail["state"] == "submitted":
        cancelled = patient.call(
            "POST",
            cancel_path + "/transitions",
            {"state": "cancelled", "reason": "Synthetic patient cancellation"},
            cancel_etag,
            key("cancellation-cancel"),
        )[0]
    else:
        cancelled = cancel_detail
    assert cancelled["state"] == "cancelled"
    record("patient-owned cancellation", "PASS", state=cancelled["state"])

    race_request = submit("version_race", "Fictional Phase10 version race")
    race_path = f"{base_path}/{race_request['id']}"
    race_detail, race_etag, _ = staff.call("GET", race_path)
    previous_race = next(
        (
            check
            for check in prior_evidence.get("checks", [])
            if check.get("check") == "concurrent same-version priority writes"
        ),
        None,
    )
    if race_detail["state"] == "submitted":
        second_staff_client = AcceptanceActor(BASE, state["actors"]["emergency_staff"])
        second_staff_client.login()
        from threading import Barrier

        barrier = Barrier(2)

        def competing_priority(actor, priority):
            barrier.wait(timeout=5)
            return actor.call(
                "PATCH",
                race_path + "/priority",
                {"assigned_priority": priority, "reason": "Concurrent synthetic version race"},
                race_etag,
                codes=(200, 412),
            )[2]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda args: competing_priority(*args),
                    ((staff, 1), (second_staff_client, 2)),
                )
            )
    else:
        assert race_detail["state"] == "triaged" and previous_race is not None
        results = previous_race["response_statuses"]
    assert sorted(results) == [200, 412], results
    record("concurrent same-version priority writes", "PASS", response_statuses=sorted(results))

    evidence["request_ids"] = {
        "lifecycle": request_id,
        "cancellation": cancel_request["id"],
        "version_race": race_request["id"],
    }
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print("PASS Emergency lifecycle, cancellation, ownership, authorization, idempotency and version concurrency", flush=True)


if __name__ == "__main__":
    main()
