# Agent Instructions for EntityGuard

Compact operational guidance for OpenCode sessions. If a fact is obvious from filenames or `README.md`, it is omitted.

## Project at a Glance

- **Project name:** EntityGuard.
- Single FastAPI service with an HTML admin UI and one JSON API namespace. All user-facing strings (UI, docs) are **German**.
- Runtime depends on a German spaCy model (`de_core_news_lg`) and a seeded SQLite database.
- All recognizers/entities are stored in `data/entityguard.db`; the API analyzer is a lazily-created singleton rebuilt on `/reload`. Alembic migrations seed the canonical initial data.

## Toolchain

- Package manager: `uv` (uses `pyproject.toml` + `uv.lock`).
- Python version: 3.13 (`.python-version`).
- No formatter, linter, type-checker, or pre-commit config is present.
- Tests: `pytest` (dev dependency), but there are currently no test files.
- CSS is **compiled, not hand-edited**: edit `frontend/static/css/tailwind-input.css`, then `npm run build:css` (or `watch:css` during dev). `admin.css` is generated — never edit it directly.

## Local Setup

1. `uv sync`
2. `uv run python -m spacy download de_core_news_lg` (~500 MB, required)
3. `uv run alembic upgrade head`
4. `uv run python main.py`

Service listens on `http://localhost:9500` (`main.py` hardcodes port `9500`).

## Dev Server Behavior

- `uvicorn.run` has **no auto-reload**: Python changes require a manual restart. The server usually runs in the user's own terminal — don't kill it without asking.
- Templates (Jinja2) and static files are read from disk per request — template/CSS/JS edits are live immediately, no restart needed.

## Docker

- Docker Compose maps port `9500:9500` and the container health-check hits `localhost:9500`; `main.py` also listens on `9500`, so the mapping works out of the box.
- The Dockerfile installs the spaCy model during the build, so the container should start ready.
- The Compose service is named `entityguard`.

## Database & Migrations

- Alembic URL: `sqlite:///data/entityguard.db` (configured in `alembic.ini`).
- `data/` is gitignored but mounted as a volume in Docker Compose, so the DB persists across `docker-compose down`. Local DB state is dev-only — migrations are the only canonical source; never document "just update the DB".
- `main.py` does not initialize or seed the database on startup. **You must run `uv run alembic upgrade head` before starting the app.**
- Alembic migrations are the exclusive source of schema, default entities/recognizers, and the default admin user.
- The default admin user is created by migration `004_seed_default_admin_user.py` (idempotent: only if `admin_users` is empty).
- New migration: `uv run alembic revision --autogenerate -m "description"`, then `uv run alembic upgrade head`. Migration files are numbered `00N_description.py` with plain string revisions (`revision = '011'`).
- The `is_builtin` column on `recognizers` exists; non-builtin DB recognizers are loaded at runtime, while Presidio’s own built-ins are mostly removed except `spacy_nlp`.

## Key Entrypoints

- `main.py` — FastAPI factory, Uvicorn runner. No runtime DB seeding.
- `backend/views/anonymizer.py` — API router `/api/v1/entityguard/*` and the cached singleton analyzer (`_analyzer`).
- `backend/components/cstm_analyzer.py` — `CustomAnalyzer` (Presidio + spaCy + DB patterns).
- `backend/admin/routes.py` — HTML admin UI under `/admin/*`; `GET /` redirects to `/admin/dashboard` if authenticated, otherwise to `/admin/login`.
- `backend/database/` — SQLAlchemy models, CRUD, seeding.
- `frontend/templates/` + `frontend/static/` — Jinja2 templates and CSS/JS assets (served at `/static`).
- Project layout: `main.py` stays in the root; backend code lives in `backend/`, frontend assets in `frontend/`.
- `GET /sanitize` (in `backend/views/public.py`) is a **public, login-free** split-view page; it still passes the user context so logged-in admins keep the sidebar.

## API / Runtime Gotchas

