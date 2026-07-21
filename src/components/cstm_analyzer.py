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
from typing import List, Optional

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from sqlalchemy.orm import Session

from src.components.bert_recognizer import BertNerRecognizer
from src.database.crud import get_allowed_values, get_entities, get_recognizer_by_name, get_recognizers
from src.database.models import RecognizerModel

# Name of the seeded DB row (alembic/versions/007_seed_bert_ner_recognizer.py)
# that controls whether the BERT NER recognizer is registered.
BERT_NER_RECOGNIZER_NAME = "bert_ner"

# Logger
logger = logging.getLogger("uvicorn.error")

# NLP Configuration
nlp_configuration = {
    "nlp_engine_name": "spacy",
    "models" : [{
        "lang_code": "de",
        "model_name": "de_core_news_lg"
    }]
}

# Module-level singleton: the transformer model is expensive to load, so it
# must survive across CustomAnalyzer re-instantiations (e.g. every /reload
# call creates a brand new CustomAnalyzer). Enablement is controlled by the
# 'bert_ner' DB row (seeded active by default, toggleable via the admin UI);
# the model itself is only ever loaded on first actual use.
_bert_recognizer: Optional[BertNerRecognizer] = None


def _get_bert_ner_row(db: Optional[Session]) -> Optional[RecognizerModel]:
    """Fetch the 'bert_ner' recognizer row, if a DB session is available."""
    if db is None:
        return None
    try:
        return get_recognizer_by_name(db, BERT_NER_RECOGNIZER_NAME)
    except Exception as e:
        logger.warning(f"Could not read '{BERT_NER_RECOGNIZER_NAME}' recognizer from DB: {e}")
        return None


def _get_bert_recognizer(db: Optional[Session]) -> Optional[BertNerRecognizer]:
    """
    Lazily create and cache the BERT NER recognizer, if enabled.

    Enablement, context words and min_score are all sourced from the
    'bert_ner' DB row (toggleable via the admin UI, seeded active by
    default in 007_seed_bert_ner_recognizer.py). Falls back to the
    BERT_NER_ENABLED env var when no DB session/row is available (e.g. the
    benchmark script). The underlying model is only ever loaded once; on
    later calls (e.g. after /reload), only `.context`/`.min_score` on the
    cached instance are refreshed from the DB, not the model itself.
    """
    global _bert_recognizer

    row = _get_bert_ner_row(db)

    if row is not None:
        enabled = row.is_active
    else:
        enabled = os.getenv("BERT_NER_ENABLED", "false").lower() in ("1", "true", "yes")

    if not enabled:
        return None

    context_words = [cw.word for cw in row.context_words] if row is not None else []
    min_score = row.min_score if row is not None else None

    if _bert_recognizer is None:
        _bert_recognizer = BertNerRecognizer(context=context_words, min_score=min_score)
    else:
        _bert_recognizer.context = context_words
        _bert_recognizer.min_score = min_score

    return _bert_recognizer


def _index_placeholder(base_placeholder: str, index: int) -> str:
    """
    Turn a static placeholder into a unique, indexed one.

    Inserts the index before the closing bracket if present
    (e.g. "[EMAIL]" -> "[EMAIL_1]"), otherwise appends it as a suffix
    (e.g. "EMAIL" -> "EMAIL_1").

    Args:
        base_placeholder (str): The static placeholder (e.g. "[EMAIL]").
        index (int): The 1-based occurrence index.

    Returns:
        str: The indexed placeholder.
    """
    if base_placeholder.endswith("]"):
        return f"{base_placeholder[:-1]}_{index}]"
    return f"{base_placeholder}_{index}"


