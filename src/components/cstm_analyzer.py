"""
Custom Analyzer module for text anonymization.

This module provides the CustomAnalyzer class that wraps Microsoft Presidio's
AnalyzerEngine and AnonymizerEngine to detect and mask sensitive entities
in medical text data. Supports both static patterns and database-loaded patterns.
"""

import logging
from typing import List, Optional

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer.nlp_engine import NlpEngineProvider
from sqlalchemy.orm import Session

# Note: MedicalPatternProvider moved to seed/ for initial database seeding only
# No static fallback - database is the single source of truth

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
        from src.database.crud import get_recognizers
        from src.database.models import RecognizerModel

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
    A custom analyzer that combines Presidio's analyzer and anonymizer
    with custom pattern recognizers for German medical text.

    Supports both static patterns (from MedicalPatternProvider) and
    dynamic patterns loaded from the database.

    Attributes:
        language (str): The language code for text analysis (default: "de").
        analyzer (AnalyzerEngine): The Presidio analyzer engine.
        anonymizer (AnonymizerEngine): The Presidio anonymizer engine.
    """

    def __init__(self, language: str = "de", db: Optional[Session] = None):
        """
        Initialize the CustomAnalyzer with NLP engine and custom recognizers.

        Args:
            language (str): Language code for text analysis. Defaults to "de".
            db (Optional[Session]): Database session for loading patterns.
                If None, falls back to static patterns.
        """
        self.language = language
        self.anonymizer = AnonymizerEngine()
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

            logger.info(f"GuardrailAnalyzer for '{language}' initialized with {len(recognizers)} custom recognizers")

        except Exception as e:
            logger.error(f"Error initializing the analyzer: {e}")

    def _remove_builtin_recognizers(self):
        """Remove all built-in Presidio recognizers except Spacy."""
        # Get all recognizer names first
        recognizer_names = [r.name for r in self.analyzer.registry.recognizers if hasattr(r, 'name')]
        logger.info(f"Available recognizers before cleanup: {recognizer_names}")

        # Keep Spacy and Pattern recognizers
        keep_recognizers = ['spacy_nlp', 'PatternRecognizer', 'Pattern', 'PatternRecognizerAdapter']

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

        logger.info(f"Reloaded {len(recognizers)} recognizers")
        return len(recognizers)
            

    def process_text(self, text: str, db: Optional[Session] = None) -> str:
        """
        Analyze and anonymize sensitive entities in the given text.

        This method identifies sensitive entities and replaces them with
        placeholders loaded from the database.

        Args:
            text (str): The input text to be anonymized.
            db (Optional[Session]): Database session for loading entity placeholders.

        Returns:
            str: The anonymized text with sensitive entities replaced by
                 masked placeholders. Returns empty string for whitespace-only input.
        """
        if not text.strip():
            return ""

        # Get all active entities from database
        db_session = db or self._db
        entity_placeholders = {}
        active_entities = []

        if db_session:
            try:
                from src.database.crud import get_entities
                db_entities = get_entities(db_session, active_only=True)
                for entity in db_entities:
                    entity_placeholders[entity.name] = entity.placeholder
                    active_entities.append(entity.name)
            except Exception as e:
                logger.warning(f"Could not load entity placeholders from DB: {e}")

        # Analyze text - only for active entities from DB
        # If no entities are active, only built-in recognizers that match active entities
        results = self.analyzer.analyze(
            text=text,
            language=self.language,
            entities=active_entities if active_entities else None
        )

        # Build operators dynamically from database entities
        operators = {}
        for entity_name, placeholder in entity_placeholders.items():
            operators[entity_name] = OperatorConfig("replace", {"new_value": placeholder})

        # Always provide DEFAULT fallback
        operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[SENSITIV]"})

        anonymized_results = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators
        )

        return anonymized_results.text
    