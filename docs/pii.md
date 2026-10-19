# PII-Maskierungs-Pipeline

Flussdiagramm und Vertrag des Verarbeitungswegs, den EntityGuard pro Anfrage
durchläuft. EntityGuard ist die Sanitizer-Seite; der Aufrufer (z. B. openDox,
OpenWebUI, eine Klinik-App) entscheidet, was mit dem maskierten Text und dem
`mapping` weiter geschieht.

```mermaid
flowchart TD
    A([Aufrufer sendet Text]) --> B["POST /api/v1/sanitize<br>Authorization: Bearer eg_…"]
    B --> C{"Aktiver API-Key<br>vorhanden & gültig?"}
    C -- Nein --> Z["HTTP 401<br>fail-closed"]
    C -- Ja --> D["AnalyzerEngine.analyze()"]

    D --> E1["Presidio<br>Email + Phone"]
    D --> E2["spaCy de_core_news_lg<br>PER/LOC/ORG"]
    D --> E3["PatternRecognizer je Entität<br>(Muster + Kontextwörter)"]
    D --> E4["aktive Transformer-Modelle<br>(optional)"]

    E1 --> F["Erkannte Spans<br>(Start, Ende, Typ, Score)"]
    E2 --> F
    E3 --> F
    E4 --> F

    F --> G["Überlappungen auflösen<br>+ Platzhalter je Vorkommen<br>[PERSON_1], [PERSON_2] …"]
    G --> H["sanitized_text + mapping<br>(Platzhalter → Original)"]
    H --> I["HTTP 200 an den Aufrufer"]
    G --> T["record_trace()<br>nur Metadaten, kein Text"]
```

## Bild-Pipeline (`/api/v1/sanitize/image`)

Bilder werden **nur im Speicher** verarbeitet und nie gespeichert. Der
Ablauf:

```mermaid
flowchart TD
    A([Bild als Base64]) --> B["POST /api/v1/sanitize/image"]
    B --> C{"API-Key gültig?"}
    C -- Nein --> Z["HTTP 401<br>fail-closed"]
    C -- Ja --> D["Bild validieren<br>PNG/JPEG/WebP, Größen-/Pixel-Limits, EXIF entfernen"]
    D --> E["OCR<br>Tesseract (CPU) oder RapidOCR (GPU/CPU)"]
    E --> F["OCR-Text + Zeilen-/Wortboxen"]
    F --> G["CustomAnalyzer.analyze_text()"]
    G --> H["Entitäten auf Boxen abbilden<br>Standard: ganze OCR-Zeile"]
    H --> I["Boxen schwarz überdecken"]
    I --> J["PNG → Base64"]
    J --> K["Antwort: Bild + OCR-Text + mapping + Boxen"]
```

- **Engine:** `auto` nutzt RapidOCR nur bei verfügbarer CUDA-GPU, sonst
  Tesseract. Eine angeforderte RapidOCR-GPU ohne CUDA fällt auf Tesseract
  zurück.
- **Schwärzung:** `line` (Default) schwärzt die komplette OCR-Zeile eines
  Treffers, `entity` nur die erkannten Wörter, `all_text` jeden erkannten
  Text. OCR-Zeilen unter `OCR_MIN_CONFIDENCE` werden zusätzlich konservativ
  geschwärzt. RapidOCR liefert Zeilenboxen; `entity` schwärzt dort daher
  ebenfalls die ganze Zeile.
- **Kein Mapping-Speicher:** Das `mapping` gehört zum maskierten OCR-Text und
  wird wie beim Text-Endpoint nur in der Antwort zurückgegeben. Für das Bild
  gibt es keine De-Anonymisierung; das redigierte PNG ist das Endergebnis.
- **Grenzen:** OCR erfasst nur gedruckten Text. Handschrift, Gesichter, Logos,
  Diagramme und schlechte Scans bleiben unerkannt. `ENTITYGUARD_OCR_VERIFY`
  kann das redigierte Bild erneut prüfen und bei Rest-Treffern fail-closed
  abbrechen.

## Erkennungsquellen

