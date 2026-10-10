"""Pure monetary and request-shape checks for Billing."""

import pytest
from pydantic import ValidationError

from billing_service.cursor import decode_cursor, encode_cursor, filter_hash
from billing_service.ledger import calculate_totals
from billing_service.schemas import ChargeImport, InvoiceCreate, PaymentCreate, TariffCreate


def test_integer_minor_unit_calculation_is_exact():
    subtotal, total = calculate_totals(
        [
            {"quantity": 3, "unit_amount_minor": 125},
            {"quantity": 2, "unit_amount_minor": 40},
        ]
    )

    assert subtotal == 455
    assert total == 455


def test_calculation_rejects_values_outside_safe_integer_range():
    with pytest.raises(ValueError, match="safe integer range"):
        calculate_totals([{"quantity": 1_000_000, "unit_amount_minor": 9_007_199_254_741}])


@pytest.mark.parametrize(
    "body",
    [
        {"charge_code": "consultation", "unit_amount_minor": 1.25, "currency": "INR"},
        {"charge_code": "medicine:0", "unit_amount_minor": 1, "currency": "INR"},
        {"charge_code": "consultation", "unit_amount_minor": True, "currency": "INR"},
        {"charge_code": "consultation", "unit_amount_minor": 1, "currency": "USD"},
        {"charge_code": "consultation", "unit_amount_minor": 1, "currency": "INR", "price": 1},
    ],
)
def test_tariff_request_rejects_float_boolean_unknown_or_invalid_money(body):
    with pytest.raises(ValidationError):
        TariffCreate.model_validate(body)


def test_charge_import_requires_sources_and_distinct_dispensing_ids():
    with pytest.raises(ValidationError):
        ChargeImport.model_validate({"dispensing_ids": []})
    with pytest.raises(ValidationError):
        ChargeImport.model_validate({"dispensing_ids": ["12", "12"]})


def test_invoice_ids_are_decimal_strings_not_numbers():
    with pytest.raises(ValidationError):
        InvoiceCreate.model_validate({"appointment_id": 12, "currency": "INR"})


def test_simulated_payment_rejects_real_payment_fields():
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate(
            {
                "amount_minor": 100,
                "currency": "INR",
                "simulated_outcome": "success",
                "card_number": "not-accepted",
            }
        )


def test_cursor_is_bound_to_filters_and_authorization_scope():
    from datetime import datetime, timezone

    scope_hash = filter_hash({"status": "open"}, "patient:7")
    cursor = encode_cursor(datetime(2026, 10, 11, tzinfo=timezone.utc), 99, scope_hash)

    assert decode_cursor(cursor, scope_hash) == (datetime(2026, 10, 11, tzinfo=timezone.utc), 99)
    with pytest.raises(Exception):
        decode_cursor(cursor, filter_hash({"status": "paid"}, "patient:7"))
