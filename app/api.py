"""HTTP layer for the Tawseel parcel service.

The HTTP layer translates requests into calls to app.domain; the domain decides.
See README.md for the four operations, their operationIds and their errors.
"""
import itertools # For generating parcel IDs.

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain import EventType, InvalidTransition, Parcel, ParcelState, apply_event


class CreateBody(BaseModel):
    merchant_ref: str = Field(min_length=1, max_length=64)
    cod_amount_piastres: int = Field(ge=0, le=5_000_000)
    address_text: str = Field(min_length=1, max_length=500)


class ParcelOut(BaseModel):
    id: str
    merchant_ref: str
    cod_amount_piastres: int
    address_text: str
    state: str
    attempts: int


class EventBody(BaseModel):
    type: EventType


def _problem(status: int, title: str, type_: str = "about:blank") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": type_, "title": title, "status": status},
    )


def create_app() -> FastAPI:
    """Return a NEW FastAPI app with its own empty in-memory store.

    Tests call this once per test, so nothing may be shared between two apps
    (no module-level dicts or counters for parcels).
    """
    app = FastAPI(title="Tawseel Parcel API")
    parcels: dict[str, Parcel] = {}
    seq = itertools.count(1)

    def parcel_out(p: Parcel) -> dict:
        return {
            "id": p.id,
            "merchant_ref": p.merchant_ref,
            "cod_amount_piastres": p.cod_amount_piastres,
            "address_text": p.address_text,
            "state": p.state.value,
            "attempts": p.attempts,
        }

    def duplicate_ref(ref: str) -> bool:
        return any(p.merchant_ref == ref for p in parcels.values())

    @app.post(
        "/v1/parcels",
        status_code=201,
        operation_id="createParcel",
        response_model=ParcelOut,
        responses={409: {"description": "Duplicate merchant_ref"}},
    )
    def create_parcel(body: CreateBody) -> JSONResponse | dict:
        if duplicate_ref(body.merchant_ref):
            return _problem(409, "Duplicate merchant_ref", "duplicate-merchant-ref")
        p = Parcel(
            id=f"pcl_{next(seq)}",
            merchant_ref=body.merchant_ref,
            cod_amount_piastres=body.cod_amount_piastres,
            address_text=body.address_text,
        )
        parcels[p.id] = p
        return JSONResponse(
            status_code=201,
            content=parcel_out(p),
            headers={"Location": f"/v1/parcels/{p.id}"},
        )

    @app.get(
        "/v1/parcels/{parcel_id}",
        operation_id="getParcel",
        response_model=ParcelOut,
        responses={404: {"description": "Parcel not found"}},
    )
    def get_parcel(parcel_id: str) -> JSONResponse | dict:
        p = parcels.get(parcel_id)
        if p is None:
            return _problem(404, "Parcel not found")
        return parcel_out(p)

    @app.post(
        "/v1/parcels/{parcel_id}/events",
        operation_id="recordParcelEvent",
        response_model=ParcelOut,
        responses={
            404: {"description": "Not found"},
            409: {"description": "Invalid transition"},
        },
    )
    def record_parcel_event(parcel_id: str, body: EventBody) -> JSONResponse | dict:
        p = parcels.get(parcel_id)
        if p is None:
            return _problem(404, "Not found")
        try:
            updated = apply_event(p, body.type)
        except InvalidTransition:
            return _problem(409, "Invalid transition", "invalid-transition")
        parcels[parcel_id] = updated
        return parcel_out(updated)

    return app


app = create_app()