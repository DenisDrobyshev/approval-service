# approval-service

A backend service for **content approval workflows**. It accepts requests to
approve content before publication and records the final decision. External
entities (publications, scenarios, users, workspaces) are referenced by
opaque identifiers — neighbouring services are intentionally **not**
implemented here.

Built with **Python + FastAPI + SQLAlchemy (async) + Alembic**, runs on
**PostgreSQL** (docker-compose) or **SQLite** (zero-infra local/dev).

> See [DESIGN.md](DESIGN.md) for the data model, service boundaries,
> idempotency handling, events/integration and known trade-offs.

---

## Features at a glance

| Requirement | How it is met |
|---|---|
| Workspace isolation | Every query is scoped by `workspace_id`; the auth context's workspace must match the path, and cross-workspace reads return `404`. |
| Idempotency (no duplicates) | Optional `Idempotency-Key` header; the first response is stored and replayed for retries. Reuse with a different payload → `409`. |
| State machine | `pending → approved / rejected / cancelled`. Final states are terminal; re-deciding → `409`. |
| Audit trail | Every successful change writes an `audit_log` row (actor, action, from/to status). |
| Event readiness | Every change writes an `outbox_events` row in the **same transaction** (transactional outbox). |
| No secret leakage | Responses/logs/events never carry tokens, emails, signed/provider URLs or raw payloads; a redaction filter scrubs logs and event free-text. |

---

## Quick start

### Option A — Docker (PostgreSQL)

```bash
docker compose up --build
```

The API container runs migrations (`alembic upgrade head`) and then serves on
**http://localhost:8000**. Interactive docs at **http://localhost:8000/docs**.

### Option B — Local (SQLite, no infrastructure)

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt

# create the schema
alembic upgrade head

# run
uvicorn app.main:app --reload
```

Default `DATABASE_URL` is `sqlite+aiosqlite:///./approval.db` (see
[.env.example](.env.example)). For local Postgres set, e.g.:

```bash
export DATABASE_URL="postgresql+asyncpg://approval:approval@localhost:5432/approval"
```

---

## Running the tests

```bash
pip install -r requirements.txt
pytest
```

The suite uses a local SQLite file and needs no external services. It covers
health/readiness, auth & scopes, CRUD, the decision state machine,
idempotency, workspace isolation, the audit trail, the outbox and redaction.

---

## Authentication (local stub)

There is no real token issuer for local runs. The caller declares its identity
through three headers:

| Header | Meaning | Example |
|---|---|---|
| `X-Workspace-Id` | Workspace the caller acts in (must equal the path `workspace_id`) | `ws_alpha` |
| `X-User-Id` | The acting user | `usr_admin` |
| `X-Scopes` | Granted actions, comma- or space-separated | `approval:read approval:create approval:decide approval:cancel` |

Scopes required per action:

| Action | Scope |
|---|---|
| read requests (`GET`) | `approval:read` |
| create a request | `approval:create` |
| approve / reject | `approval:decide` |
| cancel | `approval:cancel` |

Failure modes: missing identity → `401`; workspace mismatch or missing scope → `403`.

> Swapping this stub for real JWT/OAuth means replacing `get_principal` in
> [`app/auth.py`](app/auth.py) — nothing else changes.

---

## HTTP API

```
GET  /health
GET  /ready
POST /api/v1/workspaces/{workspace_id}/approval-requests
GET  /api/v1/workspaces/{workspace_id}/approval-requests
GET  /api/v1/workspaces/{workspace_id}/approval-requests/{request_id}
POST /api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/approve
POST /api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/reject
POST /api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/cancel
```

`GET .../approval-requests` supports `?status=pending|approved|rejected|cancelled`
and `?limit=` (1–200, default 50) / `?offset=`.

Mutating endpoints accept an optional `Idempotency-Key` header.

### Example session (curl)

```bash
BASE=http://localhost:8000
WS=ws_alpha
URL=$BASE/api/v1/workspaces/$WS/approval-requests
AUTH=(-H "X-Workspace-Id: $WS" -H "X-User-Id: usr_admin" \
      -H "X-Scopes: approval:read approval:create approval:decide approval:cancel")

# create
curl -X POST "$URL" "${AUTH[@]}" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_1", "usr_2"]
      }'

# list / get
curl "$URL" "${AUTH[@]}"
curl "$URL/req_xxx" "${AUTH[@]}"

# decisions
curl -X POST "$URL/req_xxx/approve" "${AUTH[@]}" -H "Content-Type: application/json" -d '{"comment":"Approved"}'
curl -X POST "$URL/req_xxx/reject"  "${AUTH[@]}" -H "Content-Type: application/json" -d '{"reason":"Brand tone is wrong"}'
curl -X POST "$URL/req_xxx/cancel"  "${AUTH[@]}" -H "Content-Type: application/json" -d '{"reason":"Draft was removed"}'
```

### Request / response shapes

**Create** (`sourceType` ∈ `publication | scenario | edit | external`):

```json
{
  "sourceType": "publication",
  "sourceId": "pub_123",
  "title": "Instagram reel draft",
  "description": "Needs final approval",
  "reviewerUserIds": ["usr_1", "usr_2"]
}
```

**Decisions**: approve `{ "comment": "Approved" }` (optional),
reject `{ "reason": "Brand tone is wrong" }` (required),
cancel `{ "reason": "Draft was removed" }` (optional).

**Errors** use a consistent envelope and never echo input:

```json
{ "error": { "code": "conflict", "message": "Request is already in final state 'approved' and cannot be changed" } }
```

| Status | When |
|---|---|
| `201` | request created |
| `200` | read / decision applied |
| `401` | missing auth context |
| `403` | workspace mismatch or missing scope |
| `404` | request not found (incl. another workspace's id) |
| `409` | re-deciding a finalized request, or idempotency-key reused with a different payload |
| `422` | validation error |

---

## Project layout

```
app/
  main.py              app factory, /health, /ready, access logging
  config.py            settings (env / .env)
  database.py          async engine + session
  models.py            ORM: approval_requests, idempotency_keys, audit_log, outbox_events
  schemas.py           Pydantic request/response models (camelCase API)
  enums.py             SourceType, RequestStatus, Action, EventType, AuditAction
  auth.py              header auth stub + scope/workspace checks
  service.py           business logic: state machine, idempotency, audit, outbox
  events.py            sanitized event payloads
  security.py          redaction helpers
  logging_config.py    structured logging + redaction filter
  errors.py            domain errors + clean JSON handlers
  api/routes_approvals.py
alembic/               migrations (env.py + versions/0001_initial_schema.py)
tests/                 pytest suite
Dockerfile, docker-compose.yml, entrypoint.sh
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./approval.db` | async SQLAlchemy URL |
| `LOG_LEVEL` | `INFO` | |
| `AUTO_CREATE_TABLES` | `false` | create tables on startup instead of migrations (handy for quick demos) |
