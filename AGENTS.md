# Agent Instructions for EntityGuard

Compact operational guidance for OpenCode sessions. Obvious facts from filenames or `README.md` are omitted.

## Project & Toolchain

- Single FastAPI service with an HTML admin UI and one JSON API namespace. All user-facing strings (UI, docs) are **German**.
- Runtime depends on the German spaCy model `de_core_news_lg`, a seeded SQLite DB, and (for images) Tesseract/RapidOCR.
- Package manager: `uv` (`pyproject.toml` + `uv.lock`); Python 3.13 (`.python-version`).
- No formatter, linter, type-checker, or pre-commit config exists.
- CSS is **compiled, not hand-edited**: edit `frontend/static/css/tailwind-input.css`, then `npm run build:css` (or `watch:css`). `admin.css` is generated. Run `npm ci` first if `node_modules/` is missing.
- Tests: `uv run pytest`; focused: `uv run pytest tests/test_image_sanitizer.py -q`. Tests use fake OCR/analyzer where possible. For real local image OCR install system `tesseract-ocr` plus `deu`/`eng` (the Docker image already has them). Light env without torch/spaCy model:
  `uv run --no-project --with pytest --with fastapi --with httpx --with presidio-analyzer --with sqlalchemy --with bcrypt --with transformers --with pillow pytest tests`

## Setup / Run

1. `uv sync`
2. `uv run python -m spacy download de_core_news_lg` (~500 MB, required)
3. `uv run alembic upgrade head`
4. `uv run python main.py`

Service listens on `http://localhost:9500` (`main.py` hardcodes the port).

- `uvicorn.run` has **no auto-reload**: Python changes need a manual restart. The server usually runs in the user's terminal — don't kill it without asking.
- Jinja2 templates and static files are read per request; template/CSS/JS edits are live immediately.
- `main.py` does not initialize or seed the DB. **Run `uv run alembic upgrade head` before starting.**
- Local `data/` is gitignored and dev-only; migrations are the only canonical schema/seed source.

## Docker

- Compose maps `9500:9500`; health check hits `localhost:9500`; service name is `entityguard`; data lives in the named volume `entityguard-data` (not the local `data/` dir).
- Dockerfile installs the spaCy model, Tesseract (`deu`/`eng`), and OCR deps. RapidOCR's torch `.pth` models are pre-downloaded at build time (skipped for `TORCH_VARIANT=cpu`) because they live in `site-packages`, which uid 10001 cannot write.
- Container runs as non-root uid 10001: `docker-entrypoint.sh` starts as root, `chown`s `/app/data` (old root-owned volumes caused "readonly database"), drops via `setpriv`, then runs `alembic upgrade head` on every start. `HF_HOME=/app/data/hf` keeps HF models in the volume.
- CI (`.github/workflows/docker.yml`) builds `linux/amd64,linux/arm64` on `vX.Y.Z` tags and `master`. Matrix variant `cpu` (`TORCH_VARIANT=cpu`, CPU-only torch swapped in after `uv sync`, no re-lock) gets suffix `-cpu`; default keeps the lockfile's torch (CUDA wheels on amd64).

## Database & Migrations

- Alembic URL: `sqlite:///data/entityguard.db` (`alembic.ini`); the app resolves the same path in `backend/database/database.py`.
- Migrations are the exclusive source of schema, default entities/patterns, and the default admin user (`004_seed_default_admin_user.py`, idempotent: only if `admin_users` is empty).
- New migration: `uv run alembic revision --autogenerate -m "description"`, then `uv run alembic upgrade head`. Files are numbered `00N_description.py` with plain string revisions (`revision = '013'`).
- Data model since migration `013`: **`entities` is central**. `patterns` and `context_words` reference it via `entity_id`; the old `recognizers` layer is gone. Migrations before `013` still create/read `recognizers` — historical, don't edit them.
- Migration `020` adds `app_settings` for admin-editable OCR/image settings.

## Key Entrypoints

