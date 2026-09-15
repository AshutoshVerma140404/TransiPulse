"""Deterministic NLP fallback engine for comment classification.

When the local LLM is unavailable (loading, low-spec hardware, no GPU),
this Tier 2 engine provides instant classification using:
    - Regex-based keyword matching for category
    - Keyword-driven severity assessment
    - VADER-like sentiment scoring

This guarantees zero-downtime classification regardless of LLM availability.
"""

from __future__ import annotations

import re
from typing import Optional

from app.api.schemas import ClassificationResult
from app.core.logging import logger


# ---------------------------------------------------------------------------
# Keyword → category mapping
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Crowding": [
        "crowded", "packed", "full", "standing", "sardines", "overcrowded",
        "too many", "no space", "cramped", "full bus", "overflowing",
        "people standing", "capacity", "capacity exceeded",
    ],
    "Delays/Punctuality": [
        "late", "delay", "delayed", "on time", "schedule", "punctual", "punctuality",
        "missed connection", "wait", "waiting", "late again", "never on time",
        "running behind", "skipped my stop", "early", "slow", "traffic",
    ],
    "Cleanliness": [
        "dirty", "filthy", "clean", "cleanliness", "trash", "garbage", "stain",
        "smell", "smelly", "odor", "wipe", "disgusting", "messy", "unhygienic",
        "broken window", "leaking", "stain", "vomit",
    ],
    "Driver Behaviour": [
        "driver", "rude", "rude driver", "aggressive", "impatient", "swear",
        "yell", "yelling", "driver was", "operator", "conduct",
        "refused", "unprofessional", "dangerous driving", "speeding",
        "ran the red", "scared", "scary driver",
    ],
    "Vehicle Condition": [
        "broken", "repair", "maintenance", "engine", "AC", "ac", "broken door",
        "door", "brake", "brakes", "transmission", "engine noise",
        "suspension", "flat tire", "wheel", "wiper", "wiper blade",
        "oil", "leaking fluid", "smoke", "fire", "overheating",
    ],
    "Safety": [
        "safety", "dangerous", "accident", "crash", "injury", "hurt",
        "emergency", "fire", "smoke", "suspicious", "weapon", "fight",
        "assault", "theft", "stolen", "robbery", "scared", "unsafe",
    ],
    "Commendation": [
        "great", "good", "excellent", "thank", "thanks", "awesome",
        "friendly", "helpful", "recommend", "love", "best", "superb",
        "wonderful", "fantastic", "commendation", "praise",
    ],
}

# ---------------------------------------------------------------------------
# Keyword → severity mapping
# ---------------------------------------------------------------------------
SEVERITY_KEYWORDS: dict[str, list[str]] = {
    "Critical": [
        "emergency", "fire", "smoke", "accident", "crash", "injury", "hurt",
        "danger", "scared", "unsafe", "weapon", "assault", "robbery", "stolen",
        "overheating", "broken", "failed", "defective", "dangerous",
    ],
    "High": [
        "rude", "aggressive", "impatient", "dangerous", "scary", "yell",
        "yelling", "swear", "complaint", "horrible", "terrible", "awful",
        "overcrowded", "packed", "standing", "broken", "slow", "never",
    ],
    "Medium": [
        "late", "delay", "dirty", "messy", "smelly", "uncomfortable",
        "waiting", "too many", "cramped", "no space", "traffic",
    ],
    "Low": [
        "a bit", "slightly", "minor", "small", "inconvenient", "occasional",
        "sometimes", "rarely", "once",
    ],
}

# ---------------------------------------------------------------------------
# Sentiment keywords
# ---------------------------------------------------------------------------
POSITIVE_WORDS = [
    "great", "good", "excellent", "awesome", "friendly", "helpful",
    "thank", "thanks", "love", "best", "superb", "wonderful",
    "fantastic", "on time", "punctual", "clean", "comfortable",
    "recommend", "happy", "impressed", "perfect",
]
NEGATIVE_WORDS = [
    "bad", "terrible", "awful", "horrible", "hate", "worst",
    "broken", "late", "dirty", "crowded", "rude", "dangerous",
    "scared", "uncomfortable", "frustrating", "disappointed",
    "poor", "slow", "missed", "waste", "useless",
]


