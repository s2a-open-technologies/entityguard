# OpenWebUI Filter Integration

## Filter-Code

```python
"""
title: Health Guardrail Filter
author: Christopher Abanilla
version: 0.1

A filter for OpenWebUI that sanitizes user messages before sending them to the LLM.
It uses the Medical Chat Sanitizer API to detect and mask sensitive entities
according to GDPR and HIPAA regulations.
"""
import requests
import logging
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Filter:
    """
    OpenWebUI filter that sanitizes user input before LLM processing.

    This filter intercepts user messages, sends them to the Guardrails API
    for anonymization, and replaces the original text with the sanitized version.
    If the sanitization fails, the request is blocked (fail-closed principle).

    Attributes:
        valves (Valves): Configuration object containing API URL, department ID,
            and timeout settings.
    """

    class Valves(BaseModel):
        """
        Configuration valves for the filter.

        These settings can be configured via the OpenWebUI UI.

        Attributes:
            api_url (str): URL of the Guardrails sanitization endpoint.
            department_id (str): Department-specific rule set to apply
                (e.g., "standard", "psychiatrie", "cardio").
            timeout (int): Timeout in seconds for the API request.
        """
        api_url: str = Field(
            default="http://localhost:6000/api/v1/guardrails/sanitize",
            description="Guardrails API URL"
        )
        department_id: str = Field(
            default="standard",
            description="Which rule set to apply (e.g., psychiatrie, cardio)"
        )
        timeout: int = Field(
            default=5,
            description="Timeout in seconds for the security check"
        )

    def __init__(self):
        """Initialize the filter with default valve configuration."""
        self.valves = self.Valves()

    def inlet(self, body: Dict, __user__: Optional[Dict] = None) -> Dict:
        """
        Process the request body before sending to the LLM.

        This method is executed BEFORE the message is sent to the LLM.
        It extracts the last user message, sends it to the Guardrails API
        for sanitization, and replaces the original text with the sanitized version.

        Args:
            body (Dict): The request body containing the conversation messages.
            __user__ (Optional[Dict]): The current user information (unused).

        Returns:
            Dict: The modified request body with sanitized user message.

        Raises:
            Exception: If the sanitization API call fails, raises an exception
                to block the request (fail-closed principle).
        """
        messages = body.get("messages", [])
        if not messages:
            return body

        # Only check the last message from the user
        last_message = messages[-1]
        if last_message.get("role") != "user":
            return body

        user_text = last_message.get("content", "")

        # Prepare the request payload
        payload = {
            "text": user_text,
            "department": self.valves.department_id
        }

        try:
            response = requests.post(
                self.valves.api_url,
                json=payload,
                timeout=self.valves.timeout
            )

            response.raise_for_status()
            data = response.json()
            sanitized_text = data.get("sanitized_text")

            if sanitized_text is None:
                raise ValueError("Received invalid response")

            # Replace the original text with sanitized version
            body['messages'][-1]['content'] = sanitized_text

            logger.info(f"Guardrail active: Text sanitized for department '{self.valves.department_id}'.")
            return body

        except Exception as e:
            error_msg = f"Security check failed: {str(e)}"
            logger.error(error_msg)
            # In OpenWebUI, raising an exception stops the request to the LLM
            raise Exception(f"Privacy stop: {error_msg}")
```

---

## Installation des Filters

### 1. Filter in OpenWebUI hochladen

1. Öffne OpenWebUI im Browser
2. Gehe zu **Settings** (Zahnrad-Symbol unten links)
3. Klicke auf **Functions** (oder **Funktionen**)
4. Klicke auf **+ Add Function** (bzw. **Hinzufügen**)
5. Wähle **Create a new function**
6. Kopiere den obigen Filter-Code in das Editor-Feld
7. Klicke auf **Save**

---

## Konfiguration des Filters

Der Filter kann **global** oder **pro LLM-Modell** aktiviert werden.

### Option A: Globale Aktivierung (empfohlen)

Der Filter wird auf **alle Chat-Anfragen** angewendet, unabhängig vom verwendeten Modell.

**Schritte:**

