"""AI classification model — structured output from the local LLM pipeline."""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class Category(str, enum.Enum):
    """Feedback category enum."""

    CROWDING = "Crowding"
    DELAYS = "Delays/Punctuality"
    CLEANLINESS = "Cleanliness"
    DRIVER_BEHAVIOUR = "Driver Behaviour"
    VEHICLE_CONDITION = "Vehicle Condition"
    SAFETY = "Safety"
    COMMENDATION = "Commendation"
    OTHER = "Other"


class Severity(str, enum.Enum):
    """Operational severity of the classified feedback."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Sentiment(str, enum.Enum):
    """Sentiment polarity."""

    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class AIClassification(Base):
    """Structured classification result for a feedback record."""

    __tablename__ = "ai_classifications"

    id: str = Column(String(36), primary_key=True)
    feedback_id: str = Column(
        String(36), ForeignKey("feedback.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    primary_category: Category = Column(String(32), nullable=False)
    secondary_category: Category = Column(String(32), nullable=True)
    severity: Severity = Column(String(16), nullable=False)
    sentiment: Sentiment = Column(String(16), nullable=False)
    urgency_score: int = Column(Integer, nullable=False, doc="1-5")
    actionable_insight: str = Column(Text)
    model_confidence: float = Column(Float, doc="0.0 — 1.0")
    model_source: str = Column(String(32), default="heuristic")

    # Relationships
    feedback = relationship("Feedback", back_populates="ai_classification", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "urgency_score >= 1 AND urgency_score <= 5",
            name="ck_ai_urgency_range",
        ),
        CheckConstraint(
            "model_confidence >= 0.0 AND model_confidence <= 1.0",
            name="ck_ai_confidence_range",
        ),
    )
