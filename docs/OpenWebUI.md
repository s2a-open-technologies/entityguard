# OpenWebUI Filter Integration

## Filter-Code

```python
"""
title: EntityGuard Filter
author: Christopher Abanilla
version: 0.1

A filter for OpenWebUI that sanitizes user messages before sending them to the LLM.
It uses the EntityGuard API to detect and mask sensitive entities
according to GDPR and HIPAA regulations.
"""
import requests
import logging
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# Hinweis: Die API liefert zusätzlich ein `mapping` (Platzhalter -> Originalwert),
# das hier bewusst NICHT verwendet wird - das LLM soll nur den maskierten Text
# sehen. Für eine spätere De-Anonymisierung müsste der Aufrufer das Mapping
# selbst aufbewahren.

logger = logging.getLogger(__name__)


class Filter:
    """
    OpenWebUI filter that sanitizes user input before LLM processing.

    This filter intercepts user messages, sends them to the EntityGuard API
    for anonymization, and replaces the original text with the sanitized version.
    If the sanitization fails, the request is blocked (fail-closed principle).

    Attributes:
        valves (Valves): Configuration object containing API URL
            and timeout settings.
    """

    class Valves(BaseModel):
        """
        Configuration valves for the filter.

        These settings can be configured via the OpenWebUI UI.

        Attributes:
            api_url (str): URL of the EntityGuard sanitization endpoint.
            api_key (str): API key created in the EntityGuard admin UI.
            timeout (int): Timeout in seconds for the API request.
        """
        api_url: str = Field(
            default="http://localhost:9500/api/v1/sanitize",
            description="EntityGuard API URL"
        )
        api_key: str = Field(
            default="",
            description="EntityGuard API key (create under API-Schlüssel in the admin UI)"
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
        It extracts the last user message, sends it to the EntityGuard API
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
            "text": user_text
        }

        try:
            response = requests.post(
                self.valves.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.valves.api_key}"},
                timeout=self.valves.timeout
            )

            response.raise_for_status()
            data = response.json()
            sanitized_text = data.get("sanitized_text")

            if sanitized_text is None:
                raise ValueError("Received invalid response")

            # Replace the original text with sanitized version
            body['messages'][-1]['content'] = sanitized_text

            logger.info("Guardrail active: Text sanitized.")
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
2. Suche den `EntityGuard Filter` in der Liste
3. Klicke auf das **Zahnrad-Symbol** (Einstellungen) neben dem Filter
4. Aktiviere die Option **Global** (bzw. **Enable as global filter**)
5. Konfiguriere die **Valves** (Einstellungen):

   | Einstellung | Beschreibung | Empfohlener Wert (Docker) |
   |-------------|--------------|---------------------------|
   | `api_url` | URL des EntityGuard-Dienstes | `http://host.docker.internal:9500/api/v1/sanitize` |
   | `api_key` | API-Schlüssel aus dem Admin-UI (**API-Schlüssel**) | `eg_…` |
   | `timeout` | Timeout in Sekunden | `5` |

6. Klicke auf **Save**

**Hinweis zu `api_url` und `api_key`:**

| Szenario | `api_url` |
|----------|-----------|
| OpenWebUI läuft **lokal** (nicht in Docker) | `http://localhost:9500/api/v1/sanitize` |
| OpenWebUI läuft **in Docker** (gleiches Netzwerk) | `http://entityguard:9500/api/v1/sanitize` |
| OpenWebUI läuft **in Docker** (anderes Netzwerk) | `http://host.docker.internal:9500/api/v1/sanitize` |

Den `api_key` erzeugst du in EntityGuard unter **API-Schlüssel** (der Klartext
wird nur einmal angezeigt). Ohne aktiven Schlüssel antwortet die API mit 401.

---

### Option B: Aktivierung auf LLM-Ebene

Der Filter wird **nur für bestimmte Modelle** angewendet. Dies ist nützlich, wenn unterschiedliche Modelle unterschiedliche Datenschutz-Level benötigen.

**Schritte:**

1. Gehe zu **Settings** → **Models** (oder **Modelle**)
2. Wähle das gewünschte Modell aus (z.B. `llama3`, `gpt-4`, etc.)
3. Klicke auf das **Zahnrad-Symbol** oder **Edit** beim Modell
4. Suche den Abschnitt **Functions** / **Filter**
5. Wähle `EntityGuard Filter` aus der Dropdown-Liste
6. Konfiguriere die **Valves** für dieses Modell:

   ```
    api_url: http://host.docker.internal:9500/api/v1/sanitize
    api_key: eg_…
   timeout: 5
   ```

7. Klicke auf **Save**

**Wiederhole dies für jedes Modell**, das den Filter verwenden soll.

---

## Antwort-De-Anonymisierung mit dem `mapping`

Standardmäßig sieht das LLM nur den maskierten Text und antwortet mit den
Platzhaltern (`[NAME_1]` …). Wenn der Nutzer in der Antwort wieder die
Originalwerte sehen soll, kann der Filter diese clientseitig zurücksetzen —
das LLM bekommt die Klardaten dabei **nie** zu sehen.

Dafür nutzt man zwei Haken:

- `inlet()` läuft **vor** dem LLM, maskiert die Nachricht und legt das von
  EntityGuard gelieferte `mapping` (Platzhalter → Original) im speziellen
  `__metadata__`-Dict ab.
