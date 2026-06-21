# Distributed Config Manager

A centralized configuration service that lets applications fetch runtime config from a single source of truth instead of redeploying for every change. Built with **FastAPI**, **PostgreSQL**, and **Redis**, with immutable versioning, safe rollback, and a full audit log.

PostgreSQL is the source of truth. Redis is a cache-aside read layer for low-latency lookups. Every config change creates a new immutable version — nothing is ever overwritten.

---

## Features

- **Centralized config** for all services, fetched on demand over HTTP.
- **Immutable, append-only versioning** — each push creates a new version row.
- **Safe rollback** that doesn't mutate history (rollback copies an old version into a new one).
- **Audit log** capturing who changed what, when, and why.
- **Cache-aside reads** via Redis for fast `GET /config`.
- **Concurrency-safe writes** using row-level locking (`SELECT ... FOR UPDATE`).
- **JSONB config storage** so each service can have its own schema.
- **Alembic migrations** for schema evolution.
- **Dockerized** with Docker Compose for one-command local setup.
- **Pytest** suite covering invariants, not just happy paths.

---

## Tech Stack

| Layer | Tool |
|---|---|
| API | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Tests | Pytest |
| Packaging | Docker + Docker Compose |

---

## Architecture

```
+------------------+        +---------------------------+        +------------------+
| Application      |------->| FastAPI Config Manager    |------->| PostgreSQL       |
| Services         |  GET   | - API layer               |  SQL   | Source of truth  |
| (fetch config)   |<-------| - SQLAlchemy transactions |<-------| Versions + audit |
+------------------+        | - Cache orchestration     |        +------------------+
                            +------------+--------------+
                                         |
                                         v
                                 +------------------+
                                 | Redis            |
                                 | Current-config   |
                                 | read cache       |
                                 +------------------+
```

### Design notes

- **Cache-aside, not write-through.** On a write we commit to PostgreSQL first, then `DEL` the Redis key. The next read repopulates the cache. This avoids the dual-write problem (DB succeeds but cache update fails, or vice versa) and keeps PostgreSQL as the single source of truth.
- **Rollback is forward-only.** Rolling back to version 9 doesn't reactivate v9 — it creates a new version (e.g. v13) whose payload is copied from v9. History stays linear and explainable, which matters during incident reviews.
- **JSONB for config payloads.** Configs are heterogeneous across services; JSONB gives flexibility, GIN indexing, and JSON-path queries without locking into a fixed column schema.
- **Row locking on push.** `SELECT ... FOR UPDATE` on the service row prevents two concurrent pushes from minting the same version number.

---

## Project Structure

```
distributed-config-manager/
├── app/
│   ├── main.py                 # FastAPI entrypoint
│   ├── api/config_routes.py    # HTTP endpoints
│   ├── core/                   # Settings, FastAPI deps
│   ├── db/
│   │   ├── session.py          # Engine + SessionLocal
│   │   └── models.py           # SQLAlchemy models
│   ├── cache/redis_client.py   # Redis client + helpers
│   ├── repositories/           # DB access layer
│   ├── services/               # Business logic (push, rollback, etc.)
│   └── schemas/                # Pydantic request/response models
├── alembic/
│   ├── env.py
│   └── versions/               # Migration scripts
├── tests/
│   ├── conftest.py
│   ├── test_get_config.py
│   ├── test_post_config.py
│   ├── test_rollback.py
│   └── test_history.py
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## Data Model

Three tables: `services`, `config_versions`, `audit_log`.

- `services` — service registry; holds a `current_version_id` pointer for fast reads.
- `config_versions` — immutable versions; `UNIQUE(service_id, version)` enforces monotonic numbering per service.
- `audit_log` — append-only event log (`PUSH`, `ROLLBACK`, `CREATE_SERVICE`) with actor, reason, and request ID for correlation.

`audit_log` rows are never updated or deleted — that's what makes the audit trail trustworthy.

---

## Running Locally

```bash
# 1. Clone
git clone https://github.com/your-org/distributed-config-manager.git
cd distributed-config-manager

# 2. Bring up the stack (api, db, redis, migrations)
docker compose up --build

# 3. API is available at http://localhost:8000
#    Interactive docs at http://localhost:8000/docs
```

To stop and wipe the database volume:

```bash
docker compose down -v
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://config:config@db:5432/configdb` | Postgres DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL |
| `LOG_LEVEL` | `INFO` | App log level |

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/config/{service_name}` | Get current config (cache-aside) |
| `POST` | `/config/{service_name}` | Push a new config version |
| `POST` | `/config/{service_name}/rollback` | Roll back to a previous version (creates a new version) |
| `GET` | `/config/{service_name}/history` | Paginated change history |

### Tiny example

Push a new config:

```bash
curl -X POST http://localhost:8000/config/billing-service \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "feature_flags": { "new_checkout": true },
      "timeouts": { "db_ms": 500 }
    },
    "actor": "alice@company.com",
    "change_reason": "Enable new checkout"
  }'
```

Fetch the current config:

```bash
curl http://localhost:8000/config/billing-service
```

Response:

```json
{
  "service_name": "billing-service",
  "version": 1,
  "checksum": "sha256:abc123...",
  "created_at": "2026-06-21T10:30:00Z",
  "config": {
    "feature_flags": { "new_checkout": true },
    "timeouts": { "db_ms": 500 }
  }
}
```

Roll back to version 1:

```bash
curl -X POST http://localhost:8000/config/billing-service/rollback \
  -H "Content-Type: application/json" \
  -d '{ "target_version": 1, "actor": "sre@company.com" }'
```

---

## Migrations

Alembic runs automatically via the `migrate` container in Compose. To run manually:

```bash
docker compose run --rm api alembic upgrade head        # apply
docker compose run --rm api alembic revision --autogenerate -m "msg"  # create
```

---

## Testing

```bash
# Run the full suite inside the api container
docker compose run --rm api pytest -v

# Run a single file
docker compose run --rm api pytest tests/test_rollback.py -v
```

Tests cover, among others:

- Cache hit / miss behavior on `GET /config`.
- Version increments and `current_version_id` pointer updates on `POST /config`.
- Cache key invalidation after every write.
- Rollback creates a new version and leaves historical rows untouched.
- Concurrent pushes do not produce duplicate version numbers.
- Audit log rows are written for every state change.

---

## Roadmap

- Authentication & per-service RBAC.
- Webhook notifications on push / rollback.
- Diff endpoint between two versions.
- Optional schema validation per service.
- Prometheus metrics + structured logging.

---

## License

MIT