class DatabasePatternProvider:
    """
    Provider for pattern recognizers loaded from the database.

    This class provides methods to create PatternRecognizer instances
    from database-stored pattern configurations.
    """

    @staticmethod
    def get_recognizers_from_db(db: Session) -> List[PatternRecognizer]:
        """
        Load pattern recognizers from the database.

        Args:
            db: SQLAlchemy database session.

        Returns:
            List[PatternRecognizer]: List of PatternRecognizer instances
                created from active database recognizers.
        """
        recognizers = []
        db_recognizers = get_recognizers(db, active_only=True)

        for db_rec in db_recognizers:
            # Skip builtin recognizers - Presidio loads them automatically
            if db_rec.is_builtin:
                continue

            # Create patterns from database (custom recognizers only)
            patterns = []
            for db_pattern in db_rec.patterns:
                try:
                    pattern = Pattern(
                        name=db_pattern.name,
                        regex=db_pattern.regex,
                        score=db_pattern.score
                    )
                    patterns.append(pattern)
                except Exception as e:
                    logger.warning(f"Invalid pattern '{db_pattern.name}': {e}")
                    continue

            # Get context words
            context_words = [cw.word for cw in db_rec.context_words]

            # Create recognizer
            try:
                recognizer = PatternRecognizer(
                    supported_entity=db_rec.supported_entity,
                    patterns=patterns,
                    context=context_words if context_words else [],
                    supported_language=db_rec.supported_language
                )
                recognizers.append(recognizer)
                logger.debug(f"Loaded recognizer '{db_rec.name}' from database")
            except Exception as e:
                logger.error(f"Error creating recognizer '{db_rec.name}': {e}")

        return recognizers


