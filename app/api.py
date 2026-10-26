"""HTTP layer for the Tawseel parcel service.

The HTTP layer translates requests into calls to app.domain; the domain decides.
See README.md for the four operations, their operationIds and their errors.
"""
import itertools  # For generating parcel IDs.

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
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


class PageOut(BaseModel):
    items: list[ParcelOut]
    next_cursor: str | None


_PROBLEM_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "loc": {"type": "array", "items": {"type": "string"}},
                    "msg": {"type": "string"},
                },
                "required": ["loc", "msg"],
            },
        },
    },
    "required": ["type", "title", "status"],
}


def _problem(
    status: int,
    title: str,
    type_: str = "about:blank",
    errors: list[dict] | None = None,
) -> JSONResponse:
    content: dict = {"type": type_, "title": title, "status": status}
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content=content,
    )


def create_app() -> FastAPI:
    """Return a NEW FastAPI app with its own empty in-memory store.

    Tests call this once per test, so nothing may be shared between two apps
    (no module-level dicts or counters for parcels).
    """
    app = FastAPI(title="Tawseel Parcel API")
    parcels: dict[str, Parcel] = {}
    seq = itertools.count(1)
    seqs: dict[str, int] = {}   # parcel_id -> creation seq; the cursor's numbers
    issued: set[str] = set()    # cursors this app actually handed out

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _problem(422, "Validation failed", errors=errors)

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
        responses={
            409: {"description": "Duplicate merchant_ref", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
            422: {"description": "Invalid body", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
        },
    )
    def create_parcel(body: CreateBody) -> JSONResponse | dict:
        if duplicate_ref(body.merchant_ref):
            return _problem(409, "Duplicate merchant_ref", "duplicate-merchant-ref")
        p = Parcel(
            id=f"pcl_{(s := next(seq))}",
            merchant_ref=body.merchant_ref,
            cod_amount_piastres=body.cod_amount_piastres,
            address_text=body.address_text,
        )
        parcels[p.id] = p
        seqs[p.id] = s
        return JSONResponse(
            status_code=201,
            content=parcel_out(p),
            headers={"Location": f"/v1/parcels/{p.id}"},
        )

    @app.get(
        "/v1/parcels/{parcel_id}",
        operation_id="getParcel",
        response_model=ParcelOut,
        responses={
            404: {"description": "Parcel not found", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
        },
    )
    def get_parcel(parcel_id: str) -> JSONResponse | dict:
        p = parcels.get(parcel_id)
        if p is None:
            return _problem(404, "Parcel not found")
        return parcel_out(p)

    @app.get(
        "/v1/parcels",
        operation_id="listParcels",
        response_model=PageOut,
        responses={
            400: {"description": "Invalid cursor", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
            422: {"description": "Invalid query parameters", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
        },
    )
    def list_parcels(
        state: ParcelState | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = Query(default=None),
    ) -> dict:
        after = 0
        if cursor is not None:
            if cursor not in issued:
                return _problem(400, "Invalid cursor", "invalid-cursor")
            after = int(cursor)
        matches = sorted(
            (
                (seqs[p.id], p)
                for p in parcels.values()
                if seqs[p.id] > after and (state is None or p.state == state)
            ),
            key=lambda t: t[0],
        )
        page = matches[:limit]
        next_cursor = str(page[-1][0]) if len(matches) > limit else None
        if next_cursor is not None:
            issued.add(next_cursor)
        return {"items": [parcel_out(p) for _, p in page], "next_cursor": next_cursor}

    @app.post(
        "/v1/parcels/{parcel_id}/events",
        operation_id="recordParcelEvent",
        response_model=ParcelOut,
        responses={
            404: {"description": "Parcel not found", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
            409: {"description": "Invalid transition", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
            422: {"description": "Unknown or missing event type", "content": {"application/problem+json": {"schema": _PROBLEM_SCHEMA}}},
        },
    )
    def record_parcel_event(parcel_id: str, body: EventBody) -> JSONResponse | dict:
        p = parcels.get(parcel_id)
        if p is None:
            return _problem(404, "Parcel not found")
        try:
            updated = apply_event(p, body.type)
        except InvalidTransition:
            return _problem(409, "Invalid transition", "invalid-transition")
        parcels[parcel_id] = updated
        return parcel_out(updated)

    # FastAPI auto-declares a 422 for every operation with a path parameter,
    # but getParcel has no 422 in the contract; drop it from the schema.
    orig_openapi = app.openapi

    def custom_openapi() -> dict:
        if not app.openapi_schema:
            schema = orig_openapi()
            schema["paths"]["/v1/parcels/{parcel_id}"]["get"]["responses"].pop("422", None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi

    return app


app = create_app()