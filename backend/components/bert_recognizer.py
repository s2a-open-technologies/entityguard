"""
.
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

import logging
import os
from typing import Callable, Dict, List, Optional

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

logger = logging.getLogger("uvicorn.error")

# Registry of selectable transformer NER/PII models. The registry key is
# the `detector_models.name` row that toggles the model in the admin UI
# (seeded by alembic migration 013). Each entry maps the model's raw
# entity_group labels to EntityGuard entity types (see the `entities`
# table); labels without a mapping are dropped, i.e. never masked.
#
# `gpu_recommended` marks models that are only practical with a CUDA GPU -
# the admin UI shows a "GPU empfohlen" badge, and the numbers backing that
# call come from scripts/benchmark_all_models.py (run it after changing
# the registry to refresh README/admin descriptions).
#
# Labels can be extended at runtime: create the entity in the admin UI
# and add its label to the mapping here.
OPENMED_PII_GERMAN_MAPPING: Dict[str, str] = {
    "FIRSTNAME": "PERSON",
    "LASTNAME": "PERSON",
    "MIDDLENAME": "PERSON",
    "PREFIX": "PERSON",
    "STREET": "LOCATION",
    "BUILDINGNUMBER": "LOCATION",
    "SECONDARYADDRESS": "LOCATION",
    "CITY": "LOCATION",
    "STATE": "LOCATION",
    "COUNTY": "LOCATION",
    "ZIPCODE": "LOCATION",
    "GPSCOORDINATES": "LOCATION",
    "EMAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "IBAN": "IBAN_CODE",
    "BANKACCOUNT": "IBAN_CODE",
    "BIC": "IBAN_CODE",
    "DATEOFBIRTH": "DATE_TIME",
    "DATE": "DATE_TIME",
    "TIME": "DATE_TIME",
}

BERT_MODEL_REGISTRY: Dict[str, Dict[str, object]] = {
    # Classic NER model (GermEval 2014): strong on free-form names,
    # locations and especially organizations in German text.
    "transformer_ner_fhswf": {
        "model": "fhswf/bert_de_ner",
        "gpu_recommended": False,
        "mapping": {
            "PER": "PERSON",
            "LOC": "LOCATION",
            "ORG": "ORGANIZATION",
        },
    },
    # OpenMed PII models (AI4Privacy German subset): safety net over the DB
    # regex patterns for structured PII - names, addresses, dates, IBAN,
    # e-mail, phone - including format variants regex may miss. Same label
    # scheme across sizes; larger sizes trade CPU speed for accuracy.
    "transformer_pii_openmed_small": {
        "model": "OpenMed/OpenMed-PII-German-SuperClinical-Small-44M-v1",
        "gpu_recommended": False,
        "mapping": OPENMED_PII_GERMAN_MAPPING,
    },
    "transformer_pii_openmed_base": {
        "model": "OpenMed/OpenMed-PII-German-SuperClinical-Base-184M-v1",
        "gpu_recommended": True,
        "mapping": OPENMED_PII_GERMAN_MAPPING,
    },
    "transformer_pii_openmed_large": {
        "model": "OpenMed/OpenMed-PII-German-SuperClinical-Large-434M-v1",
        "gpu_recommended": True,
        "mapping": OPENMED_PII_GERMAN_MAPPING,
    },
}

# Default registry key used when no DB row is available (benchmark script
# path via BERT_NER_ENABLED env var) and no BERT_NER_MODEL override is set.
DEFAULT_REGISTRY_KEY = "transformer_ner_fhswf"

# Cached CUDA availability for the admin UI's live GPU status. Importing
# torch is expensive (~seconds), so this is resolved lazily on first call.
_gpu_available: Optional[bool] = None


def gpu_available() -> bool:
    """
    Report whether a CUDA GPU is available, caching the result.

    Importing torch and probing CUDA costs a few seconds on first use
    (and loads the CUDA libraries), so the result is memoized module-level.
    Failures (torch missing, no CUDA support) are treated as "no GPU".

    Returns:
        bool: True if torch can run on CUDA, False otherwise.
    """
    global _gpu_available
    if _gpu_available is None:
        try:
            import torch
            _gpu_available = bool(torch.cuda.is_available())
        except Exception:
            _gpu_available = False
    return _gpu_available


def resolve_registry_entry(model_name: Optional[str] = None) -> tuple[str, Dict[str, str]]:
    """
    Resolve a model name to its registry key and label mapping.

    Looks up `model_name` (or the BERT_NER_MODEL env var, or the registry
    default, in that order) inside BERT_MODEL_REGISTRY. This guarantees a
    model selected via env var still gets its correct label mapping
    instead of silently running with the default model's mapping.

    Args:
        model_name (Optional[str]): HuggingFace model name to resolve.
            Defaults to the BERT_NER_MODEL env var, then the registry
            default.

    Returns:
        tuple[str, Dict[str, str]]: (registry key, label mapping) of the
            matching entry.

    Raises:
        ValueError: If the resolved model name is not in the registry.
    """
    name = model_name or os.getenv("BERT_NER_MODEL", BERT_MODEL_REGISTRY[DEFAULT_REGISTRY_KEY]["model"])
    for key, entry in BERT_MODEL_REGISTRY.items():
        if entry["model"] == name:
            return key, dict(entry["mapping"])
    raise ValueError(
        f"Model '{name}' is not in BERT_MODEL_REGISTRY "
        f"(available: {[e['model'] for e in BERT_MODEL_REGISTRY.values()]})"
    )


class BertNerRecognizer(EntityRecognizer):
    """
    Presidio EntityRecognizer backed by a transformer NER/PII model (native
    PyTorch), run alongside the existing SpacyRecognizer and DB-driven
    PatternRecognizers rather than replacing them.

    Multiple instances (one per BERT_MODEL_REGISTRY entry) may be
    registered simultaneously; pass the registry key as `name` so the
    instances are distinguishable in the Presidio registry.

    The underlying model is loaded once and reused for the lifetime of the
    process; instantiate instances via the module-level cache in
    cstm_analyzer and register them with the AnalyzerEngine registry rather
    than creating one per request or per reload.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        model_name: Optional[str] = None,
        label_mapping: Optional[Dict[str, str]] = None,
        supported_language: str = "de",
        context: Optional[List[str]] = None,
        min_score: Optional[float] = None,
    ):
        self.model_name = model_name or os.getenv(
            "BERT_NER_MODEL",
            BERT_MODEL_REGISTRY[DEFAULT_REGISTRY_KEY]["model"],
        )
        self.label_mapping = label_mapping or resolve_registry_entry(self.model_name)[1]
        # Per-recognizer confidence floor (separate from Presidio's global
        # default_score_threshold). Applied in analyze() before results are
        # returned, so it happens *before* Presidio's context-word score
        # boosting - a borderline result can't be "rescued" by a nearby
        # context word. Acceptable trade-off: BERT's raw scores are almost
        # always either very high (>0.99) or clearly low, not borderline.
        self.min_score = min_score
        # EntityRecognizer.__init__() calls self.load() itself, so this must
        # be set before calling super().__init__().
        self.pipeline: Optional[Callable] = None

        super().__init__(
            supported_entities=list(set(self.label_mapping.values())),
            name=name or "BertNerRecognizer",
            supported_language=supported_language,
            context=context,
        )

    def load(self) -> None:
        """Load the tokenizer + model and build the NER pipeline."""
        if self.pipeline is not None:
            return

        import torch
        from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

        device_env = os.getenv("BERT_NER_DEVICE")
        if device_env is not None:
            # Accepted values follow transformers' pipeline convention,
            # e.g. "cpu", "cuda", "cuda:0". Integers other than 0 are not
            # accepted by transformers >= 4.5x ("Invalid device string").
            device = device_env
        else:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"Loading BERT NER model '{self.model_name}' (device={device})...")
        model = AutoModelForTokenClassification.from_pretrained(self.model_name)
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        self.pipeline = pipeline(
            "token-classification",
            model=model,
            tokenizer=tokenizer,
            # "simple" could split a word mid-token when the model wavers
            # between sub-tokens (e.g. "Max Mustermann" -> "Max Must" +
            # "mann", or "Klaus Weber" -> "Klaus Web"), silently leaving
            # PII fragments unmasked. "first" decides one label per whole
            # word instead, which never drops part of a match - tested
            # against "average"/"max", which fix the split but sometimes
            # drop an entire word (e.g. "Weber") instead, a worse failure
            # mode for a sanitizer than an occasional trailing punctuation
            # character included in the span.
            aggregation_strategy="first",
            device=device,
        )
        logger.info(f"BERT NER model '{self.model_name}' loaded")

    def analyze(
        self, text: str, entities: List[str], nlp_artifacts: Optional[NlpArtifacts] = None
    ) -> List[RecognizerResult]:
        """
        Run the transformer NER pipeline on the raw text and map its
        predictions to Presidio RecognizerResults, filtered to the
        requested entities and (if set) `self.min_score`.
        """
        if not text.strip() or self.pipeline is None:
            return []

        results: List[RecognizerResult] = []
        for pred in self.pipeline(text):
            entity_type = self.label_mapping.get(pred["entity_group"])
            if entity_type is None:
                continue
            if entities and entity_type not in entities:
                continue
            if self.min_score is not None and pred["score"] < self.min_score:
                continue

            # Trim whitespace from the span: token offsets often include
            # leading spaces (e.g. "Patient Hans" -> start at the space
            # before "Hans"), and masking those would glue the surrounding
            # words together in the output ("Patient[NAME_1]" instead of
            # "Patient [NAME_1]"). Must be computed from the actual text
            # slice - pred["word"] is already whitespace-trimmed and would
            # miss the offset shift.
            span = text[pred["start"]:pred["end"]]
            start = pred["start"] + (len(span) - len(span.lstrip()))
            end = pred["end"] - (len(span) - len(span.rstrip()))
            if start >= end:
                continue

            results.append(
                RecognizerResult(
                    entity_type=entity_type,
                    start=start,
                    end=end,
                    score=float(pred["score"]),
                )
            )

        return results