1. Gehe zu **Settings** → **Functions**
2. Suche den `Health Guardrail Filter` in der Liste
3. Klicke auf das **Zahnrad-Symbol** (Einstellungen) neben dem Filter
4. Aktiviere die Option **Global** (bzw. **Enable as global filter**)
5. Konfiguriere die **Valves** (Einstellungen):

   | Einstellung | Beschreibung | Empfohlener Wert (Docker) |
   |-------------|--------------|---------------------------|
   | `api_url` | URL des Guardrails-Dienstes | `http://host.docker.internal:6000/api/v1/guardrails/sanitize` |
   | `department_id` | Regelwerk | `standard` |
   | `timeout` | Timeout in Sekunden | `5` |

6. Klicke auf **Save**

**Hinweis zur `api_url`:**

| Szenario | `api_url` |
|----------|-----------|
| OpenWebUI läuft **lokal** (nicht in Docker) | `http://localhost:6000/api/v1/guardrails/sanitize` |
| OpenWebUI läuft **in Docker** (gleiches Netzwerk) | `http://guardrails:6000/api/v1/guardrails/sanitize` |
| OpenWebUI läuft **in Docker** (anderes Netzwerk) | `http://host.docker.internal:6000/api/v1/guardrails/sanitize` |

---

### Option B: Aktivierung auf LLM-Ebene

Der Filter wird **nur für bestimmte Modelle** angewendet. Dies ist nützlich, wenn unterschiedliche Modelle unterschiedliche Datenschutz-Level benötigen.

**Schritte:**

1. Gehe zu **Settings** → **Models** (oder **Modelle**)
2. Wähle das gewünschte Modell aus (z.B. `llama3`, `gpt-4`, etc.)
3. Klicke auf das **Zahnrad-Symbol** oder **Edit** beim Modell
4. Suche den Abschnitt **Functions** / **Filter**
5. Wähle `Health Guardrail Filter` aus der Dropdown-Liste
6. Konfiguriere die **Valves** für dieses Modell:

   ```
   api_url: http://host.docker.internal:6000/api/v1/guardrails/sanitize
   department_id: standard
   timeout: 5
   ```

7. Klicke auf **Save**

**Wiederhole dies für jedes Modell**, das den Filter verwenden soll.

---

## Empfohlene Konfiguration für Docker-Umgebungen

Wenn sowohl OpenWebUI als auch der Guardrails-Dienst in Docker laufen:

### docker-compose.yml (erweitert)

```yaml
version: '3.8'

services:
  guardrails:
    build: .
    container_name: medical-chat-sanitizer
    ports:
      - "6000:6000"
    environment:
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - openwebui-network

  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: openwebui
    ports:
      - "3000:8080"
    environment:
      - OPENWEBUI_URL=http://localhost:3000
    depends_on:
      - guardrails
    networks:
      - openwebui-network
    restart: unless-stopped

networks:
  openwebui-network:
    driver: bridge
```

**Filter-Konfiguration in OpenWebUI:**

- `api_url`: `http://guardrails:6000/api/v1/guardrails/sanitize`
- `department_id`: `standard`
- `timeout`: `5`

---

## Fehlerbehebung

### Filter wird nicht ausgeführt

- Stelle sicher, dass der Filter **aktiviert** ist (global oder auf Modellebene)
- Überprüfe die **Logs** von OpenWebUI auf Fehlermeldungen

### "Connection refused" oder Timeout

- Überprüfe, ob der Guardrails-Dienst läuft: `docker ps` oder `http://localhost:6000/health`
- Korrigiere die `api_url` entsprechend deiner Umgebung (siehe Tabelle oben)

### Filter blockiert alle Anfragen

- Überprüfe die **Logs** des Guardrails-Dienstes: `docker logs medical-chat-sanitizer`
- Erhöhe ggf. das `timeout` auf `10` Sekunden
- Teste den Endpoint manuell:
  ```bash
  curl -X POST http://localhost:6000/api/v1/guardrails/sanitize \
    -H "Content-Type: application/json" \
    -d '{"text": "Test", "department": "standard"}'
  ```

---

## Abteilungsspezifische Regelwerke

Der Filter unterstützt verschiedene Regelwerke für unterschiedliche Abteilungen:

| `department_id` | Beschreibung |
|-----------------|--------------|
| `standard` | Standard-Regelwerk für allgemeine medizinische Kontexte |
| `psychiatrie` | Strengere Regeln für psychiatrische Daten (zukünftig erweiterbar) |
| `cardio` | Kardiologie-spezifische Regeln (zukünftig erweiterbar) |

Um ein neues Regelwerk hinzuzufügen, muss in `src/views/anonymizer_view.py` ein neuer Analyzer in der `_analyzer_registry` registriert werden.
