# EntityGuard - Docker Image
FROM python:3.13-slim

# TORCH_VARIANT=default -> torch aus PyPI (CUDA-Wheels auf amd64)
# TORCH_VARIANT=cpu     -> torch CPU-only (deutlich kleineres Image)
ARG TORCH_VARIANT=default

# Arbeitsverzeichnis
WORKDIR /app

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/data/hf

# System-Abhängigkeiten für Presidio & spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv installieren (gepinnt)
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /uvx /bin/

# Python-Abhängigkeiten installieren (nur Produktionsabhängigkeiten)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && \
    if [ "$TORCH_VARIANT" = "cpu" ]; then \
        uv pip install --python /app/.venv/bin/python --reinstall --no-deps torch \
            --index-url https://download.pytorch.org/whl/cpu && \
        uv pip uninstall --python /app/.venv/bin/python \
            $(/app/.venv/bin/python -c "import importlib.metadata as m; print(' '.join(sorted(d.metadata['Name'] for d in m.distributions() if d.metadata['Name'].lower().startswith(('nvidia-', 'triton')))))") \
            2>/dev/null || true; \
    fi && \
    python -c "import de_core_news_lg, torch; print('spaCy model loaded:', de_core_news_lg.__name__, '| torch', torch.__version__)"

# Konfiguration und Migrationsskripte kopieren
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Anwendungscode kopieren
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY main.py ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Nicht-root-Benutzer; /app/data (SQLite, HF-Cache) gehört ihm
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    useradd --system --uid 10001 --home-dir /app entityguard && \
    mkdir -p /app/data && \
    chown -R entityguard:entityguard /app/data
USER entityguard

# Port exponieren
EXPOSE 9500

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9500/health || exit 1

# Migrationen anwenden, dann Anwendung starten
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "main.py"]
