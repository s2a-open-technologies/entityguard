# OpenWebUI-Filter (Text + Bilder)

Fertiger Filter für OpenWebUI. Er maskiert den ganzen Chat-Kontext in einem
Aufruf und behandelt zusätzlich Bilder über `/api/v1/sanitize/image`.

## Installation

1. In OpenWebUI: **Settings → Functions → + Add Function → Create a new function**.
2. Inhalt von [`entityguard_filter.py`](entityguard_filter.py) einfügen und speichern.
3. Filter global oder pro Modell aktivieren.
4. Valves konfigurieren:

| Valve | Beschreibung | Beispiel |
|-------|--------------|----------|
| `api_url` | Text-Endpunkt | `http://entityguard:9500/api/v1/sanitize` |
| `image_api_url` | Bild-Endpunkt | `http://entityguard:9500/api/v1/sanitize/image` |
| `api_key` | API-Key aus EntityGuard | `eg_…` |
| `image_mode` | `block` (fail-closed) oder `redact` | `redact` für Bild-Chats |
| `timeout` | Text-Timeout in Sekunden | `5` |
| `image_timeout` | OCR-Timeout in Sekunden | `30` |
| `restore_mapping` | Platzhalter in der Antwort zurücksetzen | `true` |

## Verhalten

- **Text:** alle Textteile des Verlaufs werden mit `=====#N=====` verbunden,
  gemeinsam maskiert und anschließend wieder aufgeteilt.
- **Bilder:** `image_mode=block` bricht die Anfrage ab, sobald ein Bild
  enthalten ist. `image_mode=redact` schickt das Bild an EntityGuard, ersetzt
  es durch das redigierte PNG und zeigt es dem LLM nur geschwärzt.
- **Fail-Closed:** Dienst nicht erreichbar, ungültiger Key, OCR-Fehler,
  Timeout oder veränderte Trennmarken stoppen die Anfrage.
- Externe `http(s)`-Bild-URLs werden nicht abgerufen (SSRF-Schutz).

Details, Hintergründe und die einzelnen Filter-Varianten:
[`docs/OpenWebUI.md`](../../docs/OpenWebUI.md).
