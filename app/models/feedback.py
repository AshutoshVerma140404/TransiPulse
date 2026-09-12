"""Feedback model — a commuter's multi-criteria rating + comment."""

from __future__ import annotations

import enum

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class FeedbackChannel(str, enum.Enum):
    """How the commuter submitted their feedback."""

    QR_CODE = "QR_CODE"
    APP = "APP"
    WEB = "WEB"
    IMPORT_311 = "IMPORT_311"


class Feedback(Base):
    """A single commuter feedback record with multi-criteria ratings."""

    __tablename__ = "feedback"

    id: str = Column(String(36), primary_key=True)
    route_id: str = Column(
        String(16), ForeignKey("routes.id", ondelete="SET NULL"), nullable=True
    )
    trip_id: str = Column(
        String(36), ForeignKey("trips.id", ondelete="SET NULL"), nullable=True
    )

    # Temporal
    created_at: DateTime = Column(DateTime(timezone=True), nullable=False)
    hour_of_day: int = Column(Integer, nullable=False, doc="0-23, extracted at ingestion")

    # Multi-criteria ratings (1.0 — 5.0)
    punctuality_rating: float = Column(Float, nullable=True)
    cleanliness_rating: float = Column(Float, nullable=True)
    crowding_rating: float = Column(Float, nullable=True)
    driver_rating: float = Column(Float, nullable=True)
    overall_rating: float = Column(Float, nullable=False)

    # Free-text
    raw_comment: str = Column(Text, nullable=True)
    stop_name: str = Column(String(256), nullable=True)
    bus_id: str = Column(String(32), nullable=True)

    # Source
    channel: FeedbackChannel = Column(String(32), default=FeedbackChannel.WEB, nullable=False)

    # Relationships
    route = relationship("Route", back_populates="feedback", lazy="joined")
    trip = relationship("Trip", back_populates="feedback")
    ai_classification = relationship(
        "AIClassification",
        back_populates="feedback",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )

    __table_args__ = (
        CheckConstraint(
            "overall_rating >= 1.0 AND overall_rating <= 5.0",
            name="ck_feedback_overall_rating_range",
        ),
        CheckConstraint(
            "hour_of_day >= 0 AND hour_of_day <= 23",
            name="ck_feedback_hour_range",
        ),
    )
