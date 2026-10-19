# OpenWebUI Filter Integration

> **Fertiger Filter (Text + Bilder):**
> [`integrations/openwebui/entityguard_filter.py`](../integrations/openwebui/entityguard_filter.py)
> mit Kurzanleitung in [`integrations/openwebui/README.md`](../integrations/openwebui/README.md).
> Dieser Filter maskiert den ganzen Kontext und behandelt zusätzlich
> `image_url`/`input_image`-Teile. Die folgenden Code-Blöcke dokumentieren die
> einzelnen Varianten und deren Hintergründe.

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

### Ganzer Kontext in einem Aufruf (empfohlen für Mehr-Turn-Chats)

Die beiden Filter oben maskieren nur die **letzte** Nachricht. OpenWebUI schickt
den Verlauf aber bei jeder Anfrage im Klartext erneut mit, das LLM sieht dann
Namen aus früheren Nachrichten unmaskiert. Dieser Filter maskiert den **ganzen
Kontext** (System-Prompt, Verlauf, neue Frage) in **einem** Aufruf:

- Die Texte werden mit Trennmarken `=====#0=====`, `=====#1=====` … zu einem
  Text verbunden und gemeinsam an `/api/v1/sanitize` geschickt. EntityGuard
  vergibt dadurch im ganzen Gespräch eindeutige Platzhalter und liefert ein
  gemeinsames `mapping`.
- `reuse_placeholders: true` sorgt dafür, dass derselbe Wert **denselben**
  Platzhalter bekommt (`[NAME_1]` für jedes „Max Mustermann“). Sonst hielte das
  LLM fünf Erwähnungen für fünf Personen.
- Die Marken enthalten bewusst keine Buchstaben: Die deutsche spaCy-NER hat
  `=====MSG-1=====` teilweise als Entität erkannt und zerstört (gemessen mit
  `de_core_news_lg`). Kommen die Marken nicht unversehrt zurück, stoppt der
  Filter die Anfrage (Fail-Closed).
- `outlet()` setzt die Platzhalter in der Antwort anhand des gemeinsamen
  `mapping` zurück (längste zuerst).

