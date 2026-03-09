"""
Custom Analyzer module for text anonymization.

This module provides the CustomAnalyzer class that wraps Microsoft Presidio's
AnalyzerEngine and AnonymizerEngine to detect and mask sensitive entities
in medical text data.
"""

import logging
from typing import List

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .cstm_patterns import MedicalPatternProvider

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


class CustomAnalyzer:
    """
    A custom analyzer that combines Presidio's analyzer and anonymizer
    with custom pattern recognizers for German medical text.

    Attributes:
        language (str): The language code for text analysis (default: "de").
        analyzer (AnalyzerEngine): The Presidio analyzer engine.
        anonymizer (AnonymizerEngine): The Presidio anonymizer engine.
    """

    def __init__(self, language: str = "de"):
        """
        Initialize the CustomAnalyzer with NLP engine and custom recognizers.

        Args:
            language (str): Language code for text analysis. Defaults to "de".
        """
        self.language = language
        self.anonymizer = AnonymizerEngine()

        nlp_provider = NlpEngineProvider(
            nlp_configuration=nlp_configuration
        )
        nlp_engine = nlp_provider.create_engine()

        try:
            self.analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                default_score_threshold=0.4
            )

            for recognizer in MedicalPatternProvider.get_custom_recognizers():
                self.analyzer.registry.add_recognizer(recognizer=recognizer)

            logger.info(f"GuardrailAnalyzer for '{language}' initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing the analyzer: {e}")
            

    def process_text(self, text: str) -> str:
        """
        Analyze and anonymize sensitive entities in the given text.

        This method identifies sensitive entities (PERSON, LOCATION, DATE_TIME,
        EMAIL_ADDRESS, PHONE_NUMBER, MEDICAL_CONTEXT, IBAN_CODE, FALLNUMMER)
        and replaces them with masked placeholders.

        Args:
            text (str): The input text to be anonymized.

        Returns:
            str: The anonymized text with sensitive entities replaced by
                 masked placeholders. Returns empty string for whitespace-only input.
        """
        if not text.strip():
            return ""

        active_entities = [
            "PERSON", "LOCATION", "DATE_TIME", "EMAIL_ADDRESS", "PHONE_NUMBER", "MEDICAL_CONTEXT", "IBAN_CODE", "FALLNUMMER"
        ]

        results = self.analyzer.analyze(
            text=text,
            language=self.language,
            entities=active_entities
        )

        operators = {
            "PERSON": OperatorConfig("replace", {"new_value": "[NAME]"}),
            "LOCATION": OperatorConfig("replace", {"new_value": "[ADRESSE/ORT]"}),
            "DATE_TIME": OperatorConfig("replace", {"new_value": "[DATUM/ZEIT]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[TELEFON]"}),
            "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP_ADRESSE]"}),
            "MEDICAL_CONTEXT": OperatorConfig("replace", {"new_value": "[MED_IDENTIFIKATOR]"}),
            "DEFAULT": OperatorConfig("replace", {"new_value": "[SENSITIV]"}),
        }

        anonymized_results = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators
        )

        return anonymized_results.text
    