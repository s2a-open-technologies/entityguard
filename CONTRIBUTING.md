# Contributing to EntityGuard

First off, thank you for considering contributing to EntityGuard! It's people
like you that make EntityGuard such a great tool.

## Code of Conduct

This project and everyone participating in it is governed by our
[Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to
uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid
duplicates. When you create a bug report, please include as many details as
possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples to demonstrate the steps**
- **Describe the behavior you observed and what behavior you expected**
- **Include the exact input text and the resulting `sanitized_text`/`mapping` when it is a detection issue**
- **Specify your environment:**
  - Python version: `python --version`
  - Docker version: `docker --version`
  - Operating system
  - Active detection sources (patterns / spaCy / which transformer models)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. Please provide:

- **Use a clear and descriptive title**
- **Provide a step-by-step description of the suggested enhancement**
- **Provide specific examples to demonstrate the enhancement**
- **Explain why this enhancement would be useful**

### Pull Requests

1. Fork the repository
2. Create a new branch from `master`: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run the checks (see below)
5. Commit your changes with a clear commit message
6. Push to your fork
7. Open a Pull Request

## Development Setup

### Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- Node.js (only for the Tailwind CSS build)

### Backend Setup

```bash
# Install dependencies
uv sync

# Download the German spaCy model (~500 MB, required)
uv run python -m spacy download de_core_news_lg

# Create schema and seed data
uv run alembic upgrade head

# Start the dev server (http://localhost:9500)
uv run python main.py
```

### Frontend / CSS

CSS is **compiled, not hand-edited.** Edit `frontend/static/css/tailwind-input.css`,
then:

```bash
npm run build:css     # one-off
npm run watch:css     # during development
```

`frontend/static/css/admin.css` is generated — never edit it directly.

## What to Check Before Submitting

```bash
uv run python -m compileall -q backend main.py   # syntax check
uv run pytest -v                                  # tests (add tests under tests/)
npm run build:css                                 # if you touched any CSS
```

There is currently **no formatter/linter/type-checker** configured — match the
existing style (4-space Python, Jinja2 templates, German user-facing strings).

## Security Guidelines

⚠️ **This is a security-focused application handling patient data. Security is critical.**

### Before Submitting Code

- [ ] **No hardcoded secrets** — API keys and passwords live hashed in the DB, never in source
- [ ] **Input validation** — all API inputs validated with Pydantic
- [ ] **SQL injection prevention** — use the SQLAlchemy ORM, never raw SQL string concatenation
- [ ] **Never log request text or the `mapping`** — tracing must stay content-free
- [ ] **Keep the API fail-closed** — no unauthenticated access (401) and no silent pass-through on error (500)
- [ ] **Regex patterns are validated** server-side before persistence

### Migrations

- Alembic migrations are the **only** source of schema, default entities/patterns,
  and the default admin user. Never document "just update the DB".
- New migration: `uv run alembic revision --autogenerate -m "description"`, then
  `uv run alembic upgrade head`. Files are numbered `00N_description.py` with
  plain string revisions (`revision = '013'`).

### Documentation

- All user-facing strings (UI, docs) are **German**.
- Add notable changes to the `[Unreleased]` section of [`CHANGELOG.md`](CHANGELOG.md)
  as part of the work, not afterwards.

## Commit Style

- Conventional prefixes, English: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- Multi-line bodies explaining the *why* are the norm.
