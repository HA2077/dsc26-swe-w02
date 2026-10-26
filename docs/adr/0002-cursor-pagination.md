# 2. Sequence-number cursors for listing parcels

## Status

Accepted

## Context

`GET /v1/parcels` pages in creation order and consumers can filter by `state`. A consumer typically walks a filtered list over several requests, and parcels change state *while* it walks (couriers dispatch and deliver in real time). Offset pagination counts positions in the current filtered result, so when an earlier item leaves the filter mid-walk, every later item shifts and the consumer silently skips or repeats one. We also need cursors to be opaque and to fail closed: a cursor we did not issue must be rejected, not guessed at. The pull-the-other-way forces: offsets are simpler to reason about, and cursors based on the in-memory store die with the process.

## Decision

We will use sequence-number cursors: each parcel gets a monotonically increasing creation `seq`; `next_cursor` is the `seq` of the page's last item; each page returns matching parcels with `seq > cursor`, ordered by `seq`; `next_cursor` is `null` on the page containing the final match (no extra empty page). Cursors not issued by the same app instance return 400 problem+json. Bad `limit`/`state` query parameters return 422, not 400.

## Consequences

It was easier to have a cursor anchor to a parcel's position in creation order not to a position in the filtered result, so items changing state mid-walk neither shift nor shift anything else the surviving-in-filter items neither skip nor repeat. 
Harder: the cursors are bound to the in-memory store, so a process restart invalidates them and every client must restart its walk; each page is a linear scan over all parcels fine at Week-2 scale, but the store would need an index or a real database before this serves production traffic.