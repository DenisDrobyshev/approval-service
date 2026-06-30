# DESIGN — approval-service

A focused design note covering the data model, service boundaries,
idempotency, events/integration and the trade-offs taken.

## 1. Service boundaries

`approval-service` owns exactly one thing: **the lifecycle of an approval
request and its final decision.** It is deliberately small.

**Inside the boundary**
- Creating approval requests, listing/reading them, and recording a final
  decision (approve / reject / cancel).
- The integrity rules around that lifecycle: tenant isolation, idempotency,
  the state machine, the audit trail and the outbox.

**Outside the boundary (referenced only by id)**
- Publications, scenarios, edits, "external" sources → `sourceType` + `sourceId`.
- Users (`reviewerUserIds`, the acting user) and workspaces.
- Real authentication/authorization issuer (a stub stands in locally).
- Anything that owns content, media, storage or provider integrations.

The service never fetches, stores or echoes the *content* behind an id. It
keeps opaque identifiers plus a human `title`/`description`. This is what
makes the "no secrets/tokens/emails/URLs leak" rule natural to honour: the
service simply never ingests that class of data.

## 2. Data model

Four tables, all scoped by `workspace_id`.

### `approval_requests` — the aggregate
| column | type | notes |
|---|---|---|
| `id` | `str` PK | `req_<uuid4hex>` |
| `workspace_id` | `str` | tenant key, indexed |
| `source_type` | `str` | `publication \| scenario \| edit \| external` |
| `source_id` | `str` | external id |
| `title` | `str` | |
| `description` | `str?` | |
| `reviewer_user_ids` | `json` | list of external user ids |
| `status` | `str` | `pending \| approved \| rejected \| cancelled` |
| `decision_comment` | `str?` | set on approve |
| `decision_reason` | `str?` | set on reject/cancel |
| `decided_by_user_id` | `str?` | who decided |
| `decided_at` | `datetime?` | |
| `created_by_user_id` | `str` | |
| `created_at` / `updated_at` | `datetime` | |

Indexes: `workspace_id`, `status`, and composite `(workspace_id, created_at)`
(list ordering) and `(workspace_id, status)` (filtered lists).

### `idempotency_keys` — dedup store
`(workspace_id, idempotency_key)` is **unique**. Stores the
`request_fingerprint` (hash of method+path+body), the original
`response_status_code` and `response_body`, and the `target_id`.

### `audit_log` — immutable trail
One row per successful change: `actor_user_id`, `action`
(`created/approved/rejected/cancelled`), `from_status`, `to_status`, plus
redacted `details`. Append-only by convention.

### `outbox_events` — transactional outbox
One row per change: `aggregate_id`, `event_type`, `event_version`, a curated
`payload`, and `published_at` (NULL until relayed). Written in the same
transaction as the aggregate change.

### State machine

```
                 approve ─▶ approved   (final)
   pending ──────reject  ─▶ rejected   (final)
                 cancel  ─▶ cancelled  (final)
```

`pending` is the only non-final state. Any decision on a final state returns
`409` and changes nothing — this is the "no second final state" rule. The
check is `RequestStatus.is_final`, evaluated against the freshly loaded row
inside the transaction.

## 3. Multi-tenant isolation

Two layers, defence in depth:

1. **At the edge** — the auth dependency requires `X-Workspace-Id` to equal
   the path `{workspace_id}`; a mismatch is `403` before any query runs.
2. **In the data layer** — every read/write filters on `workspace_id`.
   Fetching another workspace's `request_id` simply matches no row and returns
   `404`, so existence isn't even leaked across tenants.

Idempotency keys are scoped per workspace, so the same key in two workspaces
never collides.

## 4. Idempotency / handling repeats

Mutating endpoints accept an optional `Idempotency-Key` header.

- On a keyed request we compute a **fingerprint** = `sha256(method + path +
  canonical-json(body))`.
- If `(workspace_id, key)` already exists:
  - **same fingerprint** → replay the stored status + body (a true retry);
  - **different fingerprint** → `409 idempotency_key_reuse` (the key was
    reused for a different request — fail loudly instead of returning the
    wrong result).
- Otherwise we process the request and, **in the same transaction**, insert
  the idempotency row alongside the aggregate change, audit entry and event.
- **Concurrency**: two simultaneous retries both pass the initial lookup; the
  unique constraint lets exactly one commit. The loser catches the
  `IntegrityError`, rolls back (discarding its duplicate) and replays the
  winner's stored response. So a retried create yields one row and one
  consistent response.

This also makes decisions safe to retry: a re-sent `approve` with the same key
replays the original `200` instead of hitting the state-machine `409`.

## 5. Events & integration

A **transactional outbox** prepares the service for event-driven integration
without coupling it to a broker today:

- Each successful change appends an `outbox_events` row in the same DB
  transaction as the change itself. Either both land or neither does — no lost
  or phantom events.
- Event types: `approval_request.created / .approved / .rejected / .cancelled`,
  each carrying `event_version` for forward-compatible evolution.
- A future relay process (or Debezium / polling publisher) reads rows where
  `published_at IS NULL`, ships them to Kafka/SNS/etc., and stamps
  `published_at`. Consumers should treat delivery as **at-least-once** and
  dedupe on event `id`.

**Event payloads are curated and redacted** (see `app/events.py`): identifiers,
status, reviewer ids, decision actor/time, and a *redacted* `title` and
decision comment/reason. `description` and any raw/provider data are excluded.
Consumers that need full detail call the API with their own credentials.

## 6. Not leaking secrets

The product around this service handles tokens, emails, storage keys, signed
URLs and provider payloads. This service avoids leaking them by:

- **Never ingesting them** — it stores only ids + title/description.
- **Logs** — the access log records method, path, status, latency and a
  correlation id only; never headers or bodies. A `RedactionFilter`
  (`app/logging_config.py`) scrubs every log record of emails, bearer tokens,
  API-key shapes, JWTs and URLs as a backstop. (You can see it in action: even
  uvicorn's "running on http://…" line comes out redacted.)
- **Events** — curated whitelist + redaction of free text (above).
- **Errors** — a single envelope `{ "error": { "code", "message" } }`; the
  validation handler strips the echoed `input`, and unhandled exceptions return
  an opaque `500` while the detail is logged internally.

## 7. Known trade-offs / compromises

- **No outbox publisher is included.** The table and contract exist; shipping a
  real relay (and the broker) is out of scope for a local test task. Rows
  accumulate with `published_at = NULL`.
- **`reviewerUserIds` is stored as JSON**, not a join table. Simpler and enough
  for create/read/decide; if reviewer-level workflows (per-reviewer sign-off,
  querying "requests assigned to me") were needed, a `request_reviewers` table
  would replace it.
- **Decisions are single-step.** Any caller with `approval:decide` finalizes
  the request; there's no quorum/N-of-M reviewer logic. The audit + reviewer
  list make that a natural extension.
- **Auth is a header stub** by design. It models workspace + user + scopes
  faithfully so the real issuer drops in behind `get_principal` unchanged.
- **Timestamps under SQLite** are stored without tz offset (a SQLite
  limitation); PostgreSQL keeps `timestamptz`. Application code always works in
  UTC.
- **`alembic check` is wired** and confirms the single migration matches the
  models, but there's just one migration — a real project would accrue a chain.
- **Light pagination** (`limit`/`offset` + `total`). Fine at this scale;
  keyset pagination would be the move for very large workspaces.
