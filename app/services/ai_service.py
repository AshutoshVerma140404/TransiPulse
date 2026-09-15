"""AI classification service — local LLM pipeline with deterministic fallback."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models import Feedback, AIClassification, Category, Severity, Sentiment
from app.api.schemas import ClassificationResult
from app.ai.fallback import HeuristicClassifier
from app.core.exceptions import AIEngineError


class AIService:
    """AI classification service with dual-layer resilience.

    Tier 1: Local LLM (Ollama / HuggingFace Transformers)
    Tier 2: Deterministic heuristic fallback (regex + keyword matching)
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._heuristic = HeuristicClassifier()
        self._ollama_client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def classify_single(self, feedback: Feedback) -> AIClassification:
        """Classify a single feedback record.

        Runs through Tier 1 → Tier 2 → raises error if both fail.
        """
        if not feedback.raw_comment:
            return await self._empty_classification(feedback)

        comment = feedback.raw_comment.strip()

        # Tier 1: Local LLM
        if settings.ai_enabled and settings.ai_provider in ("ollama", "transformers"):
            try:
                result = await self._classify_with_llm(comment)
                if result:
                    await self._save_classification(feedback, result, model_source=settings.ai_provider)
                    return result
            except Exception as exc:
                logger.debug("LLM classification failed: %s", exc)

        # Tier 2: Heuristic fallback
        if settings.ai_fallback_enabled:
            result = self._heuristic.classify(comment)
            await self._save_classification(feedback, result, model_source="heuristic")
            return result

        # Both tiers failed — return empty classification
        return await self._empty_classification(feedback)

    async def batch_classify(self, route_id: Optional[str] = None, limit: int = 100, force: bool = False) -> int:
        """Batch-classify unclassified feedback records."""
        stmt = select(Feedback).where(Feedback.ai_classification == None)  # noqa: E711
        if route_id:
            stmt = stmt.where(Feedback.route_id == route_id)
        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        feedback_list = list(result.scalars().all())

        count = 0
        for feedback in feedback_list:
            try:
                classification = await self.classify_single(feedback)
                count += 1
                if count % 10 == 0:
                    logger.info("Batch classified %d/%d", count, len(feedback_list))
            except Exception as exc:
                logger.debug("Skipping classification for %s: %s", feedback.id, exc)
                continue

        return count

    async def classify_text(self, comment: str) -> ClassificationResult:
        """Classify a free-text comment directly (no DB write)."""
        if settings.ai_enabled and settings.ai_provider in ("ollama", "transformers"):
            try:
                result = await self._classify_with_llm(comment)
                if result:
                    return result
            except Exception:
                pass

        return self._heuristic.classify(comment)

    # ------------------------------------------------------------------
    # Tier 1: Local LLM (Ollama)
    # ------------------------------------------------------------------
    async def _classify_with_llm(self, comment: str) -> Optional[ClassificationResult]:
        """Classify via local LLM (Ollama first, Gemini fallback)."""
        # Tier 1a: Ollama
        if settings.ai_provider == "ollama":
            result = await self._classify_ollama(comment)
            if result:
                return result
            logger.debug("Ollama unavailable — trying Gemini fallback")

        # Tier 1b: Google Gemini (if API key present)
        result = await self._classify_gemini(comment)
        if result:
            return result

        # Tier 1c: HuggingFace Transformers
        if settings.ai_provider == "transformers":
            return await self._classify_transformers(comment)

        return None

    async def _classify_ollama(self, comment: str) -> Optional[ClassificationResult]:
        """Classify using Ollama local LLM via async httpx REST call."""
        import httpx

        prompt = self._build_ollama_prompt(comment)
        payload = {
            "model": settings.ai_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": settings.ai_max_tokens,
                "temperature": settings.ai_temperature,
            },
        }
        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_host,
                timeout=settings.ai_timeout_seconds,
            ) as client:
                resp = await client.post("/api/generate", json=payload)
                resp.raise_for_status()
                result_text = resp.json().get("response", "{}")
            return self._parse_llm_response(result_text)
        except Exception as exc:
            logger.debug("Ollama classification failed: %s", exc)
            return None

    async def _classify_gemini(self, comment: str) -> Optional[ClassificationResult]:
        """Classify using Google Gemini API when Ollama is offline."""
        import os
        import httpx

        api_key = os.environ.get("GOOGLE_API_KEY", "").strip().strip("'\"")
        if not api_key:
            logger.debug("Gemini fallback skipped: GOOGLE_API_KEY not set")
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        prompt = self._build_ollama_prompt(comment)  # same structured prompt
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": settings.ai_temperature,
                "maxOutputTokens": settings.ai_max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
                resp = await client.post(url, json=payload, params={"key": api_key})
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = self._parse_llm_response(text)
            if result:
                result.model_source = "gemini"
            return result
        except Exception as exc:
            logger.debug("Gemini classification failed: %s", exc)
            return None

    async def _classify_transformers(self, comment: str) -> Optional[ClassificationResult]:
        """Classify using HuggingFace Transformers pipeline."""
        try:
            from transformers import pipeline  # type: ignore

            # Use zero-shot classification pipeline
            classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
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
            result = classifier(comment, candidate_labels, multi_label=True)

            primary = result["labels"][0] if result["labels"] else "Other"
            score = result["scores"][0] if result["scores"] else 0.5

            return ClassificationResult(
                category=primary,
                severity=self._severity_from_score(score),
                sentiment="Neutral",  # Simplified
                urgency_score=min(5, max(1, int(score * 5))),
                actionable_summary=comment[:200],
                model_confidence=float(score),
                model_source="transformers",
            )
        except Exception as exc:
            logger.debug("Transformers classification failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Parsing & helpers
    # ------------------------------------------------------------------
    def _parse_llm_response(self, text: str) -> Optional[ClassificationResult]:
        """Parse structured JSON from LLM output."""
        try:
            # Try to find JSON block
            match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if not match:
                return None
            import json
            data = json.loads(match.group())
            return ClassificationResult(
                category=data.get("category", "Other"),
                severity=data.get("severity", "Medium"),
                sentiment=data.get("sentiment", "Neutral"),
                urgency_score=int(data.get("urgency_score", 3)),
                actionable_summary=data.get("actionable_summary", ""),
                model_confidence=float(data.get("model_confidence", 0.8)),
                model_source="llm",
            )
        except Exception:
            return None

    def _build_ollama_prompt(self, comment: str) -> str:
        """Build the Ollama prompt."""
        return f"""You are TransiPulse AI, an intelligent public transport incident classifier.
Analyze the commuter comment and return ONLY valid JSON with keys:
- category: ["Crowding", "Delays/Punctuality", "Cleanliness", "Driver Behaviour", "Vehicle Condition", "Safety", "Commendation"]
- severity: ["Low", "Medium", "High", "Critical"]
- sentiment: ["Positive", "Neutral", "Negative"]
- urgency_score: Integer from 1 to 5
- actionable_summary: Concise description of the operational defect

Comment: "{comment}"

{{
  "category": "",
  "severity": "",
  "sentiment": "",
  "urgency_score": 3,
  "actionable_summary": ""
}}"""

    def _severity_from_score(self, score: float) -> str:
        if score >= 0.8:
            return "Critical"
        if score >= 0.6:
            return "High"
        if score >= 0.4:
            return "Medium"
        return "Low"

    # ------------------------------------------------------------------
    # Ollama health probe
    # ------------------------------------------------------------------
    @staticmethod
    async def probe_ollama() -> dict:
        """Probe the local Ollama server and return status info."""
        import os
        import httpx

        api_key = os.environ.get("GOOGLE_API_KEY", "").strip().strip("'\"")
        gemini_available = bool(api_key)

        try:
            async with httpx.AsyncClient(
                base_url=settings.ollama_host,
                timeout=3.0,
            ) as client:
                resp = await client.get("/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                configured = settings.ai_model
                available = configured in models
                return {
                    "status": "online",
                    "host": settings.ollama_host,
                    "configured_model": configured,
                    "model_available": available,
                    "installed_models": models,
                    "gemini_fallback": gemini_available,
                    "gemini_model": settings.gemini_model,
                }
        except Exception as exc:
            return {
                "status": "offline",
                "host": settings.ollama_host,
                "configured_model": settings.ai_model,
                "model_available": False,
                "installed_models": [],
                "error": str(exc),
                "gemini_fallback": gemini_available,
                "gemini_model": settings.gemini_model,
            }

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------
    async def _save_classification(
        self,
        feedback: Feedback,
        result: ClassificationResult,
        model_source: str,
    ) -> AIClassification:
        """Persist the classification result to the database."""
        import uuid
        from datetime import datetime

        classification = AIClassification(
            id=str(uuid.uuid4()),
            feedback_id=feedback.id,
            primary_category=Category(result.category),
            severity=Severity(result.severity),
            sentiment=Sentiment(result.sentiment) if result.sentiment in [s.value for s in Sentiment] else Sentiment.NEUTRAL,
            urgency_score=result.urgency_score,
            actionable_insight=result.actionable_summary,
            model_confidence=result.model_confidence,
            model_source=model_source,
        )
        self.db.add(classification)
        await self.db.flush()
        return classification

    async def _empty_classification(self, feedback: Feedback) -> AIClassification:
        """Return a default empty classification for comments without text."""
        import uuid
        from datetime import datetime

        classification = AIClassification(
            id=str(uuid.uuid4()),
            feedback_id=feedback.id,
            primary_category=Category.OTHER,
            severity=Severity.LOW,
            sentiment=Sentiment.NEUTRAL,
            urgency_score=1,
            actionable_insight="No comment provided",
            model_confidence=0.0,
            model_source="none",
        )
        self.db.add(classification)
        await self.db.flush()
        return classification