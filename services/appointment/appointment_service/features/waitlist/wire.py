from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from ...wire import Input, ID, Time, Version, Book, Cancel

Join = Book
Withdraw = Cancel


class Waitlist(Input):
    id: ID
    slot_id: ID
    patient_id: ID
    state: Literal['waiting', 'promoted', 'withdrawn', 'skipped']
    joined_at: Time
    promoted_appointment_id: ID | None
    skip_reason: Literal['inactive_patient', 'patient_overlap', 'slot_retired', 'window_closed'] | None
    version: Version


class Page(Input):
    items: list[Waitlist]
    next_cursor: str | None


class SlotStatus(Input):
    slot_id: ID
    waiting_count: Annotated[StrictInt, Field(ge=0)]
    promotion_pending: bool = Field(strict=True)
    accepted_revision: Version
    observed_at: Time


class Eligibility(Input):
    patient_id: ID
    active: bool = Field(strict=True)
    version: Annotated[StrictInt, Field(ge=0, le=9007199254740991)]

    @model_validator(mode='after')
    def missing_is_inactive(self):
        if self.version == 0 and self.active:
            raise ValueError('Missing identity cannot be active')
        return self


class EligibilityBatch(Input):
    items: list[Eligibility] = Field(min_length=1, max_length=50)
    observed_at: Time

    @model_validator(mode='after')
    def distinct(self):
        if len({i.patient_id for i in self.items}) != len(self.items):
            raise ValueError('Duplicate identity')
        return self
