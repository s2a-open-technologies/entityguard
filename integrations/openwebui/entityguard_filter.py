"""
title: EntityGuard Filter (Text + Bilder)
author: Christopher Abanilla
version: 0.3

OpenWebUI-Filter fuer EntityGuard: maskiert den GANZEN Kontext (System-Prompt,
Verlauf, neue Frage) in einem Aufruf und behandelt zusaetzlich Bilder.

- Text: alle Textteile werden mit Trennmarken zu einem Aufruf verbunden, damit
  EntityGuard im ganzen Gespraech eindeutige Platzhalter vergibt.
- Bilder: `image_mode="block"` bricht die Anfrage fail-closed ab.
  `image_mode="redact"` schickt das Bild an `/api/v1/sanitize/image`, ersetzt
  es durch das redigierte PNG und laesst OCR-Fehler die Anfrage stoppen.
- Antwort: `outlet()` setzt Platzhalter anhand des gemeinsamen `mapping`
  zurueck. Das LLM sieht die Originalwerte nie.

Ohne erreichbaren Dienst, ohne gueltigen API-Key oder bei einem Fehler wird
die Anfrage gestoppt (Fail-Closed).
"""

import logging
import re
from typing import Optional

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MARKER = "=====#{}====="
_MARKER_RE = re.compile(r"=====#(\d+)=====")
TEXT_KEYS = ("sanitized_text", "filtered", "result", "text")


def _slots(messages: list) -> list:
    """Alle Textstellen der Nachrichten als (Nachricht, Teil-Index oder None)."""
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


def _sanitize_images(
    messages: list,
    api_url: str,
    api_key: str,
    timeout: float,
    mode: str,
) -> None:
    """Ersetzt Bildteile durch das redigierte PNG oder blockiert die Anfrage."""
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
            raise ValueError(
                "externe Bild-URLs werden aus Sicherheitsgruenden nicht unterstuetzt"
            )
        try:
            header, data = url.split(",", 1)
        except ValueError as exc:
            raise ValueError("ungueltige Bild-Data-URI") from exc
        mime = header[5:].split(";", 1)[0] if header.startswith("data:") else ""
        payload = {
            "image_base64": data,
            "mime_type": mime,
            "reuse_placeholders": True,
        }
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
    """Maskiert alle Text- und Bildstellen in einem Aufruf.

    Returns:
        Mapping Platzhalter -> Original.
    Raises:
        Exception: bei jedem Fehler (fail-closed); die Anfrage darf dann nicht
            weitergehen.
    """
    mapping = {}
    slots = _slots(messages)
    if slots:
        joined = _join([_get(s) for s in slots])
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        wait = min(60.0, timeout + len(joined) / 2000)
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
        image_api_url = (
            api_url[: -len("/sanitize")] + "/sanitize/image"
            if api_url.endswith("/sanitize")
            else api_url
        )
    _sanitize_images(messages, image_api_url, api_key, image_timeout, image_mode)
    return mapping


def restore(text: str, mapping: dict) -> str:
    """Platzhalter zuruecksetzen, laengste zuerst ([NAME_10] vor [NAME_1])."""
    for placeholder in sorted(mapping, key=len, reverse=True):
        text = text.replace(placeholder, mapping[placeholder])
    return text


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(
            default="http://localhost:9500/api/v1/sanitize",
            description="Sanitizer-Endpunkt",
        )
        image_api_url: str = Field(
            default="http://localhost:9500/api/v1/sanitize/image",
            description="Bild-Redaktions-Endpunkt",
        )
        api_key: str = Field(
            default="",
            description="API-Key des Dienstes (EntityGuard: unter API-Schluessel erzeugen)",
        )
        timeout: int = Field(
            default=5,
            description="Grundlimit in Sekunden (waechst mit der Textlaenge)",
        )
        image_mode: str = Field(
            default="block",
            description="block = Bilder ablehnen, redact = Bilder schwaerzen",
        )
        image_timeout: int = Field(
            default=30,
            description="Zeitlimit fuer die Bild-OCR in Sekunden",
        )
        restore_mapping: bool = Field(
            default=True,
            description="Platzhalter in der Antwort zurueckuebersetzen",
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(
        self,
        body: dict,
        __metadata__: dict = None,
        __user__: Optional[dict] = None,
    ) -> dict:
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
            raise Exception(f"Privacy stop: Security check failed: {e}") from e
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
