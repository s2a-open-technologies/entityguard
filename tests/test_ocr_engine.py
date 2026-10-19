"""
Unit tests for OCR engine selection/fallback.
Copyright (C) 2026  Christopher Abanilla
"""

from types import SimpleNamespace

from backend.components import ocr
from backend.ocr_settings import OcrSettings


def make_settings(engine="auto", device="auto"):
    return OcrSettings(
        enabled=True,
        engine=engine,
        device=device,
        lang="deu+eng",
        redaction="line",
        min_confidence=0.5,
        verify=False,
        max_bytes=1024 * 1024,
        max_pixels=1_000_000,
        timeout_seconds=10,
        tesseract_cmd=None,
        env_overrides=frozenset(),
        warnings=(),
    )


def test_auto_prefers_rapidocr_when_cuda_is_available(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: True)

    assert ocr._choose_engine(make_settings())[:2] == ("rapidocr", "cuda")


def test_auto_uses_tesseract_without_cuda(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    assert ocr._choose_engine(make_settings())[:2] == ("tesseract", "cpu")


def test_requested_rapidocr_gpu_falls_back_to_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    engine, device, warnings = ocr._choose_engine(make_settings("rapidocr", "cuda"))

    assert (engine, device) == ("tesseract", "cpu")
    assert any("CUDA" in warning for warning in warnings)


def test_requested_rapidocr_without_cuda_and_without_tesseract_stays_on_cpu(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: False)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    engine, device, warnings = ocr._choose_engine(make_settings("rapidocr", "cuda"))

    assert (engine, device) == ("rapidocr", "cpu")
    assert any("CUDA" in warning for warning in warnings)


def test_rapidocr_returns_word_level_tokens(monkeypatch):
    line_box = [[10, 10], [210, 10], [210, 40], [10, 40]]
    word_results = (
        (
            ("Patient:", 0.9, [[10, 10], [60, 10], [60, 40], [10, 40]]),
            ("Max", 0.9, [[70, 10], [100, 10], [100, 40], [70, 40]]),
            ("Mustermann", 0.9, [[110, 10], [210, 10], [210, 40], [110, 40]]),
        ),
    )
    def fake_engine(image, return_word_box=False):
        assert return_word_box is True
        return SimpleNamespace(
            boxes=[line_box],
            txts=("Patient: Max Mustermann",),
            scores=(0.95,),
            word_results=word_results,
        )

    monkeypatch.setattr(ocr, "_get_rapidocr_engine", lambda device, settings: fake_engine)

    result = ocr._run_rapidocr(object(), make_settings(), "cuda")

    tokens = result.lines[0].tokens
    assert [token.text for token in tokens] == ["Patient:", "Max", "Mustermann"]
    assert (tokens[1].start, tokens[1].end) == (9, 12)
    assert [token.box for token in tokens] == [
        (10, 10, 65, 40),
        (65, 10, 105, 40),
        (105, 10, 210, 40),
    ]


def test_rapidocr_word_boxes_cover_clipped_first_letters(monkeypatch):
    # RapidOCR's CTC-derived word boxes start a few pixels right of the ink.
    line_box = [[20, 15], [360, 15], [360, 60], [20, 60]]
    word_results = (
        (
            ("Patient:", 0.9, [[24, 19], [138, 19], [138, 56], [24, 56]]),
            ("Jürgen", 0.9, [[141, 19], [237, 19], [237, 56], [141, 56]]),
            ("Müller", 0.9, [[258, 19], [353, 19], [353, 56], [258, 56]]),
        ),
    )

    def fake_engine(image, return_word_box=False):
        return SimpleNamespace(
            boxes=[line_box],
            txts=("Patient: Jürgen Müller",),
            scores=(0.95,),
            word_results=word_results,
        )

    monkeypatch.setattr(ocr, "_get_rapidocr_engine", lambda device, settings: fake_engine)

    tokens = ocr._run_rapidocr(object(), make_settings(), "cpu").lines[0].tokens

    assert [token.box for token in tokens] == [
        (20, 15, 140, 60),
        (139, 15, 248, 60),
        (247, 15, 360, 60),
    ]


def test_rapidocr_gpu_failure_falls_back_to_cpu_without_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "_choose_engine", lambda settings: ("rapidocr", "cuda", []))
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: False)

    def fake_run_rapidocr(image, settings, device):
        if device == "cuda":
            raise RuntimeError("CUDA boom")
        return ocr.OcrResult(
            text="ok",
            lines=[],
            engine="rapidocr",
            device="cpu",
            confidence=1.0,
            duration_ms=1.0,
        )

    monkeypatch.setattr(ocr, "_run_rapidocr", fake_run_rapidocr)

    result = ocr.run_ocr(object(), make_settings("rapidocr", "cuda"))

    assert (result.engine, result.device) == ("rapidocr", "cpu")
    assert any("CPU" in warning for warning in result.warnings)


def test_rapidocr_cuda_uses_torch_backend_and_cpu_uses_onnxruntime(monkeypatch):
    import rapidocr

    created = []
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda params=None: created.append(params) or object())
    ocr.clear_ocr_cache()

    ocr._get_rapidocr_engine("cuda", make_settings())
    ocr._get_rapidocr_engine("cpu", make_settings())
    ocr.clear_ocr_cache()

    cuda_params, cpu_params = created
    assert cuda_params["EngineConfig.torch.use_cuda"] is True
    assert {cuda_params[f"{stage}.engine_type"] for stage in ("Det", "Cls", "Rec")} == {
        rapidocr.EngineType.TORCH
    }
    assert not any("engine_type" in key or "use_cuda" in key for key in cpu_params)
    assert cuda_params["Rec.lang_type"] == cpu_params["Rec.lang_type"] == "de"
