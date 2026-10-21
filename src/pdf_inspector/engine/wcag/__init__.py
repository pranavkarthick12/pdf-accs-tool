"""WCAG 2.1 / 2.2 AA rules."""

from .wcag_rules import (
    WCAGTextAlternativesRule,
    WCAGTimeBasedMediaRule,
    WCAGAdaptableRule,
    WCAGDistinguishableRule,
    WCAGUseOfColorRule,
    WCAGContrastMinimumRule,
    WCAGImagesOfTextRule,
    WCAGNonTextContrastRule,
    WCAGKeyboardAccessibleRule,
    WCAGEnoughTimeRule,
    WCAGSeizuresRule,
    WCAGNavigableRule,
    WCAGInputModalitiesRule,
    WCAGReadableRule,
    WCAGPredictableRule,
    WCAGInputAssistanceRule,
    WCAGCompatibleRule,
)

from .wcag_meta import WCAG_GUIDELINE_META

WCAG_RULES = [
    WCAGTextAlternativesRule(),
    WCAGTimeBasedMediaRule(),
    WCAGAdaptableRule(),
    WCAGDistinguishableRule(),
    WCAGKeyboardAccessibleRule(),
    WCAGEnoughTimeRule(),
    WCAGSeizuresRule(),
    WCAGNavigableRule(),
    WCAGInputModalitiesRule(),
    WCAGReadableRule(),
    WCAGPredictableRule(),
    WCAGInputAssistanceRule(),
    WCAGCompatibleRule(),
]

__all__ = [
    "WCAG_RULES",
    "WCAG_GUIDELINE_META",
    "WCAGTextAlternativesRule",
    "WCAGTimeBasedMediaRule",
    "WCAGAdaptableRule",
    "WCAGDistinguishableRule",
    "WCAGUseOfColorRule",
    "WCAGContrastMinimumRule",
    "WCAGImagesOfTextRule",
    "WCAGNonTextContrastRule",
    "WCAGKeyboardAccessibleRule",
    "WCAGEnoughTimeRule",
    "WCAGSeizuresRule",
    "WCAGNavigableRule",
    "WCAGInputModalitiesRule",
    "WCAGReadableRule",
    "WCAGPredictableRule",
    "WCAGInputAssistanceRule",
    "WCAGCompatibleRule",
]
