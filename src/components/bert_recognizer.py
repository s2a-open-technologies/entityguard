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

# Model + behavior are env-configurable so they can be swapped/disabled
# without a code change (see README/.env for defaults).
DEFAULT_MODEL_NAME = "xlm-roberta-large-finetuned-conll03-german"

# Maps the NER model's raw entity_group labels to Presidio entity types.
# MISC has no Presidio equivalent and is dropped by default.
DEFAULT_LABEL_MAPPING = {
    "PER": "PERSON",
    "LOC": "LOCATION",
    "ORG": "ORGANIZATION",
}


class BertNerRecognizer(EntityRecognizer):
    """
    Presidio EntityRecognizer backed by a transformer NER model (native
    PyTorch), run alongside the existing SpacyRecognizer and DB-driven
    PatternRecognizers rather than replacing them.

    An ONNX Runtime backend was benchmarked first but dropped: on GPU, the
    native PyTorch pipeline already runs at ~15ms/call for the large model,
    and plain ONNX Runtime (without TensorRT/quantization, neither of which
    is set up here) offers no measurable improvement over that.

    The underlying model is loaded once and reused for the lifetime of the
    process; instantiate a single module-level instance and register it
    with the AnalyzerEngine registry rather than creating one per request
    or per reload.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        label_mapping: Optional[Dict[str, str]] = None,
        supported_language: str = "de",
        context: Optional[List[str]] = None,
        min_score: Optional[float] = None,
    ):
        self.model_name = model_name or os.getenv("BERT_NER_MODEL", DEFAULT_MODEL_NAME)
        self.label_mapping = label_mapping or DEFAULT_LABEL_MAPPING
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
            name="BertNerRecognizer",
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
            device = device_env
        else:
            device = 0 if torch.cuda.is_available() else -1

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

            results.append(
                RecognizerResult(
                    entity_type=entity_type,
                    start=pred["start"],
                    end=pred["end"],
                    score=float(pred["score"]),
                )
            )

        return results
