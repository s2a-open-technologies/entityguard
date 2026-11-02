# Konzept: Audio-Maskierung für Cloud-Transkription

> **Status: Konzept, nicht implementiert.** Dieses Dokument hält eine Idee fest,
> die vor einer Umsetzung erst praktisch getestet werden soll (siehe
> [Testplan](#testplan-vor-der-umsetzung)).

## Problem

Text und Bilder lassen sich mit EntityGuard bereits lokal maskieren, bevor sie
an einen LLM-Provider gehen. Audio (z. B. Diktate in openDox) ist die letzte
Lücke:

- Die Transkription läuft heute **lokal**, damit kein Rohaudio das Haus verlässt.
  Der transkribierte Text geht anschließend maskiert ans LLM.
- Lokale Modelle wie `whisper-small` verstehen Fachbegriffe zu oft falsch. Ein
  falsches Transkript lässt sich auch durch ein gutes LLM nicht mehr retten.
- Cloud-STT-Provider transkribieren deutlich besser, bekommen dann aber das
  Rohaudio mit allen Namen, Daten und der Stimme.
- Piepton oder Stille über den PII-Stellen hilft nicht: Der Satzkontext geht
  verloren, und die Transkription des Providers wird schlechter.

## Idee: Platzhalter ins Audio einsprechen

Die PII-Stellen im Audio werden nicht stummgeschaltet, sondern durch einen
**gesprochenen Platzhalter** ersetzt. Der Rest des Audios bleibt im Original,
damit das Cloud-STT Satzbau und Fachbegriffe in voller Qualität hört.

```
Original:     "Patient Hans Müller, geboren 3.4.1961, klagt über Dyspnoe …"
An Cloud-STT: "Patient Platzhalter Person eins, geboren Platzhalter Datum eins,
               klagt über Dyspnoe …"
               (Platzhalter lokal per TTS gesprochen)
Zurück:       "Patient Platzhalter Person eins, …"  →  "Patient [PERSON_1], …"
```

Das lokale ASR muss dafür **nur die PII zeitlich finden**, nicht alles korrekt
transkribieren. Ob „Dyspnoe“ lokal als „Dispnö“ erkannt wird, ist egal, denn
dieses Stück Audio geht unverändert an den Provider.

## Ablauf mit zweiter Sicherheitsschicht

```
openDox ──Audio-Chunk + bisheriges Mapping──▶ EntityGuard /api/v1/sanitize/audio
           lokal: ASR mit Wort-Zeitstempeln (nur zur PII-Lokalisierung)
                  → CustomAnalyzer (Muster, spaCy, Transformer)
                  → PII-Zeitbereiche durch TTS-Platzhalter ersetzen
        ◀── maskiertes Audio + Mapping + gesprochene Platzhalter

openDox ──maskiertes Audio (zusammengesetzt)──▶ Cloud-STT
        ◀── Text mit „Platzhalter Person eins“

openDox ──Text + Mapping──▶ EntityGuard /api/v1/sanitize      (2. Schicht)
           gesprochene Platzhalter → [PERSON_1]
           vorhandene Platzhalter schützen, neue Funde weiterzählen
        ◀── maskierter Text + zusammengeführtes Mapping

openDox ──maskierter Text──▶ LLM ──Antwort mit [PERSON_1]──▶ openDox demaskiert
```

Die zweite Runde ist die zusätzliche Sicherheitsschicht: Was das lokale ASR
verhört oder der Analyzer im Audio übersehen hat, kann im (besseren)
Transkript des Cloud-STT noch gefunden werden, **bevor** es ans LLM geht.

EntityGuard bleibt dabei zustandslos: Das Mapping liegt wie bisher beim
Aufrufer (openDox).

## Fehlender Baustein im Text-Endpoint: `existing_mapping`

`/api/v1/sanitize` kennt heute keine bereits vergebenen Platzhalter. In der
zweiten Runde würde ein neu gefundener Name erneut `[PERSON_1]` heißen und mit
dem `[PERSON_1]` aus dem Audio kollidieren. Nötig ist ein optionales Feld
`existing_mapping`:

- **Gesprochene Platzhalter zurückführen:** „Platzhalter Person eins“,
  „Person 1“, „person eins“ usw. tolerant auf `[PERSON_1]` abbilden (nur
  Platzhalter, die in `existing_mapping` stehen).
- **Vorhandene Platzhalter schützen:** Treffer, die einen `[X_n]`-Token
  überlappen, verwerfen.
- **Weiterzählen:** Zähler pro Platzhalter ab dem höchsten vorhandenen Index
  fortsetzen.
- **Wiederverwenden:** Mit `reuse_placeholders` bekommt derselbe Originalwert
  denselben vorhandenen Platzhalter.
- **Antwort:** Das zusammengeführte Mapping.

Der Baustein ist reine Logik (`backend/components/placeholders.py`), gut
testbar und auch ohne Audio für mehrstufige Pipelines nützlich.

## Chunks

openDox lädt Diktate bereits in Chunks hoch. Diese können einzeln an
EntityGuard gehen; openDox setzt das maskierte Audio am Ende zusammen.

- Jeder Chunk wird mit dem **bisher gesammelten Mapping** geschickt. Ohne das
  würden zwei Personen in verschiedenen Chunks beide `[PERSON_1]` heißen.
- Die Verarbeitung läuft parallel zum Diktat. Wenn die sprechende Person
  aufhört, ist nur noch der letzte Chunk offen.
- **Chunk-Grenzen:** Wird mitten in einem Namen geschnitten, erkennt keiner der
  beiden Chunks ihn. Deshalb in Sprechpausen schneiden oder mit Überlappung
  (`overlap_ms`) arbeiten.

## Last & Hardware

| Schritt                       | Aufwand                                   | Engpass? |
|-------------------------------|-------------------------------------------|----------|
| Text-Maskierung (2. Runde)    | ms bis wenige 100 ms                      | nein     |
| TTS-Platzhalter (z. B. Piper) | kurze Clips, CPU, cachebar                | nein     |
| Audio schneiden/einsetzen     | trivial                                   | nein     |
| **Lokales ASR**               | GPU: Bruchteil der Audiodauer; CPU: etwa Echtzeit oder langsamer | **ja** |

Gegenmaßnahmen:

- **Optionales Feature**, Standard aus. ASR-Modelle werden nur geladen, wenn
  Audio aktiviert ist.
- **Hardware-Profile:** GPU → z. B. `large-v3-turbo` (`int8_float16`);
  nur CPU → `small`/`medium` mit deutlichem Warnhinweis im Admin-UI.
- **Rückstau statt Kollaps:** Begrenzte Parallelität pro GPU (Semaphore). Ist
  sie belegt, antwortet EntityGuard mit `503` + `Retry-After`; `/health` und die
  Text-Maskierung bleiben schnell.
- **Später auslagerbar:** ASR hinter einer schmalen Schnittstelle halten, damit
  es bei Bedarf in einen eigenen Worker-Container wandern kann. Die API ist
  zustandslos und lässt sich horizontal skalieren.

**Abwägung:** Wer ohnehin eine GPU für EntityGuard anschafft, könnte auch gleich
ein großes Whisper-Modell lokal betreiben und ganz auf das Cloud-STT verzichten.
Der Unterschied: Für die PII-Lokalisierung reicht eine kleine GPU, für eine
hochwertige Volltranskription mit Fachbegriffen eher nicht. Das Audio-Feature
lohnt sich also nur, wenn das Cloud-STT spürbar besser ist als das, was lokal
machbar ist. Das soll der Testplan klären.

## Stimme

Auch mit maskierten Inhalten bleibt **die Stimme erhalten**. Sie ist ein
personenbezogenes Datum und kann je nach Nutzung als biometrisches Merkmal
(Art. 9 DSGVO) gelten. Das muss im Betrieb klar benannt werden.

Spätere Option: **Voice Conversion** (z. B. kNN-VC) vor dem Einsetzen der
Platzhalter. Sie ändert nur die Klangfarbe, braucht kein Transkript und lässt
Aussprache und Fachbegriffe erhalten. Die Platzhalter werden dann in derselben
Zielstimme gesprochen, damit keine hörbaren Brüche entstehen. Ob das Cloud-STT
darunter leidet, muss gemessen werden.

## Grenzen & Risiken

- **Was das lokale ASR verhört, geht im Klartext raus.** Ein falsch erkannter
  Name wird vom Analyzer nicht gefunden und bleibt im Audio. Die zweite Runde
  fängt ihn nur ab, wenn das Cloud-STT ihn korrekt schreibt **und** der
  Analyzer ihn dann erkennt; der Provider hat ihn zu diesem Zeitpunkt aber
  bereits gehört. Hilfreich: Zeitpuffer (z. B. ±150 ms) um Treffer, Hotwords
  bzw. `initial_prompt` mit bekannten Namen (z. B. aus dem Patientenstamm).
- **Platzhalter-Rücktranskription** muss tolerant sein (Zahlwort vs. Ziffer,
  Groß-/Kleinschreibung, Satzzeichen). Ein Platzhalter, den das Cloud-STT
  stark verändert, wird nicht zurückgeführt.
- **Schnittstellen im Audio** (eingesetzte TTS-Clips) können die
  Transkription der umgebenden Wörter verschlechtern.
- **Latenz** steigt um die lokale ASR-Zeit pro Chunk.

## Testplan vor der Umsetzung

Mit 5–10 realistischen deutschen Diktaten (Namen, Geburtsdaten, Adressen,
Fallnummern, Fachbegriffe) messen:

1. **PII-Lokalisierung:** Wie viele PII-Stellen findet lokales ASR +
   Analyzer zeitlich korrekt, pro Modell (`small`, `medium`,
   `large-v3-turbo`)?
2. **Platzhalter-Rücktranskription:** Gibt das Cloud-STT eingesprochene
   Platzhalter („Platzhalter Person eins“) wörtlich bzw. eindeutig
   zurückführbar zurück?
3. **Qualität:** Wie stark verschlechtern die Schnittstellen (und optional
   die Voice Conversion) die Transkription des Cloud-STT gegenüber dem
   Original?
4. **Zweite Schicht:** Wie viele verpasste PII-Stellen findet die
   Text-Maskierung im Cloud-Transkript noch?
5. **Echtzeitfaktor** pro Modell auf CPU und kleiner GPU, bei Chunklängen von
   10/20/30 s.

Für erste Versuche reicht ein Skript außerhalb des Endpoints, das ein Audio
einliest, die Platzhalter einsetzt und eine WAV-Datei für den manuellen Test
beim Cloud-STT schreibt.

## Mögliche Umsetzung (Skizze)

Aufbau analog zur Bild-Pipeline (`backend/components/ocr.py`,
`backend/components/image_sanitizer.py`): OCR ↔ ASR, Box ↔ Zeitbereich,
schwarzer Balken ↔ gesprochener Platzhalter.

- `backend/components/asr.py`: `AsrWord(text, start, end)`, `AsrResult`,
  Engine-Cache, `run_asr()` mit faster-whisper, Timeout und Fehlerklassen wie
  in `ocr.py`, GPU-Auswahl wie `_choose_engine`.
- `backend/components/tts.py`: lokale deutsche TTS (z. B. Piper), Cache pro
  Platzhaltertext.
- `backend/components/audio_sanitizer.py`: Decoding (ffmpeg, Mono 16 kHz),
  Größen-/Dauerlimit, Transkript mit Char-Offsets → Analyzer →
  `apply_matches` → Zeitbereiche → Splicing mit Crossfade → WAV/Base64.
  Fail-closed: bei Fehler nie Originalaudio zurückgeben.
- `POST /api/v1/sanitize/audio` (API-Key, Tracing mit Audiodauer statt
  Textlänge), Admin-Proxy und Audio-Modus in `/admin/sanitize`.
- `existing_mapping` in `/api/v1/sanitize` (siehe oben).
- Settings in `app_settings` (neue Migration) plus `ENTITYGUARD_AUDIO_*` /
  `ENTITYGUARD_ASR_*` Env-Overrides; Docker-Image mit ffmpeg und vorgeladenen
  Modellen in `/app/data/hf`.
- Tests mit Fake-ASR/Fake-TTS; Benchmark-Skript für den Echtzeitfaktor.
