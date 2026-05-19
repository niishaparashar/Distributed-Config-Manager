# Distributed Config Manager

Distributed Config Manager is a production-oriented FastAPI REST API for centralized, versioned configuration distribution. It simulates how large-scale network deployments can register services, push config changes, roll back versions, serve hot-path reads from cache, and preserve a full audit trail.

## Tech Stack

| Layer | Technology |
| --- | --- |
| API | FastAPI, Pydantic v2 |
| Database | PostgreSQL 15 |
| ORM | Async SQLAlchemy |
| Cache | Redis 7 |
| Migrations | Alembic |
| Tests | Pytest, httpx |
| Runtime | Docker, Docker Compose |
| Env | python-dotenv, pydantic-settings |

## Architecture

```text
Client
  |
  v
FastAPI REST API
  |                  |
  | latest cache     | source of truth + audit trail
  v                  v
Redis            PostgreSQL
```

## Setup

```bash
git clone <repo-url>
cd distributed-config-manager
cp .env.example .env
docker-compose up --build
```

In another shell, seed the database:

```bash
python seed.py
```

Swagger documentation is available at `http://localhost:8000/docs`.

## API Examples

Register a service:

```bash
curl -X POST http://localhost:8000/services \
  -H "Content-Type: application/json" \
  -d '{"name":"auth-service","description":"Authentication service"}'
```

List services:

```bash
curl http://localhost:8000/services
```

Push a new config:

```bash
curl -X POST http://localhost:8000/configs/auth-service \
  -H "Content-Type: application/json" \
  -d '{
    "created_by": "platform-admin",
    "config_data": {
      "db_host": "postgres://prod-db:5432",
      "max_connections": 100,
      "feature_flags": {
        "enable_dark_mode": true,
        "beta_users_only": false
      },
      "timeout_ms": 3000,
      "log_level": "INFO"
    }
  }'
```

Fetch latest config:

```bash
curl http://localhost:8000/configs/auth-service/latest
```

Get config history:

```bash
curl http://localhost:8000/configs/auth-service/history
```

Fetch a specific version:

```bash
curl http://localhost:8000/configs/auth-service/2
```

Rollback to version 1:

```bash
curl -X POST "http://localhost:8000/configs/auth-service/rollback?version=1&performed_by=platform-admin"
```

Delete a non-active version:

```bash
curl -X DELETE "http://localhost:8000/configs/auth-service/2?performed_by=platform-admin"
```

View audit trail:

```bash
curl http://localhost:8000/audit/auth-service
```

Health check:

```bash
curl http://localhost:8000/health
```

## Local Tests

```bash
pytest
```

The tests run against an async SQLite database with an in-memory Redis substitute, while the deployed stack uses PostgreSQL and Redis through Docker Compose.
