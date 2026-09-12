"""Feedback service — ingestion, filtering, and management of commuter feedback."""

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models import Feedback, FeedbackChannel, Category, Severity
from app.core.exceptions import ResourceNotFound


class FeedbackService:
    """Service for ingesting and querying feedback."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    async def submit_feedback(self, feedback_data: dict) -> Feedback:
        """Submit a new feedback record."""
        created_at = datetime.now()

        feedback = Feedback(
            id=str(uuid4()),
            route_id=feedback_data.get("route_id"),
            trip_id=feedback_data.get("trip_id"),
            created_at=created_at,
            hour_of_day=created_at.hour,
            punctuality_rating=feedback_data.get("punctuality_rating"),
            cleanliness_rating=feedback_data.get("cleanliness_rating"),
            crowding_rating=feedback_data.get("crowding_rating"),
            driver_rating=feedback_data.get("driver_rating"),
            overall_rating=feedback_data["overall_rating"],
            raw_comment=feedback_data.get("raw_comment"),
            stop_name=feedback_data.get("stop_name"),
            bus_id=feedback_data.get("bus_id"),
            channel=FeedbackChannel(feedback_data.get("channel", "WEB")),
        )
        self.db.add(feedback)
        await self.db.flush()

        # Trigger async AI classification (best-effort, non-blocking)
        await self._trigger_classification(feedback)

        return feedback

    async def _trigger_classification(self, feedback: Feedback) -> None:
        """Enqueue the feedback for AI classification if enabled."""
        if not settings.ai_enabled or not feedback.raw_comment:
            return
        try:
            from app.services.ai_service import AIService
            ai_service = AIService(self.db)
            await ai_service.classify_single(feedback)
        except Exception:
            # Classification is best-effort — never block feedback submission
            logger.debug("Background classification skipped for feedback %s", feedback.id)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    async def list_feedback(
        self,
        route_id: Optional[str] = None,
        time_slot: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[Severity] = None,
        channel: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Feedback]:
        """Query feedback with multi-dimensional filters."""
        stmt = select(Feedback)

        filters = []
        if route_id:
            filters.append(Feedback.route_id == route_id)
        if time_slot:
            # time_slot can be "peak", "off-peak", or "hour:HH"
            if time_slot.startswith("hour:"):
                hour_val = int(time_slot.split(":")[1])
                filters.append(Feedback.hour_of_day == hour_val)
            elif time_slot == "peak":
                filters.append(and_(Feedback.hour_of_day >= 7, Feedback.hour_of_day <= 9))
            elif time_slot == "evening_peak":
                filters.append(and_(Feedback.hour_of_day >= 17, Feedback.hour_of_day <= 19))
            elif time_slot == "off-peak":
                filters.append(
                    and_(
                        or_(*[Feedback.hour_of_day < 7, Feedback.hour_of_day > 19])
                    )
                )
        if channel:
            filters.append(Feedback.channel == FeedbackChannel(channel))
        if date_from:
            filters.append(Feedback.created_at >= date_from)
        if date_to:
            filters.append(Feedback.created_at < date_to)

        if filters:
            stmt = stmt.where(and_(*filters))

        # Join with AI classification for category/severity filtering
        if category or severity:
            from app.models.ai_classification import AIClassification
            stmt = stmt.join(AIClassification, Feedback.id == AIClassification.feedback_id, isouter=True)
            if category:
                stmt = stmt.where(AIClassification.primary_category == category)
            if severity:
                stmt = stmt.where(AIClassification.severity == severity)

        stmt = stmt.order_by(Feedback.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_feedback(self, feedback_id: str) -> Feedback:
        result = await self.db.execute(select(Feedback).where(Feedback.id == feedback_id))
        feedback = result.scalars().first()
        if feedback is None:
            raise ResourceNotFound("Feedback", feedback_id)
        return feedback

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------
    async def get_feedback_stats(
        self,
        route_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        """Return aggregate statistics for feedback queries."""
        stmt = select(
            func.count(Feedback.id).label("total"),
            func.avg(Feedback.overall_rating).label("avg_rating"),
            func.min(Feedback.overall_rating).label("min_rating"),
            func.max(Feedback.overall_rating).label("max_rating"),
        )
        filters = []
        if route_id:
            filters.append(Feedback.route_id == route_id)
        if date_from:
            filters.append(Feedback.created_at >= date_from)
        if date_to:
            filters.append(Feedback.created_at < date_to)
        if filters:
            stmt = stmt.where(and_(*filters))

        result = await self.db.execute(stmt)
        row = result.one()
        return {
            "total": row.total,
            "avg_rating": float(row.avg_rating) if row.avg_rating else None,
            "min_rating": float(row.min_rating) if row.min_rating else None,
            "max_rating": float(row.max_rating) if row.max_rating else None,
        }