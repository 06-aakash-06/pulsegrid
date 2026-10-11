"""PostgreSQL-backed Phase 2 billing API checks."""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor

import psycopg


def _id() -> str:
    return str(secrets.randbelow(9_000_000_000_000_000_000) + 1)


def _appointment(env, *, patient_id: str | None = None) -> tuple[str, str]:
    appointment_id = _id()
    patient = patient_id or env.patient_id
    env.owners.appointments[appointment_id] = {
        "appointment_id": appointment_id,
        "patient_id": patient,
        "state": "confirmed",
        "version": 1,
    }
    return appointment_id, patient


def _create_invoice(env, *, patient_id: str | None = None, key: str | None = None):
    appointment_id, owner_id = _appointment(env, patient_id=patient_id)
    response = env.client.post(
        "/api/v1/billing/invoices",
        json={"appointment_id": appointment_id, "currency": "INR"},
        headers=env.headers("billing_staff", key=key or "invoice-create-key-000001"),
    )
    assert response.status_code == 201, response.text
    return response, appointment_id, owner_id


def _create_tariff(env, charge_code: str, unit_amount_minor: int, key: str):
    return env.client.post(
        "/api/v1/billing/tariffs",
        json={"charge_code": charge_code, "unit_amount_minor": unit_amount_minor, "currency": "INR"},
        headers=env.headers("billing_staff", key=key),
    )


def _add_dispensing(env, appointment_id: str, patient_id: str, medicine_id: str, quantity: int):
    dispensing_id = _id()
    source_item_id = _id()
    env.owners.dispensings[dispensing_id] = {
        "dispensing_id": dispensing_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "items": [
            {
                "source_item_id": source_item_id,
                "medicine_id": medicine_id,
                "charge_code": f"medicine:{medicine_id}",
                "quantity": quantity,
            }
        ],
        "version": 1,
    }
    return dispensing_id, source_item_id


def _db_scalar(env, sql: str, params=()):
    with psycopg.connect(env.database_url) as connection:
        return connection.execute(sql, params).fetchone()[0]


def test_duplicate_source_and_payment_replay_persist_once(billing_env):
    env = billing_env
    medicine_id = _id()
    tariff = _create_tariff(env, f"medicine:{medicine_id}", 125, "tariff-create-medicine-key-001")
    assert tariff.status_code == 201
    assert tariff.headers["etag"] == '"1"'

    invoice_response, appointment_id, patient_id = _create_invoice(
        env, key="invoice-create-source-test-001"
    )
    invoice = invoice_response.json()
    duplicate_invoice = env.client.post(
        "/api/v1/billing/invoices",
        json={"appointment_id": appointment_id, "currency": "INR"},
        headers=env.headers("billing_staff", key="invoice-create-duplicate-key-01"),
    )
    assert duplicate_invoice.status_code == 409
    assert duplicate_invoice.json()["error"]["code"] == "invoice_exists"
    dispensing_id, source_item_id = _add_dispensing(
        env, appointment_id, patient_id, medicine_id, quantity=2
    )
    charge_body = {"dispensing_ids": [dispensing_id]}
    charge_headers = env.headers(
        "billing_staff", key="charge-import-source-test-001", etag='"1"'
    )
    charged = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json=charge_body,
        headers=charge_headers,
    )
    assert charged.status_code == 200, charged.text
    assert charged.headers["etag"] == '"2"'
    charged_invoice = charged.json()
    assert charged_invoice["total_minor"] == 250
    assert charged_invoice["items"] == [
        {
            "id": charged_invoice["items"][0]["id"],
            "charge_code": f"medicine:{medicine_id}",
            "source_service": "pharmacy",
            "source_item_id": source_item_id,
            "quantity": 2,
            "unit_amount_minor": 125,
            "tariff_revision": 1,
        }
    ]

    replayed_charge = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json=charge_body,
        headers=charge_headers,
    )
    assert replayed_charge.status_code == 200
    assert replayed_charge.headers["etag"] == '"2"'
    assert replayed_charge.json() == charged_invoice
    changed_key_reuse = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json={"consultation_id": _id(), "dispensing_ids": [dispensing_id]},
        headers=charge_headers,
    )
    assert changed_key_reuse.status_code == 409
    assert changed_key_reuse.json()["error"]["code"] == "idempotency_key_reused"

    duplicate_source = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json=charge_body,
        headers=env.headers(
            "billing_staff", key="charge-import-source-test-002", etag='"2"'
        ),
    )
    assert duplicate_source.status_code == 200
    assert duplicate_source.headers["etag"] == '"2"'
    assert duplicate_source.json() == charged_invoice

    payment_body = {"amount_minor": 250, "currency": "INR", "simulated_outcome": "success"}
    payment_headers = env.headers(
        "patient", key="payment-success-idempotency-001", etag='"2"'
    )
    paid = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json=payment_body,
        headers=payment_headers,
    )
    assert paid.status_code == 201, paid.text
    assert paid.headers["etag"] == '"3"'
    assert paid.json() == {
        "id": paid.json()["id"],
        "invoice_id": invoice["id"],
        "amount_minor": 250,
        "currency": "INR",
        "status": "success",
        "version": 3,
    }
    replayed_payment = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json=payment_body,
        headers=payment_headers,
    )
    assert replayed_payment.status_code == 201
    assert replayed_payment.headers["etag"] == '"3"'
    assert replayed_payment.json() == paid.json()
    changed_payment_reuse = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json={"amount_minor": 100, "currency": "INR", "simulated_outcome": "success"},
        headers=payment_headers,
    )
    assert changed_payment_reuse.status_code == 409
    assert changed_payment_reuse.json()["error"]["code"] == "idempotency_key_reused"

    invoice_id_int = int(invoice["id"])
    assert _db_scalar(env, "SELECT count(*) FROM invoice_items WHERE invoice_id=%s", (invoice_id_int,)) == 1
    assert _db_scalar(env, "SELECT count(*) FROM payments WHERE invoice_id=%s", (invoice_id_int,)) == 1
    assert _db_scalar(env, "SELECT total_minor FROM invoices WHERE id=%s", (invoice_id_int,)) == 250
    assert _db_scalar(env, "SELECT paid_minor FROM invoices WHERE id=%s", (invoice_id_int,)) == 250
    assert _db_scalar(env, "SELECT status FROM invoices WHERE id=%s", (invoice_id_int,)) == "paid"
    assert _db_scalar(env, "SELECT count(*) FROM audit_entries WHERE chain_id='billing'") >= 4
    assert _db_scalar(env, "SELECT count(*) FROM outbox_events WHERE aggregate_id=%s AND published_at IS NULL", (invoice_id_int,)) >= 3


