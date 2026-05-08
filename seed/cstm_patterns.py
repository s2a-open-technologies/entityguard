"""
Custom pattern recognizers for German medical and privacy-related entities.

This module provides the MedicalPatternProvider class that defines custom
regex-based patterns for detecting sensitive entities specific to the
German healthcare context, including medical institutions, professions,
phone numbers, email addresses, and patient case numbers.
"""

from presidio_analyzer import PatternRecognizer, Pattern


class MedicalPatternProvider:
    """
    Central provider for all custom pattern recognizers.

    This class provides static methods to create and return a list of
    PatternRecognizer instances configured with custom patterns for
    German medical and privacy-related entity detection.
    """

    @staticmethod
    def get_custom_recognizers() -> list[PatternRecognizer]:
        """
        Create and return a list of custom pattern recognizers.

        Returns:
            list[PatternRecognizer]: A list of configured PatternRecognizer
                instances for detecting:
                - Medical context entities (professions, unions, health insurers)
                - German phone numbers
                - Email addresses
                - Patient case numbers and birth dates in medical context

        The recognizers cover:
            - MEDICAL_CONTEXT: Exposed professions (mayor, CEO, chief physician),
              German unions (ver.di, IG Metall), health insurers (AOK, TK, Barmer)
            - PHONE_NUMBER: German phone numbers with +49 or 0 prefix
            - EMAIL_ADDRESS: Standard email format
            - MEDICAL_CONTEXT: Case numbers (5+ digits) and birth dates (DD.MM.YYYY)
              when appearing in medical context (patient, file, record)
        """
        # GDPR Article 9 & Context Identifiers

        # 1. GDPR & Medical Context
        med_patterns = [
            Pattern(name="berufe_exponiert", regex=r"(?i)\b(Bürgermeister|Landrat|Vorstand|Abgeordneter|Chefarzt)\b", score=0.85),
            Pattern(name="gewerkschaft_de", regex=r"(?i)\b(ver\.di|IG Metall|GEW|Marburger Bund|Gewerkschaft)\b", score=0.95),
            Pattern(name="krankenkasse_de", regex=r"(?i)\b(AOK|TK|Techniker Krankenkasse|Barmer|DAK|Hallesche|Debeka)\b", score=0.9),
        ]
        med_recognizer = PatternRecognizer(supported_entity="MEDICAL_CONTEXT", patterns=med_patterns, supported_language="de")

        # Phone number patterns for German numbers
        phone_patterns = [
            Pattern(
                name="telefonnummern_deutschland",
                regex=r"(?:\+49|0|[Oo])(?:\s*\d{2,5}\s*)(?:[/-]?\s*\d{3,9})",
                score=0.85)
        ]
        phone_recognizer = PatternRecognizer(supported_entity="PHONE_NUMBER", patterns=phone_patterns, supported_language="de")

        # Email address patterns
        email_patterns = [
            Pattern(
                name="email_regex",
                regex=r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
                score=0.95)
        ]
        email_recognizer = PatternRecognizer(supported_entity="EMAIL_ADDRESS", patterns=email_patterns, supported_language="de")

        # Case number patterns with low score, extended by context
        fall_patterns = [
            Pattern(
                name="fallnummer_generic",
                regex=r"\b\d{5,}\b",
                score=0.3
            ),
            Pattern(
                name="geburtsdatum_generic",
                regex=r"\d{1,2}\.\d{1,2}\.\d{2,4}",
                score=0.3
            )
        ]

        fall_context = [
            "fall", "fallnr", "fallnummer", "fallid", "patient", "patientennummer", "akte", "befund", "aktenzeichen", "az"
        ]


        fall_recognizer = PatternRecognizer(
            supported_entity="MEDICAL_CONTEXT",
            patterns=fall_patterns,
            context=fall_context,
            supported_language="de"
        )

        return [
            med_recognizer, phone_recognizer, email_recognizer, fall_recognizer
        ]
