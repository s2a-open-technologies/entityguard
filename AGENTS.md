# Agent Instructions for EntityGuard

Compact operational guidance for OpenCode sessions. If a fact is obvious from filenames or `README.md`, it is omitted.

## Project at a Glance

- **Project name:** EntityGuard.
- Single FastAPI service with an HTML admin UI and one JSON API namespace.
- Runtime depends on a German spaCy model (`de_core_news_lg`) and a seeded SQLite database.
- All recognizers/entities are stored in `data/entityguard.db`; the app loads them at startup. Alembic migrations seed the canonical initial data.

## Toolchain

- Package manager: `uv` (uses `pyproject.toml` + `uv.lock`).
- Python version: 3.13 (`.python-version`).
- No formatter, linter, type-checker, or pre-commit config is present.
- Tests: `pytest` (dev dependency), but there are currently no test files.

## Local Setup

1. `uv sync`
2. `uv run python -m spacy download de_core_news_lg` (~500 MB, required)
3. `uv run alembic upgrade head`
4. `uv run python main.py`

Service listens on `http://localhost:9500` (`main.py` hardcodes port `9500`).

## Docker

- Docker Compose maps port `9500:9500` and the container health-check hits `localhost:9500`; `main.py` also listens on `9500`, so the mapping works out of the box.
- The Dockerfile installs the spaCy model during the build, so the container should start ready.
- The Compose service is named `entityguard`.

## Database & Migrations

- Alembic URL: `sqlite:///data/entityguard.db` (configured in `alembic.ini`).
- `data/` is gitignored but mounted as a volume in Docker Compose, so the DB persists across `docker-compose down`.
- `main.py` no longer initializes or seeds the database on startup. **You must run `uv run alembic upgrade head` before starting the app.**
- Alembic migrations are the exclusive source of schema, default entities/recognizers, and the default admin user.
- The default admin user is created by migration `004_seed_default_admin_user.py` (idempotent: only if `admin_users` is empty).
- New migration: `uv run alembic revision --autogenerate -m "description"`, then `uv run alembic upgrade head`.
- The `is_builtin` column on `recognizers` exists; non-builtin DB recognizers are loaded at runtime, while Presidio’s own built-ins are mostly removed except `spacy_nlp`.

## Key Entrypoints

- `main.py` — FastAPI factory, Uvicorn runner. No runtime DB seeding.
- `src/views/anonymizer.py` — API router `/api/v1/entityguard/*` and the cached analyzer registry (`_analyzer_registry`).
- `src/components/cstm_analyzer.py` — `CustomAnalyzer` (Presidio + spaCy + DB patterns).
- `src/admin/routes.py` — HTML admin UI under `/admin/*`; `GET /` redirects to `/admin/dashboard` if authenticated, otherwise to `/admin/login`.
- `src/database/` — SQLAlchemy models, CRUD, seeding.

## API / Runtime Gotchas

- `/api/v1/entityguard/sanitize` returns HTTP 500 on any processing error (fail-closed). It never returns raw text on failure.
- `/api/v1/entityguard/reload` clears the analyzer registry and reloads from the DB. Call this after editing patterns in the admin UI; otherwise edits are not reflected.
- Admin UI login: `admin` / `admin`. Change the password immediately in production.
- Analyzer cache is keyed by `department`; only `"standard"` is currently implemented.
- Placeholders come from the `entities` table; if an entity is inactive, it will not be passed to Presidio for analysis. The `DEFAULT` operator maps to `[SENSITIV]`.

## Editing Patterns / Entities

- Add/edit recognizers, patterns, context words, and entities via `/admin` in a browser.
- After saving, either click the reload button in the UI or `POST /api/v1/entityguard/reload` to activate changes.
- Regex is validated server-side before persistence.
- Recognizer and entity names are unique.

## Testing

- `uv run pytest` / `uv run pytest -v`
- Currently no tests exist; add tests under a `tests/` directory if extending the suite.

## Useful Verification Commands

```bash
uv run alembic upgrade head        # apply migrations
uv run python main.py              # local dev server on port 6000
uv run pytest -v                   # run tests (none yet)

# health check (adjust port for local vs Docker)
curl http://localhost:9500/health

# sanitize

curl -s -X POST http://localhost:9500/api/v1/entityguard/sanitize \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291"}'

# reload patterns after admin changes
curl -X POST http://localhost:9500/api/v1/entityguard/reload
```

## References

- `README.md` — full user-facing docs, API examples, OpenWebUI integration.
- `docs/OpenWebUI.md` — OpenWebUI filter setup.
