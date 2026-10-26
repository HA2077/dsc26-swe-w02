# AI usage

Keep all three headings exactly as they are. If this file is missing or any heading is
missing, the grader stops and gives 0 ("AI_USAGE.md missing or incomplete"). The content
is not scored, but your Track Mentor reads it and the W8 defence can ask about it.

## Tools

opencode (CLI agent running the GLM model) was used to implement `app/domain.py` and
`app/api.py` and to write these two ADRs working one endpoint at a time. Each step was
run against the public tests and an extra sanity script for (page walks, error shapes,
OpenAPI table checks) before moving on and every diff was reviewed by me before continuing.

## What AI got wrong

The first version of `apply_event` forgot to increment `attempts` on `created + dispatch`
(it bumped attempts only on the `failed_attempt + dispatch` retry path). 

I caught it and i fixed it with the agent.

A second catch: FastAPI silently injects a `422` response into the OpenAPI schema of every route with a path parameter, which would have left a plain-JSON 422 in the `getParcel` contract; comparing the spec against the expected status table exposed it and a small `custom_openapi` wrapper drops it.

## In my own words

1. Why does `listParcels` need a cursor rather than an offset?

In cursor based pagination the cursor is a pointer to a specific item in the dataset allowing for reliable pagination. On the other hand, offset pagination is relying on counting positions in the current filtered result which can lead to issues when items change state mid-walk. 

Overall with cursor pagination items changing state do not affect the position of other items preventing silent skips or repeats and thats what we needed in listParcels.

2. Which of your four operations would break the courier app if you renamed one field, and who would have to approve that change?

In recordParcelEvent if we change the type field the api would break the app because the app was expecting a different field name so the app wouldn't be able to send the data, 

And i think the whoever owns the API contract (tech lead / API owner) would approve this sensitive change because it got alot to change based on this change.