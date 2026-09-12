"""Feedback API endpoints."""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ResourceNotFound
from app.core.logging import logger
from app.api.schemas import (
    FeedbackCreate,
    FeedbackResponse,
)
from app.models import FeedbackChannel
from app.services.feedback_service import FeedbackService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=FeedbackResponse)
async def submit_feedback(
    feedback_data: FeedbackCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """Submit commuter feedback (multi-criteria rating + comment)."""
    service = FeedbackService(db)
    try:
        feedback = await service.submit_feedback(feedback_data.model_dump())
        logger.info("Feedback submitted: route=%s rating=%.1f", feedback.route_id, feedback.overall_rating)
        return _to_response(feedback)
    except Exception as exc:
        logger.error("Failed to submit feedback: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/", response_model=list[FeedbackResponse])
async def list_feedback(
    route: Optional[str] = Query(None, alias="route_id", description="Filter by route ID"),
    time_slot: Optional[str] = Query(None, description="Filter by time slot (peak, evening_peak, off-peak, hour:HH)"),
    category: Optional[str] = Query(None, description="Filter by AI category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    date_from: Optional[datetime] = Query(None, description="Start date"),
    date_to: Optional[datetime] = Query(None, description="End date"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    """Query feedback with multi-dimensional filters."""
    service = FeedbackService(db)
    try:
        severity_enum = None
        if severity:
            from app.models import Severity
            severity_enum = Severity(severity)
        records = await service.list_feedback(
            route_id=route,
            time_slot=time_slot,
            category=category,
            severity=severity_enum,
            channel=channel,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )
        return [_to_response(r) for r in records]
    except ResourceNotFound:
        return []


@router.get("/stats", response_model=dict)
async def feedback_stats(
    route: Optional[str] = Query(None, alias="route_id"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregate stats for feedback queries."""
    service = FeedbackService(db)
    return await service.get_feedback_stats(route_id=route, date_from=date_from, date_to=date_to)


# ---------------------------------------------------------------------------
# Mappers
# ---------------------------------------------------------------------------
def _to_response(feedback) -> FeedbackResponse:
    """Map a Feedback ORM model to a FeedbackResponse schema."""
    ai_class = getattr(feedback, "ai_classification", None)
    return FeedbackResponse(
        id=feedback.id,
        route_id=feedback.route_id,
        trip_id=feedback.trip_id,
        created_at=feedback.created_at,
        hour_of_day=feedback.hour_of_day,
        punctuality_rating=feedback.punctuality_rating,
        cleanliness_rating=feedback.cleanliness_rating,
        crowding_rating=feedback.crowding_rating,
        driver_rating=feedback.driver_rating,
        overall_rating=feedback.overall_rating,
        raw_comment=feedback.raw_comment,
        stop_name=feedback.stop_name,
        bus_id=feedback.bus_id,
        channel=feedback.channel.value if isinstance(feedback.channel, FeedbackChannel) else feedback.channel,
        primary_category=ai_class.primary_category if ai_class else None,
        severity=ai_class.severity if ai_class else None,
        sentiment=ai_class.sentiment if ai_class else None,
        urgency_score=ai_class.urgency_score if ai_class else None,
    )