- `/api/v1/entityguard/sanitize` returns HTTP 500 on any processing error (fail-closed). It never returns raw text on failure.
- `/api/v1/entityguard/reload` rebuilds the singleton analyzer from the DB. Call this after editing patterns in the admin UI; otherwise edits are not reflected. The model toggles on `/admin/modelle` trigger the rebuild themselves.
- Admin UI login: `admin` / `admin`. Change the password immediately in production.
- `/api/v1/entityguard/sanitize` returns `sanitized_text` plus a `mapping` (placeholder -> original value) for every masked entity occurrence. Placeholders are uniquely indexed per occurrence (e.g. `[EMAIL_1]`, `[EMAIL_2]`), not just per entity type.
- Placeholders come from the `entities` table; if an entity is inactive, it will not be passed to Presidio for analysis. The `DEFAULT` operator maps to `[SENSITIV]`. A hit for an entity that has no DB row is silently dropped — e.g. ORGANIZATION hits were lost before migration `011` seeded the entity.
- Transformer models (`backend/components/bert_recognizer.py`) are **inactive by default** (migrations `010`/`011`/`012`). Selectable via `BERT_MODEL_REGISTRY` (key = `recognizers.name` DB row): `transformer_ner_fhswf` (fhswf/bert_de_ner), `transformer_pii_openmed_small` (44M), `_base` (184M), `_large` (434M). The OpenMed sizes share one label mapping (`OPENMED_PII_GERMAN_MAPPING`) and differ only in accuracy/speed; base+large carry `gpu_recommended=True`. Managed on `/admin/modelle` (on/off switches with a live CUDA status and "GPU empfohlen" badge, immediate analyzer rebuild - not editable recognizer rows; the recognizer list hides these rows and edit/delete routes redirect to /admin/modelle). Models load lazily on first use and are cached module-level (survive `/reload`). Latencies add up when several are active.
- `scripts/benchmark_all_models.py` is the source of the CPU/GPU latency numbers quoted in README, AGENTS and the admin model descriptions. Rerun it after changing the registry and update those numbers.
- `recognizers.name` for transformer rows is a **code contract** — renaming a row in the DB orphans the model. The admin routes already guard this; don't bypass it.
- `BERT_NER_DEVICE` must be a string device spec - transformers >= 4.5x rejects integer devices (`-1` used to mean CPU; now use `cpu`).

## Editing Patterns / Entities

- Add/edit recognizers, patterns, context words, and entities via `/admin` in a browser.
- After saving, either click the reload button in the UI or `POST /api/v1/entityguard/reload` to activate changes.
- Regex is validated server-side before persistence.
- Recognizer and entity names are unique.

## Testing

- `uv run pytest` / `uv run pytest -v`
- Currently no tests exist; add tests under a `tests/` directory if extending the suite.
- Quick non-pytest sanity check: start the server and `curl` the sanitize endpoint (see below), or run `scripts/benchmark_all_models.py` (all registry models, CPU+GPU) / `scripts/benchmark_bert_recognizer.py` (one model via `BERT_NER_MODEL`) for latency regressions.

## Releases / Changelog

- All notable changes are documented in `CHANGELOG.md` (Keep a Changelog format). Add your changes to the `[Unreleased]` section as part of the work, not afterwards.
- Canonical version lives in `pyproject.toml`. **`main.py`'s FastAPI `version=` is a manual mirror — update it alongside the bump.** The root `package.json` is Tailwind build tooling with its own version - never synced.
- Release workflow:
  1. Make sure `[Unreleased]` in `CHANGELOG.md` has bullets (empty sections abort the bump with a warning).
  2. `uv run python scripts/bump_version.py minor --commit` (or `patch`/`major`) - bumps the version, moves the `[Unreleased]` section under `## [X.Y.Z] — date`, commits and tags `vX.Y.Z`.
  3. `git push && git push --tags` - the tag push triggers `.github/workflows/release.yml`, which extracts the CHANGELOG section for that version and creates the GitHub Release with it as notes.
- Never create tags/releases manually; the script + workflow are the single path.

## Commit Style

- Conventional prefixes, English: `feat:`, `fix:`, `refactor:`, `chore:` (see `git log`). Multi-line bodies explaining the *why* are the norm.

## Useful Verification Commands

```bash
uv run alembic upgrade head        # apply migrations
uv run python main.py              # local dev server on port 9500
uv run pytest -v                   # run tests (none yet)
npm run build:css                  # rebuild admin.css after CSS changes

# health check
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
