"""Parcel lifecycle rules for Tawseel.

Pure Python: do not import fastapi, starlette, pydantic or sqlalchemy here
(a hidden test checks). Keep the names below exactly as they are.
"""
from dataclasses import dataclass, replace
from enum import StrEnum

MAX_ATTEMPTS = 3


class ParcelState(StrEnum):
    CREATED = "created"
    OUT_FOR_DELIVERY = "out_for_delivery"
    FAILED_ATTEMPT = "failed_attempt"
    DELIVERED = "delivered"
    RETURNED = "returned"


class EventType(StrEnum):
    DISPATCH = "dispatch"
    DELIVER = "deliver"
    FAIL = "fail"
    RETURN = "return"


class InvalidTransition(Exception): ...


@dataclass(frozen=True)
class Parcel:
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: ParcelState = ParcelState.CREATED
    attempts: int = 0


TRANSITIONS: dict[tuple[ParcelState, EventType], ParcelState] = {
    (ParcelState.CREATED, EventType.DISPATCH): ParcelState.OUT_FOR_DELIVERY,
    (ParcelState.OUT_FOR_DELIVERY, EventType.DELIVER): ParcelState.DELIVERED,
    (ParcelState.OUT_FOR_DELIVERY, EventType.FAIL): ParcelState.FAILED_ATTEMPT,
    (ParcelState.FAILED_ATTEMPT, EventType.RETURN): ParcelState.RETURNED,
}


def apply_event(parcel: Parcel, event: EventType) -> Parcel:
    # Handle the special case of dispatching a parcel that has failed attempts. HA
    if (parcel.state, event) == (ParcelState.FAILED_ATTEMPT, EventType.DISPATCH):
        if parcel.attempts >= MAX_ATTEMPTS:
            raise InvalidTransition("cannot dispatch: delivery attempts exhausted")
        return replace(parcel, state=ParcelState.OUT_FOR_DELIVERY, attempts=parcel.attempts + 1)
    next_state = TRANSITIONS.get((parcel.state, event))
    if next_state is None:
        raise InvalidTransition(f"{event.value} not allowed from {parcel.state.value}")
    return replace(parcel, state=next_state, attempts=parcel.attempts + (event is EventType.DISPATCH))