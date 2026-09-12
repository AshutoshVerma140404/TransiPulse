"""RouteAnalyticsCache model — pre-computed analytics snapshot per route."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class RouteAnalyticsCache(Base):
    """Cached analytics snapshot for a route, refreshed by the analytics engine.

    This avoids recomputing expensive aggregates on every dashboard request.
    """

    __tablename__ = "route_analytics_cache"

    route_id: str = Column(
        String(16), ForeignKey("routes.id", ondelete="CASCADE"), primary_key=True
    )

    updated_at: DateTime = Column(DateTime(timezone=True), nullable=False)

    # Bayesian-adjusted score
    bayesian_rating: float = Column(Float, nullable=False)
    raw_avg_rating: float = Column(Float)

    # Volume metrics
    total_ratings: int = Column(Integer, default=0)
    total_complaints_month: int = Column(Integer, default=0)
    complaints_7d: int = Column(Integer, default=0)
    complaints_30d: int = Column(Integer, default=0)

    # Issue analysis
    top_issue: str = Column(String(64), nullable=True)
    second_issue: str = Column(String(64), nullable=True)
    worst_period: str = Column(String(32), nullable=True)

    # Deterioration
    deterioration_velocity: float = Column(Float, default=0.0)
    deterioration_status: str = Column(String(48), default="STABLE")

    # Recommendations
    recommendation: str = Column(Text, nullable=True)

    # Ranking metadata
    rank: int = Column(Integer, nullable=True)
    health_badge: str = Column(String(16), doc="HEALTHY | WARNING | CRITICAL")

    def to_case_study_dict(self) -> dict:
        """Return the exact output format required by the case study."""
        return {
            "route_id": self.route_id,
            "overall_rating": round(self.bayesian_rating, 1),
            "top_issue": self.top_issue,
            "second_issue": self.second_issue,
            "worst_period": self.worst_period,
            "complaints_this_month": self.total_complaints_month,
            "deterioration_status": self.deterioration_status,
            "recommendation": self.recommendation,
        }

    # Relationship
    route = relationship("Route", back_populates="analytics")
