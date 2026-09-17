"""Analytics API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.api.schemas import (
    DeteriorationEntry,
    RankingEntry,
    TemporalHeatmapResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/rankings", response_model=list[RankingEntry])
async def get_rankings(
    db: AsyncSession = Depends(get_db),
) -> list[RankingEntry]:
    """Bayesian route leaderboard (Best to Worst, sortable)."""
    service = AnalyticsService(db)
    results = await service.get_rankings()
    return [
        RankingEntry(
            route_id=r["route_id"],
            bayesian_rating=r["bayesian_rating"],
            raw_avg_rating=r["raw_avg_rating"],
            total_ratings=r["total_ratings"],
            rank=r["rank"],
            health_badge=r["health_badge"],
            top_issue=r.get("top_issue"),
            second_issue=r.get("second_issue"),
            worst_period=r.get("worst_period"),
            deterioration_status=r.get("deterioration_status", "STABLE"),
            total_complaints_month=r.get("complaint_count", r.get("total_complaints_month", 0)),
        )
        for r in results
    ]


@router.get("/deterioration", response_model=list[DeteriorationEntry])
async def get_deterioration(
    db: AsyncSession = Depends(get_db),
) -> list[DeteriorationEntry]:
    """List of routes experiencing rapid service deterioration."""
    service = AnalyticsService(db)
    results = await service.get_deterioration_list()
    return [
        DeteriorationEntry(
            route_id=r["route_id"],
            deterioration_velocity=r.get("velocity", 0.0),
            deterioration_status=r["status"],
            short_term_avg=r.get("short_term_avg", 0.0),
            long_term_avg=r.get("long_term_avg", 0.0),
            complaint_acceleration=r.get("accel", 0.0),
            recommendation=r.get("recommendation"),
        )
        for r in results
    ]


@router.get("/temporal-heatmap", response_model=TemporalHeatmapResponse)
async def get_temporal_heatmap(
    db: AsyncSession = Depends(get_db),
) -> TemporalHeatmapResponse:
    """Hour-by-hour complaint intensity matrix."""
    service = AnalyticsService(db)
    return await service.get_temporal_heatmap()