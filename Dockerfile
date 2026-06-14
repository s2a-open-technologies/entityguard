# EntityGuard - Docker Image
FROM python:3.13-slim

# Arbeitsverzeichnis
WORKDIR /app

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System-Abhängigkeiten für Presidio & spaCy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten installieren
COPY pyproject.toml uv.lock ./
RUN pip install --upgrade pip && \
    pip install uv && \
    uv sync --frozen

# spaCy NLP-Modell herunterladen
RUN python -m spacy download de_core_news_lg

# Anwendungscode kopieren
COPY src/ ./src/
COPY main.py ./

# Port exponieren
EXPOSE 9500

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9500/health || exit 1

# Anwendung starten
CMD ["python", "main.py"]