def test_decline_overpayment_and_later_charge_reopen_invoice(billing_env):
    env = billing_env
    consultation_tariff = _create_tariff(
        env, "consultation", 100, "tariff-consultation-key-0001"
    )
    assert consultation_tariff.status_code == 201
    invoice_response, appointment_id, patient_id = _create_invoice(
        env, key="invoice-create-transition-001"
    )
    invoice = invoice_response.json()
    consultation_id = _id()
    env.owners.consultations[consultation_id] = {
        "consultation_id": consultation_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "status": "finalized",
        "charge_code": "consultation",
        "quantity": 1,
        "version": 2,
    }
    charge = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json={"consultation_id": consultation_id, "dispensing_ids": []},
        headers=env.headers("billing_staff", key="consultation-import-key-001", etag='"1"'),
    )
    assert charge.status_code == 200
    assert charge.json()["total_minor"] == 100

    decline = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json={"amount_minor": 40, "currency": "INR", "simulated_outcome": "decline"},
        headers=env.headers("patient", key="payment-decline-key-000001", etag='"2"'),
    )
    assert decline.status_code == 201
    assert decline.json()["status"] == "declined"
    assert decline.json()["version"] == 3
    assert decline.headers["etag"] == '"3"'
    after_decline = env.client.get(
        f"/api/v1/billing/invoices/{invoice['id']}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert after_decline.json()["paid_minor"] == 0
    assert after_decline.json()["version"] == 3

    success = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json={"amount_minor": 100, "currency": "INR", "simulated_outcome": "success"},
        headers=env.headers("patient", key="payment-full-key-000001", etag='"3"'),
    )
    assert success.status_code == 201
    assert env.client.get(
        f"/api/v1/billing/invoices/{invoice['id']}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    ).json()["status"] == "paid"
    paid_invoice_attempt = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json={"amount_minor": 1, "currency": "INR", "simulated_outcome": "success"},
        headers=env.headers("patient", key="payment-after-paid-key-001", etag='"4"'),
    )
    assert paid_invoice_attempt.status_code == 409
    assert paid_invoice_attempt.json()["error"]["code"] == "overpayment"

    medicine_id = _id()
    assert _create_tariff(env, f"medicine:{medicine_id}", 10, "tariff-reopen-key-000001").status_code == 201
    dispensing_id, _ = _add_dispensing(env, appointment_id, patient_id, medicine_id, 1)
    add_later_charge = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json={"consultation_id": consultation_id, "dispensing_ids": [dispensing_id]},
        headers=env.headers("billing_staff", key="charge-reopen-after-paid-001", etag='"4"'),
    )
    assert add_later_charge.status_code == 200
    assert add_later_charge.json()["status"] == "open"
    assert add_later_charge.json()["total_minor"] == 110
    assert add_later_charge.json()["paid_minor"] == 100
    assert add_later_charge.json()["balance_minor"] == 10

    overpayment = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/payments",
        json={"amount_minor": 11, "currency": "INR", "simulated_outcome": "success"},
        headers=env.headers("patient", key="payment-over-balance-key-1", etag='"5"'),
    )
    assert overpayment.status_code == 409
    assert overpayment.json()["error"]["code"] == "overpayment"
    persisted = env.client.get(
        f"/api/v1/billing/invoices/{invoice['id']}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    ).json()
    assert persisted["paid_minor"] == 100
    assert persisted["balance_minor"] == 10


def test_source_service_outage_does_not_invent_charges(billing_env):
    env = billing_env
    medicine_id = _id()
    assert _create_tariff(env, f"medicine:{medicine_id}", 7, "tariff-outage-key-000001").status_code == 201
    invoice_response, appointment_id, patient_id = _create_invoice(env, key="invoice-outage-test-key-001")
    invoice_id = invoice_response.json()["id"]
    dispensing_id, _ = _add_dispensing(env, appointment_id, patient_id, medicine_id, 1)
    env.owners.failures["pharmacy"] = 503
    headers = env.headers("billing_staff", key="charge-source-outage-key-1", etag='"1"')
    unavailable = env.client.post(
        f"/api/v1/billing/invoices/{invoice_id}/charges",
        json={"dispensing_ids": [dispensing_id]},
        headers=headers,
    )
    assert unavailable.status_code == 503
    assert _db_scalar(env, "SELECT count(*) FROM invoice_items WHERE invoice_id=%s", (int(invoice_id),)) == 0
    assert _db_scalar(env, "SELECT total_minor FROM invoices WHERE id=%s", (int(invoice_id),)) == 0

    env.owners.failures.pop("pharmacy")
    retried = env.client.post(
        f"/api/v1/billing/invoices/{invoice_id}/charges",
        json={"dispensing_ids": [dispensing_id]},
        headers=headers,
    )
    assert retried.status_code == 200
    assert retried.json()["total_minor"] == 7


def test_draft_consultation_is_not_a_valid_charge_transition(billing_env):
    env = billing_env
    assert _create_tariff(env, "consultation", 100, "tariff-draft-source-key-01").status_code == 201
    invoice_response, appointment_id, patient_id = _create_invoice(
        env, key="invoice-draft-source-key-001"
    )
    invoice_id = invoice_response.json()["id"]
    consultation_id = _id()
    env.owners.consultations[consultation_id] = {
        "consultation_id": consultation_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "status": "draft",
        "charge_code": "consultation",
        "quantity": 1,
        "version": 1,
    }
    request_body = {"consultation_id": consultation_id, "dispensing_ids": []}
    missing_precondition = env.client.post(
        f"/api/v1/billing/invoices/{invoice_id}/charges",
        json=request_body,
        headers=env.headers("billing_staff", key="missing-if-match-charge-key-01"),
    )
    assert missing_precondition.status_code == 428
    rejected = env.client.post(
        f"/api/v1/billing/invoices/{invoice_id}/charges",
        json=request_body,
        headers=env.headers("billing_staff", key="draft-consultation-import-01", etag='"1"'),
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "source_not_finalized"
    assert _db_scalar(env, "SELECT count(*) FROM invoice_items WHERE invoice_id=%s", (int(invoice_id),)) == 0
    assert _db_scalar(env, "SELECT version FROM invoices WHERE id=%s", (int(invoice_id),)) == 1

    env.owners.consultations[consultation_id]["status"] = "finalized"
    accepted = env.client.post(
        f"/api/v1/billing/invoices/{invoice_id}/charges",
        json=request_body,
        headers=env.headers("billing_staff", key="finalized-consultation-import-01", etag='"1"'),
    )
    assert accepted.status_code == 200
    assert accepted.json()["total_minor"] == 100


def test_patient_ownership_current_authority_and_history_pagination(billing_env):
    env = billing_env
    own_one, _, _ = _create_invoice(env, key="invoice-own-history-key-001")
    own_two, _, _ = _create_invoice(env, key="invoice-own-history-key-002")
    other_patient = _id()
    foreign, _, _ = _create_invoice(
        env, patient_id=other_patient, key="invoice-foreign-history-key-01"
    )

    no_token = env.client.get("/api/v1/billing/invoices")
    assert no_token.status_code == 401
    wrong_role = env.client.get(
        "/api/v1/billing/tariffs",
        headers={"Authorization": "Bearer " + env.token("doctor")},
    )
    assert wrong_role.status_code == 403
    env.owners.authority_active = False
    revoked = env.client.get(
        "/api/v1/billing/tariffs",
        headers={"Authorization": "Bearer " + env.token("billing_staff")},
    )
    assert revoked.status_code == 403
    env.owners.authority_active = True

    hidden = env.client.get(
        f"/api/v1/billing/invoices/{foreign.json()['id']}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert hidden.status_code == 404
    wrong_filter = env.client.get(
        f"/api/v1/billing/invoices?patient_id={other_patient}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert wrong_filter.status_code == 404

    page_one = env.client.get(
        "/api/v1/billing/invoices?status=open&limit=1",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert page_one.status_code == 200
    assert len(page_one.json()["items"]) == 1
    cursor = page_one.json()["next_cursor"]
    assert cursor
    page_two = env.client.get(
        f"/api/v1/billing/invoices?status=open&limit=1&cursor={cursor}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert page_two.status_code == 200
    assert len(page_two.json()["items"]) == 1
    assert page_two.json()["items"][0]["id"] != page_one.json()["items"][0]["id"]
    changed_filter = env.client.get(
        f"/api/v1/billing/invoices?status=paid&cursor={cursor}",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert changed_filter.status_code == 400
    unknown_query = env.client.get(
        "/api/v1/billing/invoices?unexpected=true",
        headers={"Authorization": "Bearer " + env.token("patient")},
    )
    assert unknown_query.status_code == 422
    assert own_one.json()["id"] != own_two.json()["id"]


def test_concurrent_full_payments_never_exceed_balance(billing_env):
    env = billing_env
    assert _create_tariff(env, "consultation", 100, "tariff-concurrent-key-001").status_code == 201
    invoice_response, appointment_id, patient_id = _create_invoice(
        env, key="invoice-concurrent-test-key-01"
    )
    invoice = invoice_response.json()
    consultation_id = _id()
    env.owners.consultations[consultation_id] = {
        "consultation_id": consultation_id,
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "status": "finalized",
        "charge_code": "consultation",
        "quantity": 1,
        "version": 1,
    }
    charge = env.client.post(
        f"/api/v1/billing/invoices/{invoice['id']}/charges",
        json={"consultation_id": consultation_id, "dispensing_ids": []},
        headers=env.headers("billing_staff", key="charge-concurrent-key-0001", etag='"1"'),
    )
    assert charge.status_code == 200

    def pay(key):
        return env.client.post(
            f"/api/v1/billing/invoices/{invoice['id']}/payments",
            json={"amount_minor": 100, "currency": "INR", "simulated_outcome": "success"},
            headers=env.headers("patient", key=key, etag='"2"'),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, ["payment-concurrent-a-key-01", "payment-concurrent-b-key-01"]))
    assert sorted(result.status_code for result in results) == [201, 412]
    assert _db_scalar(env, "SELECT paid_minor FROM invoices WHERE id=%s", (int(invoice["id"]),)) == 100
    assert _db_scalar(env, "SELECT count(*) FROM payments WHERE invoice_id=%s AND status='success'", (int(invoice["id"]),)) == 1


def test_service_only_workflow_snapshot_tracks_financial_versions(billing_env):
    import time,jwt
    env=billing_env
    invoice_response,aid,pid=_create_invoice(env,key='phase3-snapshot-invoice-001')
    invoice=invoice_response.json()
    def headers(scope='workflow:billing-read'):
        now=int(time.time())
        token=jwt.encode(dict(iss='pulsegrid-service:appointment',aud='pulsegrid-internal:billing',
            sub='appointment',jti=_id(),iat=now,nbf=now,exp=now+60,token_use='service',scopes=[scope]),
            env.appointment_private_key,algorithm='RS256',headers={'kid':'appointment-test'})
        return {'Authorization':'Bearer '+token}
    path=f'/internal/v1/appointments/{aid}/workflow-snapshot?patient_id={pid}'
    result=env.client.get(path,headers=headers())
    assert result.status_code==200,result.text
    before=result.json()['snapshot']
    assert before['revision']>=2 and before['invoice']['balance_minor']==0
    assert before['invoice']['charge_source_keys']==[]
    assert env.client.get(path,headers=env.headers('patient')).status_code==401
    assert env.client.get(path,headers=headers('invoice:write')).status_code==403
    assert env.client.get(path.replace(pid,_id()),headers=headers()).status_code==404
    medicine=_id()
    assert _create_tariff(env,'medicine:'+medicine,125,'phase3-snapshot-tariff-001').status_code==201
    dispensing,source=_add_dispensing(env,aid,pid,medicine,2)
    charged=env.client.post(f"/api/v1/billing/invoices/{invoice['id']}/charges",json={'dispensing_ids':[dispensing]},
        headers=env.headers('billing_staff',key='phase3-snapshot-charges-001',etag=invoice_response.headers['etag']))
    assert charged.status_code==200,charged.text
    after=env.client.get(path,headers=headers()).json()['snapshot']
    assert after['revision']>before['revision']
    assert after['invoice']['total_minor']==250 and after['invoice']['balance_minor']==250
    assert after['invoice']['charge_source_keys']==[{'source_service':'pharmacy','source_item_id':source}]