class CustomAnalyzer:
    """
    A custom analyzer that combines Presidio's analyzer with custom pattern
    recognizers for German medical text, and replaces detected entities with
    unique, indexed placeholders.

    Patterns are loaded dynamically from the database; there is no static
    fallback.

    Attributes:
        language (str): The language code for text analysis (default: "de").
        analyzer (AnalyzerEngine): The Presidio analyzer engine.
    """

    def __init__(self, language: str = "de", db: Optional[Session] = None):
        """
        Initialize the CustomAnalyzer with NLP engine and custom recognizers.

        Args:
            language (str): Language code for text analysis. Defaults to "de".
            db (Optional[Session]): Database session for loading patterns.
                If None, no recognizers are loaded.
        """
        self.language = language
        self._db = db

        nlp_provider = NlpEngineProvider(
            nlp_configuration=nlp_configuration
        )
        nlp_engine = nlp_provider.create_engine()

        try:
            self.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                default_score_threshold=0.4
            )

            # Remove all built-in recognizers except Spacy (for PERSON, LOCATION detection)
            # We load everything from database only
            self._remove_builtin_recognizers()

            # Load custom patterns from database
            recognizers = self._load_recognizers(db)

            for recognizer in recognizers:
                self.analyzer.registry.add_recognizer(recognizer=recognizer)

            self._add_bert_recognizer(db)

            logger.info(f"GuardrailAnalyzer for '{language}' initialized with {len(recognizers)} custom recognizers")

        except Exception as e:
            logger.error(f"Error initializing the analyzer: {e}")

    def _remove_builtin_recognizers(self):
        """Remove all built-in Presidio recognizers except Spacy."""
        # Get all recognizer names first
        recognizer_names = [r.name for r in self.analyzer.registry.recognizers if hasattr(r, 'name')]
        logger.info(f"Available recognizers before cleanup: {recognizer_names}")

        # Keep only the built-in recognizers that matter for German medical data
        keep_recognizers = [
            'SpacyRecognizer',
            'EmailRecognizer',
            'PhoneRecognizer',
            'PatternRecognizer',
            'Pattern',
            'PatternRecognizerAdapter'
        ]

        for name in recognizer_names:
            if name not in keep_recognizers:
                try:
                    self.analyzer.registry.remove_recognizer(name)
                    logger.info(f"Removed built-in recognizer: {name}")
                except Exception as e:
                    logger.warning(f"Could not remove recognizer '{name}': {e}")

        # Log remaining recognizers
        remaining = [r.name for r in self.analyzer.registry.recognizers if hasattr(r, 'name')]
        logger.info(f"Remaining recognizers after cleanup: {remaining}")
            

    def _add_bert_recognizer(self, db: Optional[Session]) -> None:
        """Register the cached BERT NER recognizer, if enabled, without reloading the model."""
        bert_recognizer = _get_bert_recognizer(db)
        if bert_recognizer is not None:
            self.analyzer.registry.add_recognizer(recognizer=bert_recognizer)

    def _load_recognizers(self, db: Optional[Session]) -> List[PatternRecognizer]:
        """
        Load recognizers from database or fall back to static patterns.

        Args:
            db: Optional database session.

        Returns:
            List[PatternRecognizer]: List of pattern recognizers.
        """
        if db:
            try:
                recognizers = DatabasePatternProvider.get_recognizers_from_db(db)
                logger.info(f"Loaded {len(recognizers)} recognizers from database")
                return recognizers
            except Exception as e:
                logger.warning(f"Error loading from database: {e}")

        # No fallback - if DB is empty, return empty list
        logger.warning("No database session available, no recognizers loaded")
        return []
    

    def reload_patterns(self, db: Optional[Session] = None) -> int:
        """
        Reload pattern recognizers from the database.

        This removes custom recognizers and reloads them
        from the database. Built-in recognizers (Spacy) are preserved.

        Args:
            db: Database session. If None, uses stored session from init.

        Returns:
            int: Number of recognizers loaded.
        """
        db = db or self._db

        # Remove custom recognizers (those loaded from DB)
        # Keep built-in Spacy recognizer
        for recognizer in list(self.analyzer.registry.recognizers):
            if hasattr(recognizer, 'name') and recognizer.name not in ['spacy_nlp']:
                try:
                    self.analyzer.registry.remove_recognizer(recognizer.name)
                except Exception as e:
                    logger.debug(f"Could not remove recognizer '{recognizer.name}': {e}")

        # Re-remove built-ins (keep only Spacy)
        self._remove_builtin_recognizers()

        # Reload recognizers from database
        recognizers = self._load_recognizers(db)

        for recognizer in recognizers:
            self.analyzer.registry.add_recognizer(recognizer=recognizer)

        # Re-register the cached BERT recognizer (it was removed above along
        # with the other non-'spacy_nlp' recognizers); the underlying model
        # is not reloaded since _get_bert_recognizer() returns the cached instance.
        self._add_bert_recognizer(db)

        logger.info(f"Reloaded {len(recognizers)} recognizers")
        return len(recognizers)
            

    def process_text(self, text: str, db: Optional[Session] = None) -> tuple[str, dict[str, str]]:
        """
        Analyze and anonymize sensitive entities in the given text.

        This method identifies sensitive entities and replaces each occurrence
        with a unique, indexed placeholder loaded from the database (e.g.
        "[EMAIL_1]", "[EMAIL_2]"), so that multiple entities of the same type
        can be told apart. A mapping of placeholder to original value is
        returned alongside the anonymized text to allow de-anonymization.

        Args:
            text (str): The input text to be anonymized.
            db (Optional[Session]): Database session for loading entity placeholders.

        Returns:
            tuple[str, dict[str, str]]: The anonymized text with sensitive
                entities replaced by unique masked placeholders, and a mapping
                of placeholder to original value. Returns ("", {}) for
                whitespace-only input.
        """
        if not text.strip():
            return "", {}

        # Get all active entities from database
        db_session = db or self._db
        entity_placeholders = {}
        active_entities = []

        if db_session:
            try:
                db_entities = get_entities(db_session, active_only=True)
                for entity in db_entities:
                    entity_placeholders[entity.name] = entity.placeholder
                    active_entities.append(entity.name)
            except Exception as e:
                logger.warning(f"Could not load entity placeholders from DB: {e}")

        # Exact-match strings that should never be masked, regardless of
        # which recognizer flagged them (spaCy, BERT, or a custom pattern).
        allow_list: List[str] = []
        if db_session:
            try:
                allow_list = [v.value for v in get_allowed_values(db_session)]
            except Exception as e:
                logger.warning(f"Could not load allow-list from DB: {e}")

        # Analyze text - only for active entities from DB
        # If no entities are active, only built-in recognizers that match active entities
        results = self.analyzer.analyze(
            text=text,
            language=self.language,
            entities=active_entities if active_entities else None,
            allow_list=allow_list if allow_list else None
        )

        # Replace each match with a unique, indexed placeholder (e.g.
        # "[EMAIL_1]", "[EMAIL_2]") and record the original value in
        # `mapping`, so the same entity type can appear more than once in a
        # text without becoming ambiguous. Matches are applied left-to-right;
        # a match that overlaps one already placed is skipped.
        mapping: dict[str, str] = {}
        counters: dict[str, int] = {}
        output_parts: List[str] = []
        last_end = 0

        sorted_results = sorted(results, key=lambda r: (r.start, r.start - r.end))
        for result in sorted_results:
            if result.start < last_end:
                continue

            base_placeholder = entity_placeholders.get(result.entity_type, "[SENSITIV]")
            counters[result.entity_type] = counters.get(result.entity_type, 0) + 1
            indexed_placeholder = _index_placeholder(base_placeholder, counters[result.entity_type])
            mapping[indexed_placeholder] = text[result.start:result.end]

            output_parts.append(text[last_end:result.start])
            output_parts.append(indexed_placeholder)
            last_end = result.end

        output_parts.append(text[last_end:])

        return "".join(output_parts), mapping
    