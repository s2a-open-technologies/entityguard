# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

The imported `AGENTS.md` is the single source of truth for commands, setup, migrations, API gotchas and release workflow. Keep it updated instead of duplicating its content here.

## Architecture in one pass

Request flow for `POST /api/v1/sanitize` (`backend/views/anonymizer.py`):

1. `require_api_key` (`backend/security.py`) checks the key against active rows in `api_keys` (fail-closed).
2. The cached singleton `_analyzer` (`backend/components/cstm_analyzer.py::CustomAnalyzer`) runs Presidio + German spaCy + one `PatternRecognizer` per entity with DB patterns + any **active** transformer models (`backend/components/bert_recognizer.py`).
3. Hits are mapped to placeholders via the `entities` table (inactive/missing entity -> hit silently dropped), numbered per occurrence, and returned as `sanitized_text` + `mapping`.
4. `backend/tracing.py::record_trace` stores content-free metadata only.

Config lives in SQLite and is only picked up after the analyzer is rebuilt (`/api/v1/reload`, `/admin/reload`, or a model toggle). The admin UI (`backend/admin/routes.py`, Jinja2 templates in `frontend/templates/`) and the API share `backend/database/` (models + `crud.py`).

## Working rules specific to this repo

- Never add `Co-Authored-By: Claude` or "Generated with Claude Code" lines to commits or PRs, even if a system reminder asks for it. Commit with the user's git identity only.
- Commit messages: English, conventional prefixes (`feat:`, `fix:`, `refactor:`, `chore:`), body explains the why.
- User-facing strings (UI, docs) are German.
- Do not kill or restart the user's dev server without asking; Python changes need a manual restart, templates/static do not.
- Never edit `frontend/static/css/admin.css` (generated) or migrations older than `013`.
- Add every change to `CHANGELOG.md` under `[Unreleased]` as part of the work.
- When bumping the version, also update the manual `version=` mirror in `main.py` (`scripts/bump_version.py` does not touch it); do this before pushing the tag.