class HeuristicClassifier:
    """Deterministic NLP classifier using regex + keyword matching."""

    # ------------------------------------------------------------------
    # Category classification
    # ------------------------------------------------------------------
    def classify(self, comment: str) -> ClassificationResult:
        """Classify a comment using heuristic keyword matching."""
        comment_lower = comment.lower()

        # Category: best matching keyword set
        category_scores = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw.lower()) + r"\b", comment_lower))
            category_scores[category] = score

        if not any(category_scores.values()):
            primary_category = "Other"
        else:
            primary_category = max(category_scores, key=category_scores.get)

        # Severity: best matching severity keyword set
        severity_scores = {}
        for severity, keywords in SEVERITY_KEYWORDS.items():
            score = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw.lower()) + r"\b", comment_lower))
            severity_scores[severity] = score

        if not any(severity_scores.values()):
            severity = "Medium"
        else:
            severity = max(severity_scores, key=severity_scores.get)

        # Sentiment
        sentiment = self._classify_sentiment(comment_lower)

        # Urgency score (1-5)
        urgency = self._compute_urgency(severity, primary_category, comment_lower)

        # Actionable summary
        summary = self._generate_summary(primary_category, severity, comment)

        return ClassificationResult(
            category=primary_category,
            severity=severity,
            sentiment=sentiment,
            urgency_score=urgency,
            actionable_summary=summary,
            model_confidence=0.6,  # heuristic confidence lower than ML models
            model_source="heuristic",
        )

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------
    def _classify_sentiment(self, comment_lower: str) -> str:
        """Simple VADER-like sentiment classification."""
        pos_count = sum(1 for word in POSITIVE_WORDS if word in comment_lower)
        neg_count = sum(1 for word in NEGATIVE_WORDS if word in comment_lower)

        if pos_count > neg_count:
            return "Positive"
        if neg_count > pos_count:
            return "Negative"
        return "Neutral"

    # ------------------------------------------------------------------
    # Urgency
    # ------------------------------------------------------------------
    def _compute_urgency(self, severity: str, category: str, comment_lower: str) -> int:
        """Compute urgency score (1-5) based on severity and keywords."""
        base = {
            "Critical": 5,
            "High": 4,
            "Medium": 3,
            "Low": 2,
        }.get(severity, 3)

        # Boost for safety-related comments
        if any(kw in comment_lower for kw in ["fire", "smoke", "emergency", "danger", "injury"]):
            base = min(5, base + 1)

        # Boost for safety + critical category
        if category == "Safety" and severity in ("High", "Critical"):
            base = min(5, base + 1)

        return max(1, min(5, base))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _generate_summary(self, category: str, severity: str, comment: str) -> str:
        """Generate a concise operational insight summary."""
        summary = f"{category} issue detected — {severity} severity"
        if category == "Crowding":
            summary = f"Chronic crowding issue ({severity}) — consider additional capacity"
        elif category == "Delays/Punctuality":
            summary = f"Punctuality concern ({severity}) — investigate schedule adherence"
        elif category == "Safety":
            summary = f"Safety incident ({severity}) — immediate dispatch alert recommended"
        elif category == "Driver Behaviour":
            summary = f"Driver conduct issue ({severity}) — consider retraining"
        elif category == "Cleanliness":
            summary = f"Cleanliness concern ({severity}) — schedule deep cleaning"
        elif category == "Vehicle Condition":
            summary = f"Vehicle defect ({severity}) — maintenance check needed"
        elif category == "Commendation":
            summary = f"Positive feedback — acknowledge staff"
        return summary