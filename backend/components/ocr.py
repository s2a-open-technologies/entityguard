"""
OCR engine abstraction for image text extraction.
Copyright (C) 2026  Christopher Abanilla

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import importlib.util
import logging
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Optional

from backend.ocr_settings import OcrSettings

logger = logging.getLogger("uvicorn.error")


class OcrError(RuntimeError):
    """Base error for image text extraction."""


class OcrUnavailableError(OcrError):
    """No configured OCR engine is installed/available."""


class OcrTimeoutError(OcrError):
    """OCR exceeded the configured time limit."""


@dataclass(frozen=True)
class OcrToken:
    """One recognized text unit (word for Tesseract, line for RapidOCR)."""

    text: str
    start: int
    end: int
    box: tuple[int, int, int, int]
    confidence: float
    line_id: int


@dataclass
class OcrLine:
    """A recognized text line with its bounding box and tokens."""

    line_id: int
    text: str
    start: int
    end: int
    box: tuple[int, int, int, int]
    confidence: float
    tokens: list[OcrToken] = field(default_factory=list)


@dataclass
class OcrResult:
    """Normalized OCR output independent of the underlying engine."""

    text: str
    lines: list[OcrLine]
    engine: str
    device: str
    confidence: float
    duration_ms: float
    warnings: list[str] = field(default_factory=list)


_engine_cache: dict[tuple[str, str, str], object] = {}
_rapidocr_lock = threading.Lock()


def clear_ocr_cache() -> None:
    """Drop cached OCR engines (call after changing engine/device settings)."""
    _engine_cache.clear()


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def tesseract_available(settings: OcrSettings) -> bool:
    """Return whether pytesseract and the tesseract binary are usable."""
    cmd = settings.tesseract_cmd or "tesseract"
    return _module_available("pytesseract") and shutil.which(cmd) is not None


def _cuda_available() -> bool:
    """Return whether ONNX Runtime exposes a CUDA execution provider."""
    try:
        import onnxruntime
        return "CUDAExecutionProvider" in onnxruntime.get_available_providers()
    except Exception:
        return False


def rapidocr_available() -> bool:
    """Return whether the RapidOCR Python package can be imported."""
    return _module_available("rapidocr")


def available_engines(settings: Optional[OcrSettings] = None) -> dict[str, str]:
    """Describe engine/device availability for the admin UI."""
    return {
        "tesseract": "verfügbar" if settings and tesseract_available(settings) else "nicht verfügbar",
        "rapidocr_cpu": "verfügbar" if rapidocr_available() else "nicht verfügbar",
        "rapidocr_cuda": "verfügbar (CUDA)" if rapidocr_available() and _cuda_available() else "nicht verfügbar",
    }


def _choose_engine(settings: OcrSettings) -> tuple[str, str, list[str]]:
    """Pick engine/device; fall back to Tesseract when GPU RapidOCR is unavailable."""
    warnings: list[str] = []
    tesseract_ok = tesseract_available(settings)
    rapidocr_ok = rapidocr_available()
    cuda_ok = rapidocr_ok and _cuda_available()

    if settings.engine == "tesseract":
        if tesseract_ok:
            return "tesseract", "cpu", warnings
        raise OcrUnavailableError("Tesseract ist nicht installiert oder nicht erreichbar")

    if settings.engine == "rapidocr":
        if not rapidocr_ok:
            if tesseract_ok:
                warnings.append("RapidOCR ist nicht installiert; Tesseract wird verwendet.")
                return "tesseract", "cpu", warnings
            raise OcrUnavailableError("RapidOCR ist nicht installiert und Tesseract ist nicht verfügbar")
        device = settings.device
        if device == "auto":
            device = "cuda" if cuda_ok else "cpu"
        if device == "cuda" and not cuda_ok:
            if tesseract_ok:
                warnings.append("RapidOCR-GPU angefordert, aber CUDA ist nicht verfügbar; Tesseract wird verwendet.")
                return "tesseract", "cpu", warnings
            warnings.append("RapidOCR-GPU angefordert, aber CUDA ist nicht verfügbar; RapidOCR läuft auf CPU.")
            device = "cpu"
        return "rapidocr", device, warnings

    if cuda_ok:
        return "rapidocr", "cuda", warnings
    if tesseract_ok:
        return "tesseract", "cpu", warnings
    if rapidocr_ok:
        warnings.append("Keine CUDA-GPU und kein Tesseract; RapidOCR läuft auf CPU.")
        return "rapidocr", "cpu", warnings
    raise OcrUnavailableError("Weder Tesseract noch RapidOCR sind verfügbar")


def _run_with_timeout(func, timeout_seconds: int):
    if timeout_seconds <= 0:
        return func()
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        raise OcrTimeoutError(f"OCR hat das Zeitlimit von {timeout_seconds}s überschritten") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _union_boxes(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _build_result(
    lines: list[OcrLine],
    engine: str,
    device: str,
    duration_ms: float,
    warnings: list[str],
) -> OcrResult:
    text = "\n".join(line.text for line in lines)
    scores = [token.confidence for line in lines for token in line.tokens if token.confidence >= 0]
    confidence = sum(scores) / len(scores) if scores else 0.0
    return OcrResult(
        text=text,
        lines=lines,
        engine=engine,
        device=device,
        confidence=confidence,
        duration_ms=duration_ms,
        warnings=warnings,
    )


def _run_tesseract(image, settings: OcrSettings) -> OcrResult:
    import pytesseract
    from pytesseract import Output

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    started = time.perf_counter()
    data = pytesseract.image_to_data(
        image,
        lang=settings.lang,
        config="--oem 1 --psm 3",
        output_type=Output.DICT,
    )
    duration_ms = (time.perf_counter() - started) * 1000

    grouped: dict[tuple[int, int, int], list[dict]] = {}
    order: list[tuple[int, int, int]] = []
    count = len(data.get("text", []))
    for i in range(count):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        try:
            confidence = float(data["conf"][i])
        except (TypeError, ValueError):
            confidence = -1.0
        key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append({
            "text": word,
            "conf": max(0.0, confidence) / 100.0,
            "box": (
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["left"][i]) + int(data["width"][i]),
                int(data["top"][i]) + int(data["height"][i]),
            ),
        })

    lines: list[OcrLine] = []
    cursor = 0
    for line_id, key in enumerate(order):
        words = grouped[key]
        line_text = " ".join(word["text"] for word in words)
        line_start = cursor
        tokens: list[OcrToken] = []
        offset = line_start
        for word in words:
            tokens.append(OcrToken(
                text=word["text"],
                start=offset,
                end=offset + len(word["text"]),
                box=word["box"],
                confidence=word["conf"],
                line_id=line_id,
            ))
            offset += len(word["text"]) + 1
        line_conf = sum(token.confidence for token in tokens) / len(tokens) if tokens else 0.0
        lines.append(OcrLine(
            line_id=line_id,
            text=line_text,
            start=line_start,
            end=line_start + len(line_text),
            box=_union_boxes([token.box for token in tokens]),
            confidence=line_conf,
            tokens=tokens,
        ))
        cursor = line_start + len(line_text) + 1

    return _build_result(lines, "tesseract", "cpu", duration_ms, [])


def _get_rapidocr_engine(device: str, settings: OcrSettings):
    key = ("rapidocr", device, settings.lang)
    if key in _engine_cache:
        return _engine_cache[key]

    from rapidocr import RapidOCR

    params: dict[str, object] = {}
    if device == "cuda":
        params["EngineConfig.onnxruntime.use_cuda"] = True
    if "deu" in settings.lang or "ger" in settings.lang:
        params["Rec.lang_type"] = "de"
    elif "eng" in settings.lang:
        params["Rec.lang_type"] = "en"
    else:
        params["Rec.lang_type"] = "la"
    engine = RapidOCR(params=params or None)
    _engine_cache[key] = engine
    return engine


def _run_rapidocr(image, settings: OcrSettings, device: str) -> OcrResult:
    import numpy as np

    started = time.perf_counter()
    engine = _get_rapidocr_engine(device, settings)
    with _rapidocr_lock:
        result = engine(image, return_word_box=False)
    duration_ms = (time.perf_counter() - started) * 1000

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()

    raw_lines: list[tuple[tuple[int, int, int, int], str, float]] = []
    for box, text, score in zip(boxes if boxes is not None else [], texts, scores):
        points = np.asarray(box)
        x0, y0 = points[:, 0].min(), points[:, 1].min()
        x1, y1 = points[:, 0].max(), points[:, 1].max()
        normalized = text.strip()
        if normalized:
            raw_lines.append(((int(x0), int(y0), int(x1), int(y1)), normalized, float(score)))

    raw_lines.sort(key=lambda item: (item[0][1], item[0][0]))

    lines: list[OcrLine] = []
    cursor = 0
    for line_id, (box, text, score) in enumerate(raw_lines):
        line_start = cursor
        token = OcrToken(
            text=text,
            start=line_start,
            end=line_start + len(text),
            box=box,
            confidence=score,
            line_id=line_id,
        )
        lines.append(OcrLine(
            line_id=line_id,
            text=text,
            start=line_start,
            end=line_start + len(text),
            box=box,
            confidence=score,
            tokens=[token],
        ))
        cursor = line_start + len(text) + 1

    return _build_result(lines, "rapidocr", device, duration_ms, [])


def run_ocr(image, settings: OcrSettings) -> OcrResult:
    """Run OCR on a PIL image using the configured/auto-selected engine."""
    engine, device, warnings = _choose_engine(settings)

    if engine == "tesseract":
        try:
            result = _run_with_timeout(lambda: _run_tesseract(image, settings), settings.timeout_seconds)
        except OcrError:
            raise
        except Exception as exc:
            raise OcrError(f"Tesseract fehlgeschlagen: {exc}") from exc
        result.warnings.extend(warnings)
        return result

    try:
        result = _run_with_timeout(
            lambda: _run_rapidocr(image, settings, device), settings.timeout_seconds
        )
        result.warnings.extend(warnings)
        return result
    except OcrError:
        raise
    except Exception as exc:
        if device == "cuda" and tesseract_available(settings):
            logger.warning("RapidOCR GPU failed (%s); falling back to Tesseract", exc)
            try:
                fallback = _run_with_timeout(
                    lambda: _run_tesseract(image, settings), settings.timeout_seconds
                )
            except OcrError:
                raise
            except Exception as fallback_exc:
                raise OcrError(f"Tesseract fehlgeschlagen: {fallback_exc}") from fallback_exc
            fallback.warnings.extend(warnings)
            fallback.warnings.append(f"RapidOCR-GPU fehlgeschlagen ({exc}); Tesseract eingesetzt.")
            return fallback
        raise OcrError(f"RapidOCR fehlgeschlagen: {exc}") from exc