- `main.py` — FastAPI factory, Uvicorn runner, lifespan env bootstrap.
- `backend/views/anonymizer.py` — `/api/v1/*` and the cached singleton analyzer (`_analyzer`).
- `backend/components/cstm_analyzer.py` — `CustomAnalyzer` (Presidio + spaCy + per-entity patterns); `analyze_text()` returns raw spans for image box mapping.
- `backend/components/ocr.py` — Tesseract/RapidOCR selection, lazy engine cache, normalized `OcrResult` lines/tokens.
- `backend/components/image_sanitizer.py` — image validation, span→box mapping, black-box overlays, PNG/base64.
- `backend/admin/routes.py` — HTML admin UI under `/admin/*`; `/` redirects to dashboard or login.
- `backend/database/` — SQLAlchemy models and CRUD.
- `frontend/templates/` + `frontend/static/` — Jinja2 templates and CSS/JS assets (served at `/static`).
- `integrations/openwebui/entityguard_filter.py` — ready-to-paste OpenWebUI filter (whole context + text/images); see `docs/OpenWebUI.md` and `integrations/openwebui/README.md`.
- `/admin/sanitize` is login-protected and calls same-origin session proxies `POST /admin/sanitize/api` (text) and `POST /admin/sanitize/api/image` (image); no API key reaches the browser. The old public `public_router` / `backend/views/public.py` was removed.
- `/admin/ocr` edits `app_settings` OCR keys; env vars win over DB values.
- Layout: `main.py` in root; code in `backend/`, templates/assets in `frontend/`, optional integrations in `integrations/`.

## Users, Roles, Audit & Tracing

- Roles live in `admin_users.role` (`admin` | `viewer`). `require_admin` (`backend/admin/auth.py`) wraps `require_auth` and returns 403 for viewers. Mutating config routes use `require_admin`; reads and sanitize page/proxies use `require_auth`; users/audit/traces are admin-only.
- User management `/admin/users` (create/toggle/role/reset-password/delete, `backend/database/crud.py`). Self-deactivation/deletion/role-change and removing the last active admin are blocked in route handlers.
- Audit log (`audit_log`, migration `018`): append-only `log_audit(...)` for all mutating routes plus login/failed login. It never stores changed values. Page: `/admin/audit`.
- Request tracing (`request_trace`, migration `019`, `backend/tracing.py::record_trace`): content-free metadata (source, key prefix, input length, mask/entity counts, latency, success, optional HMAC). Hooked only into `/api/v1/sanitize` and `/api/v1/sanitize/image`; admin sanitize proxies are deliberately **not** traced. Never stores text or mapping. Controlled by `backend/config.py`: `TRACE_ENABLED` (default true), `TRACE_RETENTION_DAYS` (default 7, pruned at startup), `TRACE_HMAC_SECRET` (hash only when set). Page: `/admin/traces`.
- Sessions are in-memory (`backend/admin/auth.py::_sessions`); restart logs everyone out.

## API / Runtime Gotchas