- `outlet()` läuft **nach** der LLM-Antwort und ersetzt die Platzhalter darin
  wieder durch die Originalwerte.

`__metadata__` wird pro Request durchgereicht, `outlet()` sieht also genau das
`mapping` der aktuellen Anfrage.

### Erweiterter Filter-Code

```python
import requests
import logging
from pydantic import BaseModel, Field
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def _restore(text: str, mapping: Dict[str, str]) -> str:
    # Längste Platzhalter zuerst, damit z. B. [NAME_10] nicht in [NAME_1] zerfällt.
    for placeholder in sorted(mapping, key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(
            default="http://localhost:9500/api/v1/sanitize",
            description="EntityGuard API URL"
        )
        api_key: str = Field(
            default="",
            description="EntityGuard API key (create under API-Schlüssel in the admin UI)"
        )
        timeout: int = Field(
            default=5,
            description="Timeout in seconds for the security check"
        )
        restore_mapping: bool = Field(
            default=True,
            description="Platzhalter in der LLM-Antwort durch die Originalwerte ersetzen"
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(
        self,
        body: Dict,
        __metadata__: dict = None,
        __user__: Optional[Dict] = None,
    ) -> Dict:
        messages = body.get("messages", [])
        if not messages or messages[-1].get("role") != "user":
            return body

        user_text = messages[-1].get("content", "")
        try:
            response = requests.post(
                self.valves.api_url,
                json={"text": user_text},
                headers={"Authorization": f"Bearer {self.valves.api_key}"},
                timeout=self.valves.timeout,
            )
            response.raise_for_status()
            data = response.json()
            sanitized_text = data.get("sanitized_text")
            if sanitized_text is None:
                raise ValueError("Received invalid response")

            body["messages"][-1]["content"] = sanitized_text

            # mapping für die Rückübersetzung in outlet() merken (pro Request).
            if __metadata__ is not None:
                __metadata__["entityguard_mapping"] = data.get("mapping", {})

            logger.info("Guardrail active: Text sanitized.")
            return body

        except Exception as e:
            error_msg = f"Security check failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(f"Privacy stop: {error_msg}")

    def outlet(self, body: Dict, __metadata__: dict = None) -> Dict:
        if not self.valves.restore_mapping or not __metadata__:
            return body

        mapping = __metadata__.get("entityguard_mapping") or {}
        if not mapping:
            return body

        for message in body.get("messages", []):
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                message["content"] = _restore(message["content"], mapping)
        return body
```

### Einschränkungen

- **`outlet()` läuft nicht für alle Pfade.** Es greift bei normalen
  WebUI-Chats und beim Inline-Outlet von `/api/chat/completions`, **nicht**
  aber bei `/api/chat/completed` (dort wird ein frisches `__metadata__` ohne
  das `mapping` aufgebaut).
- **Nur die aktuelle Anfrage.** `__metadata__` lebt pro Request. Platzhalter
  aus früheren Nachrichten (Mehr-Turn-Verlauf) kennt `outlet()` nicht; dafür
  bräuchte man ein persistentes Platzhalter-Register (z. B. serverseitig in
  EntityGuard).
- **Nur die Ausgabe.** Die Rückübersetzung ist rein clientseitig. Das LLM hat
  die Originalwerte nie gesehen; nur der Nutzer sieht sie wieder.
- Wer die De-Anonymisierung nicht braucht, lässt `restore_mapping` einfach auf
  `false` — dann bleibt es beim reinen Einweg-Maskieren aus dem
  [Filter-Code](#filter-code) oben.

---

## Empfohlene Konfiguration für Docker-Umgebungen

Wenn sowohl OpenWebUI als auch der EntityGuard-Dienst in Docker laufen:

### docker-compose.yml (erweitert)

```yaml
version: '3.8'

services:
  entityguard:
    build: .
    container_name: entityguard
    ports:
      - "9500:9500"
    environment:
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9500/health"]
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
      - entityguard
    networks:
      - openwebui-network
    restart: unless-stopped

networks:
  openwebui-network:
    driver: bridge
```

**Filter-Konfiguration in OpenWebUI:**

- `api_url`: `http://entityguard:9500/api/v1/sanitize`
- `api_key`: `eg_…` (unter **API-Schlüssel** im Admin-UI erzeugen)
- `timeout`: `5`

---

## Fehlerbehebung

### Filter wird nicht ausgeführt

- Stelle sicher, dass der Filter **aktiviert** ist (global oder auf Modellebene)
- Überprüfe die **Logs** von OpenWebUI auf Fehlermeldungen

### "Connection refused" oder Timeout

- Überprüfe, ob der EntityGuard-Dienst läuft: `docker ps` oder `http://localhost:9500/health`
- Korrigiere die `api_url` entsprechend deiner Umgebung (siehe Tabelle oben)

### Filter blockiert alle Anfragen

  - Überprüfe die **Logs** des EntityGuard-Dienstes: `docker logs entityguard`
- Erhöhe ggf. das `timeout` auf `10` Sekunden
- Prüfe, ob ein **aktiver API-Schlüssel** existiert und in den Valves als
  `api_key` eingetragen ist (sonst HTTP 401)
- Teste den Endpoint manuell:
  ```bash
  curl -X POST http://localhost:9500/api/v1/sanitize \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer eg_…" \
    -d '{"text": "Test"}'
  ```
