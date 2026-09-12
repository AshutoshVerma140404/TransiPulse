"""Bonus AI subsystem: local LLM classification with deterministic fallback."""

from app.ai.classifier import OllamaClassifier, TransformersClassifier, LLMClassifier
from app.ai.fallback import HeuristicClassifier

__all__ = ["LLMClassifier", "OllamaClassifier", "TransformersClassifier", "HeuristicClassifier"]