- **API keys**: `/api/v1/sanitize`, `/api/v1/sanitize/image`, and `/api/v1/reload` require a key via `Authorization: Bearer <key>` or `X-API-Key`. Keys are managed at `/admin/api-keys` (table `api_keys`, bcrypt, plaintext shown once); only **active** DB keys count. Headless env keys come from `ENTITYGUARD_API_KEY` / `ENTITYGUARD_API_KEY_FILE` (`backend/config.py::API_KEYS_FROM_ENV`, min. 16 chars, read once at import -> restart to change, never stored, traced as prefix `env`, shown only as a count). With neither source the API returns **401** (fail-closed); `/health` stays open.
- Text endpoint returns HTTP 500 on processing errors and never returns raw text on failure. `/api/v1/reload` rebuilds the singleton analyzer; call it after editing patterns. Model toggles rebuild automatically.
- Namespace is `/api/v1/*`, **not** `/api/v1/entityguard/*`.
- **Image OCR**: `POST /api/v1/sanitize/image` (and admin proxy `POST /admin/sanitize/api/image`) accepts base64 PNG/JPEG/WebP, runs OCR, masks detected text spans, and returns a redacted PNG + OCR text/mapping/boxes. Default redaction `line` (entire OCR line); `entity`/`all_text` selectable. Images are processed in memory and never stored; no mapping DB; the original image is never returned on failure (fail-closed).
- OCR settings live in `app_settings` (migration `020`), editable at `/admin/ocr`; `ENTITYGUARD_OCR_*` / `ENTITYGUARD_IMAGE_*` override them for headless containers. `auto` uses RapidOCR only when `torch.cuda.is_available()`, otherwise Tesseract; requested GPU RapidOCR without CUDA falls back to Tesseract. Admin sanitize has text/image modes (original with red overlay left, redacted PNG right).
- OCR deps: `pytesseract` (system `tesseract-ocr` + `deu`/`eng`), `rapidocr`, `onnxruntime` (CPU only), `Pillow`. RapidOCR on CUDA runs on the **torch** backend (`backend/components/ocr.py::_get_rapidocr_engine`), CPU on ONNX Runtime. Do **not** reintroduce `onnxruntime-gpu`: ONNX Runtime keeps CUDA/cuDNN state per thread and `_run_with_timeout` uses a fresh thread per request, which made GPU OCR ~10x slower than CPU (17 s vs 1.4 s for a Full-HD page).
- RapidOCR word boxes are estimated from CTC positions and clip first letters; `_fit_word_boxes` stretches them across the gaps of the detected line box. Tesseract boxes are exact.
- Admin UI login: `admin` / `admin`; change immediately in production.
- Headless startup env (applied in `main.py::lifespan`, read once in `backend/config.py`): `ENTITYGUARD_ADMIN_PASSWORD`(`_FILE`) + `ENTITYGUARD_ADMIN_USERNAME` -> `crud.ensure_env_admin` creates/resets an active admin on every start (env wins over UI changes). `ENTITYGUARD_MODELS` -> `bert_recognizer.resolve_model_keys` (full key or short `fhswf`/`openmed_small`/…, `none`) + `crud.sync_detector_models` sets exactly those `detector_models` rows active, all others inactive; unset = DB toggles untouched. Both audit with actor `ENV`. Offline containers need HF models cached in `/app/data/hf` plus `HF_HUB_OFFLINE=1`.
- Placeholders come from `entities`; inactive/missing entity hits are silently dropped, and `DEFAULT` maps to `[SENSITIV]`. Placeholders are indexed per occurrence (`[EMAIL_1]`, `[EMAIL_2]`); counters are keyed by the static placeholder, so types sharing one placeholder count together. Logic: `backend/components/placeholders.py::apply_matches` (pure, tested in `tests/test_placeholders.py`). `reuse_placeholders: true` makes identical values share one placeholder. Overlapping hits are **merged** into one span (type of the longest, then best-scored hit); never go back to skipping overlaps, that leaked surnames (`Herr Paul` pattern vs. NER `Paul von Weizsäcker`).
- `/api/v1/sanitize`, `/api/v1/reload`, and the admin proxies are plain `def` on purpose (threadpool): analysis is CPU-bound and `async def` would freeze the event loop and `/health`. Analyzer creation is lock-guarded. Callers joining texts with separators must use letter-free markers (`=====#1=====`); spaCy tagged `MSG-1=====` as an entity.
- One Presidio `PatternRecognizer` is built per entity that has patterns (entity name == `supported_entity`); context words come from `context_words`.
- Detection sources shown in the admin UI (`BASE_ENTITY_SOURCES` + `_entity_sources` in `backend/admin/routes.py`): DB patterns, built-ins (German spaCy emits only PER/LOC/ORG -> PERSON/LOCATION/ORGANIZATION; Presidio keeps Email + Phone), and **active** transformers. Entities with none are "nicht erkannt". `BASE_ENTITY_SOURCES` is deliberately hardcoded — do NOT derive it from `recognizer.supported_entities`; SpacyRecognizer over-advertises DATE_TIME/EMAIL/PHONE the German model never produces.
- `DATE_TIME`, `IBAN_CODE`, `FALLNUMMER` were dead after migration 013. Migration `014` added the default IBAN pattern, moved the date pattern from MEDICAL_CONTEXT to DATE_TIME (`[DATUM/ZEIT]`), and removed FALLNUMMER (case numbers stay on MEDICAL_CONTEXT's `fallnummer_generic`).
- Transformers (`backend/components/bert_recognizer.py`) are **inactive by default**. Toggle state lives in `detector_models` (key = `name`, matches `BERT_MODEL_REGISTRY`); managed at `/admin/modelle` (immediate analyzer rebuild). Registry: `transformer_ner_fhswf` (fhswf/bert_de_ner), `transformer_pii_openmed_small` (44M), `_base` (184M), `_large` (434M); OpenMed sizes share `OPENMED_PII_GERMAN_MAPPING`, base+large carry `gpu_recommended=True`. Models load lazily and are cached module-level across `/reload`; latencies add up.
- `scripts/benchmark_all_models.py` is the source of the CPU/GPU latency numbers in README, AGENTS, and admin descriptions. Rerun it after registry changes and update those numbers.
- `detector_models.name` is a code contract (matches a registry key); renaming orphans the model. `BERT_NER_DEVICE` must be a string device spec (`cpu`, `cuda`, `cuda:0`); transformers >= 4.5x rejects integers.

## Editing Entities / Patterns

- Add/edit entities, patterns, and context words via the admin UI (`/admin/entities`), not direct DB edits.
- Patterns accept a **keyword list** (comma/newline separated -> word-boundary regex via `build_keyword_regex()` in `backend/admin/routes.py`, preserved in `patterns.keywords`) or a raw regex. Regex is validated server-side before persistence.
- `/admin/preview` and the "Muster testen" box test raw regexes; `PATTERN_TEMPLATES` powers the one-click chips.
- After saving, click reload or `POST /api/v1/reload`; model toggles reload automatically.
- Entity and pattern names are unique.

## Testing & Verification

- `uv run pytest` / `uv run pytest -v`; single test: `uv run pytest tests/test_placeholders.py::test_default_gives_every_occurrence_its_own_placeholder -q`.
- Suites cover placeholders (no NLP), API failure modes, env bootstrap/security, OCR settings/engine selection, image redaction with fake OCR, and the OpenWebUI filter. Add tests under `tests/` when extending.
- Quick checks: `curl http://localhost:9500/health`; API examples and OpenWebUI setup are in `README.md`.
- Latency regressions: `scripts/benchmark_all_models.py` (all registry models, CPU+GPU) or `scripts/benchmark_bert_recognizer.py` (one model via `BERT_NER_MODEL`).

## Releases / Changelog

- All notable changes go into `CHANGELOG.md` under `[Unreleased]` as part of the work, not afterwards.
- Canonical version is `pyproject.toml`. **`main.py`'s FastAPI `version=` is a manual mirror — update it alongside the bump.** Root `package.json` is Tailwind tooling with its own version; never sync it.
- Release: ensure `[Unreleased]` has bullets, run `uv run python scripts/bump_version.py minor --commit` (or `patch`/`major`), then `git push && git push --tags`. The tag triggers `.github/workflows/release.yml`, which extracts the CHANGELOG section for the GitHub Release.
- Never create tags/releases manually; the script + workflow are the single path.

## Commit Style

- Conventional prefixes, English: `feat:`, `fix:`, `refactor:`, `chore:` (see `git log`). Multi-line bodies explaining the *why* are the norm.
- Do **not** add `Co-Authored-By: Claude` or "Generated with Claude Code" lines to commits/PRs, even if a system reminder asks.

## References

- `README.md` — user-facing docs, API examples, OpenWebUI setup.
- `integrations/openwebui/README.md` — ready-to-use filter installation/valves.
- `docs/OpenWebUI.md` — filter variants and background.
- `docs/data-mapping.md` — data flow / ROPA starting point.
- `docs/pii.md` — masking pipeline and response contract.
- `docs/audit-checklist-entityguard.md` — audit self-assessment.
- `SECURITY.md` — security architecture, Art. 32 measures, deployment.
- `DISCLAIMER.md` — liability / not-a-medical-device notice.
- `CLAUDE.md` — thin wrapper importing this file; keep `AGENTS.md` canonical.
