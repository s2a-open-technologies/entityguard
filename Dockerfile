# EntityGuard - Docker Image
FROM python:3.13-slim

# Arbeitsverzeichnis
WORKDIR /app

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1

# System-Abhängigkeiten für Presidio & spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv installieren
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Python-Abhängigkeiten installieren (nur Produktionsabhängigkeiten)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && \
    uv run python -c "import de_core_news_lg; print('spaCy model loaded:', de_core_news_lg.__name__)"

# Konfiguration und Migrationsskripte kopieren
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Anwendungscode kopieren
COPY src/ ./src/
COPY main.py ./

# Alembic-Migrationen anwenden (benötigt src-Modul)
RUN mkdir -p /app/data && \
    uv run alembic upgrade head

# Port exponieren
EXPOSE 9500

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9500/health || exit 1

# Anwendung starten
CMD ["uv", "run", "python", "main.py"]