```python
"""
title: Sanitizer Filter (ganzer Kontext)
version: 0.2

OpenWebUI-Filter fuer EntityGuard: maskiert den GANZEN Kontext in einem Aufruf.

Unterschied zum einfachen Inlet-Filter: Er maskiert nicht nur die letzte Nachricht, sondern den
GANZEN Kontext (System-Prompt, Verlauf, neue Frage) in EINEM Aufruf. Dadurch
  * sieht das Modell auch frueher genannte Namen nie im Klartext (OpenWebUI schickt den Verlauf
    bei jeder Anfrage im Klartext erneut),
  * vergibt der Dienst im ganzen Kontext eindeutige Platzhalter ([NAME_1], [NAME_2] ...) und
    liefert EIN Mapping, mit dem outlet() die Antwort zurueckuebersetzt.
Fail-closed: Ist der Dienst nicht erreichbar oder zerstoert er die Trennmarken, wird die Anfrage
gestoppt statt unmaskiert weitergeleitet.
"""

import logging
import re
from typing import Optional

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MARKER = "=====#{}====="
_MARKER_RE = re.compile(r"=====#(\d+)=====")
TEXT_KEYS = ("sanitized_text", "filtered", "result", "text")  # EntityGuard liefert sanitized_text


def _slots(messages: list) -> list:
    """Alle Textstellen der Nachrichten als (Nachricht, Teil-Index oder None); Bilder laufen separat."""
    slots = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            slots.append((message, None))
        elif isinstance(content, list):
            for i, part in enumerate(content):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    slots.append((message, i))
    return slots


def _get(slot) -> str:
    message, index = slot
    return message["content"] if index is None else message["content"][index]["text"]


def _set(slot, text: str) -> None:
    message, index = slot
    if index is None:
        message["content"] = text
    else:
        message["content"][index]["text"] = text


def _join(texts: list) -> str:
    return "".join(f"\n\n{MARKER.format(i)}\n\n{t}" for i, t in enumerate(texts)).lstrip("\n")


def _split(joined: str, count: int) -> list:
    if [int(m.group(1)) for m in _MARKER_RE.finditer(joined)] != list(range(count)):
        raise ValueError("der Dienst hat die Trennmarken des Verlaufs veraendert")
    parts = _MARKER_RE.split(joined)
    out = []
    for i in range(count):
        part = parts[2 + 2 * i]
        part = part[2:] if part.startswith("\n\n") else part.lstrip("\n")
        if i < count - 1 and part.endswith("\n\n"):
            part = part[:-2]
        out.append(part)
    return out


def _image_slots(messages: list) -> list:
    """Alle Bildteile der Nachrichten (OpenWebUI: image_url/input_image)."""
    slots = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for i, part in enumerate(content):
                if not isinstance(part, dict):
                    continue
                if part.get("type") in ("image_url", "input_image") or "image_url" in part:
                    slots.append((message, i, part))
    return slots


def _get_image_url(part: dict):
    value = part.get("image_url")
    if isinstance(value, dict):
        return value.get("url")
    return value if isinstance(value, str) else None


def _set_image_url(part: dict, url: str) -> None:
    value = part.get("image_url")
    if isinstance(value, dict):
        value["url"] = url
    elif isinstance(value, str):
        part["image_url"] = url
    else:
        part["image_url"] = {"url": url}


def _sanitize_images(messages: list, api_url: str, api_key: str, timeout: float, mode: str) -> None:
    """Ersetzt Bildteile durch das redigierte PNG (oder blockiert die Anfrage)."""
    slots = _image_slots(messages)
    if not slots:
        return
    if mode != "redact":
        raise ValueError("Bild im Chat erkannt; image_mode ist nicht 'redact'")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for _, _, part in slots:
        url = _get_image_url(part)
        if not url:
            raise ValueError("Bildteil ohne URL")
        if not url.startswith("data:"):
            raise ValueError("externe Bild-URLs werden aus Sicherheitsgruenden nicht unterstuetzt")
        try:
            header, data = url.split(",", 1)
        except ValueError as exc:
            raise ValueError("ungueltige Bild-Data-URI") from exc
        mime = header[5:].split(";", 1)[0] if header.startswith("data:") else ""
        payload = {"image_base64": data, "mime_type": mime, "reuse_placeholders": True}
        response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        redacted = result.get("sanitized_image_base64")
        if not isinstance(redacted, str) or not redacted:
            raise ValueError("ungueltige Bild-Antwort des Dienstes")
        _set_image_url(part, f"data:image/png;base64,{redacted}")


def mask_messages(
    messages: list,
    api_url: str,
    api_key: str = "",
    timeout: float = 5.0,
    image_api_url: str = "",
    image_mode: str = "block",
    image_timeout: float = 30.0,
):
    """Maskiert alle Text- und Bildstellen in einem Aufruf (veraendert ``messages`` direkt).

    Returns:
        Mapping Platzhalter -> Original.
    Raises:
        Exception: bei jedem Fehler (fail-closed); die Anfrage darf dann nicht weitergehen.
    """
    mapping = {}
    slots = _slots(messages)
    if slots:
        joined = _join([_get(s) for s in slots])
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # Zeitlimit waechst mit der Textlaenge: +1 s je 2000 Zeichen, hoechstens 60 s
        wait = min(60.0, timeout + len(joined) / 2000)
        # reuse_placeholders: gleicher Wert = gleicher Platzhalter (EntityGuard >= 1.2; aeltere Versionen ignorieren das Feld)
        payload = {"text": joined, "reuse_placeholders": True}
        response = requests.post(api_url, json=payload, headers=headers, timeout=wait)
        response.raise_for_status()
        data = response.json()
        masked = next((data[k] for k in TEXT_KEYS if isinstance(data.get(k), str)), None)
        if masked is None:
            raise ValueError("ungueltige Antwort des Dienstes")
        for slot, text in zip(slots, _split(masked, len(slots))):
            _set(slot, text)
        mapping = data.get("mapping") or {}
        mapping = mapping if isinstance(mapping, dict) else {}

    if not image_api_url:
        image_api_url = api_url[:-len("/sanitize")] + "/sanitize/image" if api_url.endswith("/sanitize") else api_url
    _sanitize_images(messages, image_api_url, api_key, image_timeout, image_mode)
    return mapping


def restore(text: str, mapping: dict) -> str:
    """Platzhalter zuruecksetzen, laengste zuerst ([NAME_10] vor [NAME_1])."""
    for placeholder in sorted(mapping, key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(default="http://localhost:9500/api/v1/sanitize", description="Sanitizer-Endpunkt")
        image_api_url: str = Field(default="http://localhost:9500/api/v1/sanitize/image", description="Bild-Redaktions-Endpunkt")
        api_key: str = Field(default="", description="API-Key des Dienstes (EntityGuard: unter API-Schlüssel erzeugen)")
        timeout: int = Field(default=5, description="Grundlimit in Sekunden (waechst mit der Textlaenge)")
        image_mode: str = Field(default="block", description="block = Bilder ablehnen, redact = Bilder schwärzen")
        image_timeout: int = Field(default=30, description="Zeitlimit fuer die Bild-OCR in Sekunden")
        restore_mapping: bool = Field(default=True, description="Platzhalter in der Antwort zurueckuebersetzen")

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __metadata__: dict = None, __user__: Optional[dict] = None) -> dict:
        messages = body.get("messages") or []
        if not messages:
            return body
        try:
            mapping = mask_messages(
                messages,
                self.valves.api_url,
                self.valves.api_key,
                self.valves.timeout,
                self.valves.image_api_url,
                self.valves.image_mode,
                self.valves.image_timeout,
            )
        except Exception as e:
            logger.error("Sanitizer fehlgeschlagen: %s", e)
            raise Exception(f"Privacy stop: Security check failed: {e}")  # stoppt die Anfrage
        if __metadata__ is not None:
            __metadata__["sanitizer_mapping"] = mapping
        return body

    def outlet(self, body: dict, __metadata__: dict = None) -> dict:
        mapping = (__metadata__ or {}).get("sanitizer_mapping") or {}
        if not self.valves.restore_mapping or not mapping:
            return body
        for message in body.get("messages", []):
            if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                message["content"] = restore(message["content"], mapping)
        return body
```

