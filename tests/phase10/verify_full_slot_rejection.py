"""Check one occupied-slot collision through live Appointment owner APIs."""
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
    for role in ("patient", "other"):
        actor = AcceptanceActor(BASE, state["actors"][role])
        actor.login()
        actors[role] = actor

    occupied = {
        value["slot_id"]
        for value in resources.values()
        if isinstance(value, dict) and "slot_id" in value
    }
    now = datetime.now(timezone.utc)
    available = next(
        slot
        for slot in resources["slots"]
        if slot["id"] not in occupied
        and datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00")) > now
    )
    key = str(uuid.uuid5(run_id, "phase10-full-slot-collision"))
    primary = actors["patient"]
    secondary = actors["other"]
    body = {
        "patient_id": primary.data["profile"]["id"],
        "slot_id": available["id"],
        "expected_schedule_revision": resources["decision"]["revision"],
    }
    booked = primary.call(
        "POST", "/api/v1/appointments", body, key=key, codes=(201,)
    )[0]
    assert booked["slot_id"] == available["id"]
    conflict_body = {
        **body,
        "patient_id": secondary.data["profile"]["id"],
    }
    conflict, _, status = secondary.call(
        "POST",
        "/api/v1/appointments",
        conflict_body,
        key=str(uuid.uuid5(run_id, "phase10-full-slot-collision-replay")),
        codes=(409,),
    )
    assert conflict["error"]["code"] == "slot_occupied"
    evidence = {
        "isolated_project": "pulsegrid-audit-20261025",
        "slot_id": available["id"],
        "first_booking_status": 201,
        "second_patient_status": status,
        "second_patient_error": conflict["error"]["code"],
        "retained_records_touched": False,
    }
    (ROOT / "docs/phase-10/evidence/full-slot-rejection.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print("PASS occupied slot rejected for a second fictional patient", flush=True)


if __name__ == "__main__":
    main()
