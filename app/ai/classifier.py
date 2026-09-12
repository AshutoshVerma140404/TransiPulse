"""Local LLM / SLM classifier for comment classification.

Supports multiple backend providers:
    - Ollama (quantized Llama-3.2-1B / Qwen2.5-1.5B)
    - HuggingFace Transformers (distilbert / zero-shot)
    - ONNX Runtime (for quantized models)

All models run locally — no cloud API keys required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.api.schemas import ClassificationResult
from app.core.config import settings
from app.core.logging import logger


class LLMClassifier(ABC):
    """Abstract base class for local LLM classifiers."""

    @abstractmethod
    async def classify(self, comment: str) -> Optional[ClassificationResult]:
        """Classify a comment into category/severity/sentiment/urgency."""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError


class OllamaClassifier(LLMClassifier):
    """Ollama-based local LLM classifier."""

    def __init__(self, model: str = "llama3.2:1b-instruct-q4_K_M") -> None:
        self._model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_available(self) -> bool:
        try:
            import ollama  # noqa: F401
            return True
        except ImportError:
            return False

    async def classify(self, comment: str) -> Optional[ClassificationResult]:
        if not self.is_available:
            return None
        try:
            import ollama
            import json
            import re

            prompt = self._build_prompt(comment)
            response = ollama.generate(
                model=self._model,
                prompt=prompt,
                options={"num_predict": 256, "temperature": 0.0},
                timeout=15,
            )
            text = response.get("response", "{}")

            # Parse JSON from response
            match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group())
            return ClassificationResult(
                category=data.get("category", "Other"),
                severity=data.get("severity", "Medium"),
                sentiment=data.get("sentiment", "Neutral"),
                urgency_score=int(data.get("urgency_score", 3)),
                actionable_summary=data.get("actionable_summary", ""),
                model_confidence=float(data.get("model_confidence", 0.8)),
                model_source="ollama",
            )
        except Exception as exc:
            logger.debug("Ollama classification error: %s", exc)
            return None

    def _build_prompt(self, comment: str) -> str:
        return (
            'You are TransiPulse AI, an intelligent public transport incident classifier.\n'
            'Analyze the commuter comment and return ONLY valid JSON with keys:\n'
            '- category: ["Crowding", "Delays/Punctuality", "Cleanliness", "Driver Behaviour", "Vehicle Condition", "Safety", "Commendation"]\n'
            '- severity: ["Low", "Medium", "High", "Critical"]\n'
            '- sentiment: ["Positive", "Neutral", "Negative"]\n'
            '- urgency_score: Integer from 1 to 5\n'
            '- actionable_summary: Concise description of the operational defect\n\n'
            f'Comment: "{comment}"\n\n'
            "{\n  \"category\": \"\",\n  \"severity\": \"\",\n  \"sentiment\": \"\",\n  \"urgency_score\": 3,\n  \"actionable_summary\": \"\"\n}"
        )


class TransformersClassifier(LLMClassifier):
    """HuggingFace Transformers-based zero-shot classifier."""

    def __init__(self, model: str = "facebook/bart-large-mnli") -> None:
        self._model = model
        self._pipeline = None

    @property
    def provider_name(self) -> str:
        return "transformers"

    @property
    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401
            return True
        except ImportError:
            return False

    async def classify(self, comment: str) -> Optional[ClassificationResult]:
        if not self.is_available:
            return None
        try:
            from transformers import pipeline

            if self._pipeline is None:
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=self._model,
                )

            candidate_labels = [
                "Crowding",
                "Delays/Punctuality",
                "Cleanliness",
                "Driver Behaviour",
                "Vehicle Condition",
                "Safety",
                "Commendation",
            ]
            result = self._pipeline(comment, candidate_labels, multi_label=True)

            primary = result["labels"][0] if result["labels"] else "Other"
            score = result["scores"][0] if result["scores"] else 0.5

            return ClassificationResult(
                category=primary,
                severity=self._severity_from_score(score),
                sentiment="Neutral",
                urgency_score=min(5, max(1, int(score * 5))),
                actionable_summary=comment[:200],
                model_confidence=float(score),
                model_source="transformers",
            )
        except Exception as exc:
            logger.debug("Transformers classification error: %s", exc)
            return None

    @staticmethod
    def _severity_from_score(score: float) -> str:
        if score >= 0.8:
            return "Critical"
        if score >= 0.6:
            return "High"
        if score >= 0.4:
            return "Medium"
        return "Low"