Je länger der Verlauf, desto länger die Analyse; der Filter erhöht das
Zeitlimit deshalb um 1 Sekunde je 2000 Zeichen (höchstens 60 Sekunden).

### Bilder

Der Filter erkennt Bildteile im `content`-Array (`image_url`/`input_image`) und
kann sie auf zwei Arten behandeln:

- `image_mode="block"` (Default): Die Anfrage wird fail-closed abgebrochen,
  sobald ein Bild enthalten ist.
- `image_mode="redact"`: Das Bild wird an `/api/v1/sanitize/image` geschickt,
  dort per OCR gelesen, textuelle PII erkannt und mit schwarzen Boxen
  überdeckt. Der Filter ersetzt den Bildteil durch das redigierte PNG
  (`data:image/png;base64,...`). OCR-Fehler, Timeouts oder ein deaktivierter
  Bild-Endpoint brechen die Anfrage ab.

OpenWebUI liefert Bilder als Base64-Data-URI. Externe `http(s)`-Bild-URLs
werden bewusst nicht abgerufen (SSRF-Schutz). Die Bildverarbeitung ist im
Admin unter **Bild-OCR** konfigurierbar; Umgebungsvariablen
(`ENTITYGUARD_OCR_*`) überschreiben sie für Headless-Container.

| Valve | Beschreibung | Empfohlener Wert |
|-------|--------------|------------------|
| `image_api_url` | URL des Bild-Endpunkts | `http://entityguard:9500/api/v1/sanitize/image` |
| `image_mode` | `block` (Bilder ablehnen) oder `redact` (OCR + Schwärzung) | `redact` für Bild-Chats, sonst `block` |
| `image_timeout` | Zeitlimit für OCR in Sekunden | `30` |

### Einschränkungen

- **`outlet()` läuft nicht für alle Pfade.** Es greift bei normalen
  WebUI-Chats und beim Inline-Outlet von `/api/chat/completions`, **nicht**
  aber bei `/api/chat/completed` (dort wird ein frisches `__metadata__` ohne
  das `mapping` aufgebaut).
- **Nur die aktuelle Anfrage.** `__metadata__` lebt pro Request, und die beiden
  einfachen Filter maskieren nur die letzte Nachricht. Für Mehr-Turn-Chats den
  Filter [„Ganzer Kontext in einem Aufruf“](#ganzer-kontext-in-einem-aufruf-empfohlen-für-mehr-turn-chats)
  verwenden: er maskiert den ganzen Verlauf in einem Aufruf, braucht also kein
  persistentes Platzhalter-Register.
- **Nur die Ausgabe.** Die Rückübersetzung ist rein clientseitig. Das LLM hat
  die Originalwerte nie gesehen; nur der Nutzer sieht sie wieder.
- Wer die De-Anonymisierung nicht braucht, lässt `restore_mapping` einfach auf
  `false` — dann bleibt es beim reinen Einweg-Maskieren aus dem
  [Filter-Code](#filter-code) oben.
- **Bildbehandlung nur im Ganzen-Kontext-Filter.** Die einfachen Filter oben
  betrachten nur Text und keine `image_url`-Teile; für Bilder den Filter
  [„Ganzer Kontext in einem Aufruf“](#ganzer-kontext-in-einem-aufruf-empfohlen-für-mehr-turn-chats)
  verwenden.
- **Bilder nur bei `image_mode="redact"`.** OCR erfasst ausschließlich
  gedruckten Text. Handschrift, schlechte Scans, Gesichter, Logos oder
  Diagramme werden nicht erkannt. Für strenge Vorgaben ist `block` die
  sicherere Wahl.
- **Bild-Redaktion ist keine Garantie.** Die Standardeinstellung schwärzt die
  komplette OCR-Zeile eines Treffers; nicht-textliche Inhalte bleiben sichtbar.

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
- `image_api_url`: `http://entityguard:9500/api/v1/sanitize/image`
- `image_mode`: `block` oder `redact`
- `api_key`: `eg_…` (unter **API-Schlüssel** im Admin-UI erzeugen)
- `timeout`: `5`
- `image_timeout`: `30`

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