| Quelle | Erkennt | Code |
|---|---|---|
| **Presidio** (Standard) | E-Mail (`EMAIL_ADDRESS`), Telefon (`PHONE_NUMBER`) | `_remove_builtin_recognizers()` behält nur `SpacyRecognizer`, `EmailRecognizer`, `PhoneRecognizer` |
| **spaCy** `de_core_news_lg` | Personen, Orte, Organisationen (`PER`/`LOC`/`ORG`) — die deutsche NER emittiert **nur** diese drei | Presidio `SpacyRecognizer` |
| **Muster** (pro Entität) | Freie Regex bzw. Stichwortliste | ein `PatternRecognizer` pro Entität mit Mustern; Kontextwörter aus `context_words` |
| **Transformer-Modelle** (optional) | je nach Modell Namen/Orte/Organisationen oder strukturierte PII | `backend/components/bert_recognizer.py`, `BERT_MODEL_REGISTRY`; standardmäßig inaktiv |

Wodurch eine Entität tatsächlich erkannt wird, zeigt das Admin-UI pro Entität
(`BASE_ENTITY_SOURCES` + `_entity_sources`); Entitäten ohne Quelle werden als
„nicht erkannt" markiert.

## Response-Contract

```json
{
  "sanitized_text": "Herr [PERSON_1] aus [LOCATION_1]",
  "mapping": {"[PERSON_1]": "Müller", "[LOCATION_1]": "Berlin"}
}
```

- **Eindeutige Tokens pro Vorkommen**: Platzhalter werden durchnummeriert
  (`[PERSON_1]`, `[PERSON_2]`, …), nicht nur pro Kategorie. Damit kollidieren
  mehrere Vorkommen derselben Entität nicht im `mapping`-Dict. Gezählt wird je
  **Platzhalter** (nicht je Entitätstyp): Typen, die sich einen Platzhalter
  teilen (z. B. IBAN und der Fallback `[SENSITIV]`), laufen in einer Zählung.
- **Optional: gleicher Wert, gleicher Platzhalter**: Mit
  `"reuse_placeholders": true` im Request bekommt ein identischer Wert (exakt
  gleicher Text, gleicher Platzhalter) überall denselben Token; das `mapping`
  hat einen Eintrag je Wert. Gedacht für ganze Gespräche in einem Aufruf.
- **Platzhalter kommen aus der `entities`-Tabelle**: Ist eine Entität inaktiv
  oder hat keine DB-Zeile, werden ihre Treffer verworfen (kein Platzhalter).
  Der Fallback `[SENSITIV]` greift nur, wenn ein erkannter Typ keine Zeile hat.
- **Das `mapping` geht an den Aufrufer zurück, nicht ans LLM.** Der Aufrufer
  kann damit später de-anonymisieren (z. B. OpenWebUI `outlet()`), muss das
  Mapping aber selbst aufbewahren. EntityGuard speichert es **nicht**.

## Fail-Closed-Verhalten

- **Kein gültiger API-Key:** HTTP 401, kein Text wird verarbeitet.
- **Fehler in der Pipeline:** HTTP 500; der Dienst gibt **niemals** den
  unverarbeiteten Text zurück. Der Aufrufer entscheidet, ob er die Anfrage
  daraufhin blockiert (empfohlen) — die Referenz-OpenWebUI-Einbindung tut das.

## Trace (inhaltsfrei)

`backend/tracing.py::record_trace` schreibt pro API-Anfrage **nur** Metadaten:
Quelle, Key-Präfix, Eingabelänge, Maskierungsanzahl, Anzahl je Entitätstyp,
Latenz, Erfolg und — falls `TRACE_HMAC_SECRET` gesetzt ist — einen
HMAC-SHA256 des Inputs zur Korrelation. **Nie** Text, **nie** `mapping`. Die
Admin-Testseite (`/admin/sanitize/api`) wird bewusst nicht getraced (Live-
Vorschau feuert bei jedem Tippen). Retention siehe
[`docs/data-mapping.md`](data-mapping.md).

## Konfiguration

- **API-Key:** im Admin-UI unter **API-Schlüssel** erzeugen (pro App,
  mehrere möglich, an-/ausschaltbar). Header: `Authorization: Bearer eg_…`
  oder `X-API-Key: eg_…`.
- **Erkennung:** Entitäten, Muster und Kontextwörter im Admin-UI pflegen;
  danach `POST /api/v1/reload` oder der Reload-Knopf im UI.
- **Modelle:** `/admin/modelle` schaltet Transformer-Modelle zu (sofortiger
  Analyzer-Neuaufbau).
