# Agent Instructions for EntityGuard

Compact operational guidance for OpenCode sessions. If a fact is obvious from filenames or `README.md`, it is omitted.

## Project at a Glance

- **Project name:** EntityGuard.
- Single FastAPI service with an HTML admin UI and one JSON API namespace. All user-facing strings (UI, docs) are **German**.
- Runtime depends on a German spaCy model (`de_core_news_lg`) and a seeded SQLite database.
- All entities, patterns and context words are stored in `data/entityguard.db`; the API analyzer is a lazily-created singleton rebuilt on `/reload`. Alembic migrations seed the canonical initial data.

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
- The container runs as non-root (uid 10001) and `docker-entrypoint.sh` runs `alembic upgrade head` on every start (not at build time), so image updates migrate existing volumes. `HF_HOME=/app/data/hf` keeps downloaded transformer models in the volume.
- Images are built by `.github/workflows/docker.yml` for `linux/amd64,linux/arm64` and pushed to `ghcr.io/s2a-open-technologies/entityguard` on `vX.Y.Z` tags (`X.Y.Z`, `X.Y`, `X`, `latest`) and `master` (`edge`). Matrix variant `cpu` (`--build-arg TORCH_VARIANT=cpu`, CPU-only torch swapped in after `uv sync`, no re-lock) gets the suffix `-cpu` (`latest-cpu`, `X.Y.Z-cpu`, …). The default variant keeps the lockfile's torch (CUDA wheels on amd64).
- The Compose service is named `entityguard`.

## Database & Migrations

- Alembic URL: `sqlite:///data/entityguard.db` (configured in `alembic.ini`; the app resolves the same path via `backend/database/database.py`). Local `data/` is gitignored, dev-only — migrations are the only canonical source; never document "just update the DB".
- Docker Compose uses a **named volume** `entityguard-data` (not a host bind mount since the volume change), so the container DB persists across `docker-compose down` but is separate from the local `data/` dir. There is no docker-compose host-mount of the local DB.
- `main.py` does not initialize or seed the database on startup. **You must run `uv run alembic upgrade head` before starting the app.**
- Alembic migrations are the exclusive source of schema, default entities/patterns, and the default admin user.
- The default admin user is created by migration `004_seed_default_admin_user.py` (idempotent: only if `admin_users` is empty).
- New migration: `uv run alembic revision --autogenerate -m "description"`, then `uv run alembic upgrade head`. Migration files are numbered `00N_description.py` with plain string revisions (`revision = '013'`).
- Data model (since migration `013`): **`entities` is the central unit**. `patterns` and `context_words` reference it directly via `entity_id`; the old `recognizers` layer (and its inert `spacy_*`/`builtin_*` placeholder rows) no longer exists. Migrations before `013` still create/read `recognizers` — they are historical; don't edit them.

## Key Entrypoints

- `main.py` — FastAPI factory, Uvicorn runner. No runtime DB seeding.
- `backend/views/anonymizer.py` — API router `/api/v1/*` and the cached singleton analyzer (`_analyzer`).
- `backend/components/cstm_analyzer.py` — `CustomAnalyzer` (Presidio + spaCy + per-entity patterns).
- `backend/admin/routes.py` — HTML admin UI under `/admin/*`; `GET /` redirects to `/admin/dashboard` if authenticated, otherwise to `/admin/login`.
- `backend/database/` — SQLAlchemy models, CRUD, seeding.
- `frontend/templates/` + `frontend/static/` — Jinja2 templates and CSS/JS assets (served at `/static`).
- Project layout: `main.py` stays in the root; backend code lives in `backend/`, frontend assets in `frontend/`.
- `GET /admin/sanitize` (in `backend/admin/routes.py`) is the login-protected split-view page (redirects to `/admin/login` when unauthenticated). Its JS calls the same-origin session-authenticated proxy `POST /admin/sanitize/api` — no API key ever reaches the browser. The old public `public_router` / `backend/views/public.py` was removed.

## Users, Roles, Audit & Tracing

- **Roles** live in `admin_users.role` (`admin` | `viewer`). `require_admin` (in `backend/admin/auth.py`) wraps `require_auth` and returns 403 for viewers. All mutating config routes use `require_admin`; read routes and the sanitize page/proxy use `require_auth`; users/audit/traces are admin-only.
- **User management** is `/admin/users` (create/toggle/role/reset-password/delete, `backend/database/crud.py`). Self-deactivation/deletion/role-change and removing the last active admin are blocked in the route handlers.
- **Audit log** (`audit_log` table, migration `018`): append-only `log_audit(...)` calls record who/when/what for all mutating routes plus login and failed login. It never stores changed values. Page: `/admin/audit`.
- **Request tracing** (`request_trace` table, migration `019`, `backend/tracing.py::record_trace`): content-free per-request metadata (source, key prefix, input length, mask/entity counts, latency, success, optional HMAC). Hooked only into `/api/v1/sanitize` — the admin sanitize page/proxy is deliberately **not** traced (live preview fires per keystroke pause and would flood the log). **Never** stores the text or the mapping. Controlled by `backend/config.py`: `TRACE_ENABLED` (default true), `TRACE_RETENTION_DAYS` (default 7, pruned on startup in `main.py`), `TRACE_HMAC_SECRET` (hash only written when set). Page: `/admin/traces`.
- Sessions are still in-memory (`backend/admin/auth.py::_sessions`) — a restart logs everyone out.

