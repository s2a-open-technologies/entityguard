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
from dataclasses import dataclass, field, replace
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
    """Return whether torch can use a CUDA GPU (RapidOCR's GPU backend)."""
    try:
        import torch
        return torch.cuda.is_available()
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

    from rapidocr import EngineType, RapidOCR

    # Keep more detail than RapidOCR's 2000px default and retain faint lines
    # instead of dropping them below text_score 0.5. Low-confidence lines are
    # still conservatively redacted via min_confidence.
    params: dict[str, object] = {
        "Global.max_side_len": 3200,
        "Global.text_score": 0.3,
    }
    if device == "cuda":
        # GPU runs on torch, not onnxruntime-gpu: ONNX Runtime keeps its
        # CUDA/cuDNN state per thread and re-runs the exhaustive conv algo
        # search for every new timeout worker thread (~10x slower than CPU).
        # torch is already installed with CUDA for the transformer models.
        for stage in ("Det", "Cls", "Rec"):
            params[f"{stage}.engine_type"] = EngineType.TORCH
        params["EngineConfig.torch.use_cuda"] = True
    if "deu" in settings.lang or "ger" in settings.lang:
        params["Rec.lang_type"] = "de"
    elif "eng" in settings.lang:
        params["Rec.lang_type"] = "en"
    else:
        params["Rec.lang_type"] = "la"
    engine = RapidOCR(params=params or None)
    _engine_cache[key] = engine
    return engine


def _fit_word_boxes(
    tokens: list[OcrToken],
    line_box: tuple[int, int, int, int],
) -> list[OcrToken]:
    """Stretch RapidOCR word boxes so they tile the detected line box.

    RapidOCR derives word boxes from CTC character positions, which are
    typically shifted by a few pixels and clip the first letter of a word.
    The line box from text detection is reliable, so each word is extended to
    the middle of the gap to its neighbours (first/last word to the line
    edges) and to the full line height. This can only add whitespace to a
    redaction, never leave ink of the word uncovered.
    """
    ordered = sorted(tokens, key=lambda token: token.box[0])
    fitted: list[OcrToken] = []
    for index, token in enumerate(ordered):
        if index == 0:
            left = line_box[0]
        else:
            left = (ordered[index - 1].box[2] + token.box[0]) // 2
        if index == len(ordered) - 1:
            right = line_box[2]
        else:
            right = (token.box[2] + ordered[index + 1].box[0] + 1) // 2
        fitted.append(replace(
            token,
            box=(
                min(left, token.box[0]),
                min(line_box[1], token.box[1]),
                max(right, token.box[2]),
                max(line_box[3], token.box[3]),
            ),
        ))
    by_start = {token.start: token for token in fitted}
    return [by_start[token.start] for token in tokens]


def _run_rapidocr(image, settings: OcrSettings, device: str) -> OcrResult:
    import numpy as np

    started = time.perf_counter()
    engine = _get_rapidocr_engine(device, settings)
    with _rapidocr_lock:
        result = engine(image, return_word_box=True)
    duration_ms = (time.perf_counter() - started) * 1000

    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()
    word_results = getattr(result, "word_results", None) or ()

    def box_from_points(points) -> tuple[int, int, int, int]:
        array = np.asarray(points)
        return (
            int(array[:, 0].min()),
            int(array[:, 1].min()),
            int(array[:, 0].max()),
            int(array[:, 1].max()),
        )

    raw_lines: list[tuple[tuple[int, int, int, int], str, float, object]] = []
    for index, (box, text, score) in enumerate(zip(boxes if boxes is not None else [], texts, scores)):
        normalized = text.strip()
        if not normalized:
            continue
        word_line = word_results[index] if index < len(word_results) else ()
        raw_lines.append((box_from_points(box), normalized, float(score), word_line))

    raw_lines.sort(key=lambda item: (item[0][1], item[0][0]))

    lines: list[OcrLine] = []
    cursor = 0
    for line_id, (box, text, score, word_line) in enumerate(raw_lines):
        line_start = cursor
        tokens: list[OcrToken] = []
        search_from = 0
        for word_text, word_score, word_box in word_line or ():
            normalized_word = (word_text or "").strip()
            if not normalized_word or not word_box:
                continue
            relative_start = text.find(normalized_word, search_from)
            if relative_start < 0:
                continue
            token_start = line_start + relative_start
            try:
                confidence = float(word_score)
            except (TypeError, ValueError):
                confidence = score
            tokens.append(OcrToken(
                text=normalized_word,
                start=token_start,
                end=token_start + len(normalized_word),
                box=box_from_points(word_box),
                confidence=confidence,
                line_id=line_id,
            ))
            search_from = relative_start + len(normalized_word)

        if tokens:
            tokens = _fit_word_boxes(tokens, box)
        else:
            tokens.append(OcrToken(
                text=text,
                start=line_start,
                end=line_start + len(text),
                box=box,
                confidence=score,
                line_id=line_id,
            ))

        lines.append(OcrLine(
            line_id=line_id,
            text=text,
            start=line_start,
            end=line_start + len(text),
            box=box,
            confidence=score,
            tokens=tokens,
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
        if device == "cuda":
            logger.warning("RapidOCR GPU failed (%s); falling back to RapidOCR CPU", exc)
            try:
                fallback = _run_with_timeout(
                    lambda: _run_rapidocr(image, settings, "cpu"), settings.timeout_seconds
                )
            except OcrError:
                raise
            except Exception as fallback_exc:
                raise OcrError(f"RapidOCR fehlgeschlagen: {fallback_exc}") from fallback_exc
            fallback.warnings.extend(warnings)
            fallback.warnings.append(f"RapidOCR-GPU fehlgeschlagen ({exc}); RapidOCR läuft auf CPU.")
            return fallback
        raise OcrError(f"RapidOCR fehlgeschlagen: {exc}") from exc
