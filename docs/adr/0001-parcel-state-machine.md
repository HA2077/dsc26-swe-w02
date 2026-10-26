# 1. Parcel lifecycle as a pure-Python state machine

## Status

Accepted

## Context

A parcel follows a strict lifecycle: `created` → `out_for_delivery` → (`delivered` or `failed_attempt`) with `failed_attempt` going back out for delivery (at most 3 delivery attempts total) or to `returned`. Deliveries must not be undoable, retry attempts must be capped and `delivered`/`returned` are terminal. The courier app talks to our API, but it must not get to decide which transitions are legal — the rules live server-side, and both the courier app and the merchant integration depend on them being enforced consistently.

## Decision

We will encode the lifecycle as a transition table in `app/domain.py`: `apply_event(parcel, event)` looks up the `(state, event)` pair, returns a new immutable `Parcel` (via `dataclasses.replace`, never mutating its input), bumps `attempts` once per dispatch, and raises `InvalidTransition` for every pair not in the table thats including dispatching past `MAX_ATTEMPTS = 3`. The HTTP layer only translates requests 
*it never encodes* transition rules itself.

## Consequences

It was easier to test the rules as plain Python with no HTTP involved and the frozen dataclass makes accidental mutation impossible. 
It was harder adding a state or event means touching the table, the enums and the tests together; the API layer can never shortcut a transition even if it would be convenient for a client. The table approach was chosen over a chain-of-responsibility or class-per-state design because there are only 5 states and 4 events  a flat table is the smallest thing that shows every rule on one screen.