## API / Runtime Gotchas

- **API keys**: `/api/v1/sanitize` and `/api/v1/reload` require a key (`backend/security.py::require_api_key`), sent as `Authorization: Bearer <key>` or `X-API-Key`. Keys are created/managed in the admin UI (`/admin/api-keys`, table `api_keys`, bcrypt hash, plaintext shown once); only **active** DB keys count. With no active key the API returns **401** (fail-closed). `/health` stays open.
- `/api/v1/sanitize` returns HTTP 500 on any processing error (fail-closed). It never returns raw text on failure.
- `/api/v1/reload` rebuilds the singleton analyzer from the DB. Call this after editing patterns in the admin UI; otherwise edits are not reflected. The model toggles on `/admin/modelle` trigger the rebuild themselves.
- The API namespace is `/api/v1/*` (e.g. `/api/v1/sanitize`), **not** `/api/v1/entityguard/*` — that path does not exist despite appearing in some older docs.
- Admin UI login: `admin` / `admin`. Change the password immediately in production.
- `/api/v1/sanitize` returns `sanitized_text` plus a `mapping` (placeholder -> original value) for every masked entity occurrence. Placeholders are uniquely indexed per occurrence (e.g. `[EMAIL_1]`, `[EMAIL_2]`), not just per entity type.
- Placeholders come from the `entities` table; if an entity is inactive (or has no DB row), its hits are silently dropped. The `DEFAULT` operator maps to `[SENSITIV]`.
- One Presidio `PatternRecognizer` is built per entity that has patterns (entity name == supported_entity); a recognizer's context words come from the entity's `context_words`.
- Detection sources are shown in the admin UI (`BASE_ENTITY_SOURCES` in `backend/admin/routes.py` + `_entity_sources`): DB patterns, built-in engines (German spaCy NER emits only PER/LOC/ORG → PERSON/LOCATION/ORGANIZATION; Presidio keeps Email + Phone) and **active** transformer models. Entities with none are flagged "nicht erkannt". `BASE_ENTITY_SOURCES` is a deliberate hardcoded map — do NOT derive it from `recognizer.supported_entities`, SpacyRecognizer over-advertises DATE_TIME/EMAIL/PHONE that the German model never produces.
- `DATE_TIME`, `IBAN_CODE` and `FALLNUMMER` were dead after migration 013 (no patterns, no built-in engine). Migration `014` fixed this: default IBAN pattern on IBAN_CODE, the date pattern moved from MEDICAL_CONTEXT to DATE_TIME (dates now mask as `[DATUM/ZEIT]`), and FALLNUMMER was removed (case numbers stay on MEDICAL_CONTEXT's `fallnummer_generic`).
- Transformer models (`backend/components/bert_recognizer.py`) are **inactive by default**. Toggle state lives in the `detector_models` table (key = `name`, matches `BERT_MODEL_REGISTRY`); managed on `/admin/modelle` (on/off switches with a live CUDA status and "GPU empfohlen" badge, immediate analyzer rebuild). Registry: `transformer_ner_fhswf` (fhswf/bert_de_ner), `transformer_pii_openmed_small` (44M), `_base` (184M), `_large` (434M) — the OpenMed sizes share `OPENMED_PII_GERMAN_MAPPING` and differ only in accuracy/speed; base+large carry `gpu_recommended=True`. Models load lazily on first use and are cached module-level (survive `/reload`). Latencies add up when several are active.
- `scripts/benchmark_all_models.py` is the source of the CPU/GPU latency numbers quoted in README, AGENTS and the admin model descriptions. Rerun it after changing the registry and update those numbers.
- `detector_models.name` matches a `BERT_MODEL_REGISTRY` key (code contract) — renaming it orphans the model.
- `BERT_NER_DEVICE` must be a string device spec - transformers >= 4.5x rejects integer devices (`-1` used to mean CPU; now use `cpu`).

## Editing Entities / Patterns

- Add/edit entities, their patterns and context words via `/admin` (entity detail page) in a browser.
- Patterns can be entered as a **keyword list** (comma/newline separated -> auto-built word-boundary regex, `build_keyword_regex()` in `backend/admin/routes.py`) or as a raw regex; the keyword list is preserved in `patterns.keywords` for round-tripping.
- The `/admin/preview` endpoint and the "Muster testen" box test raw regexes; `PATTERN_TEMPLATES` in `routes.py` powers the one-click chips.
- After saving, either click the reload button in the UI or `POST /api/v1/reload` to activate changes (model toggles reload automatically).
- Regex is validated server-side before persistence.
- Entity and pattern names are unique.

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

# sanitize (create an API key first under /admin/api-keys)
curl -s -X POST http://localhost:9500/api/v1/sanitize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eg_..." \
  -d '{"text": "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291"}'

# reload patterns after admin changes
curl -X POST http://localhost:9500/api/v1/reload -H "Authorization: Bearer eg_..."
```

## References

- `README.md` — full user-facing docs, API examples, OpenWebUI integration.
- `docs/OpenWebUI.md` — OpenWebUI filter setup.
- `docs/data-mapping.md` — data flow / ROPA starting point (what is and isn't stored).
- `docs/pii.md` — masking pipeline and response contract.
- `docs/audit-checklist-entityguard.md` — audit self-assessment.
- `SECURITY.md` — security architecture, Art. 32 measures, deployment notes.
- `DISCLAIMER.md` — liability / not-a-medical-device notice.
