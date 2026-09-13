"""Routes API endpoints."""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ResourceNotFound
from app.core.logging import logger
from app.models import Route, RouteAnalyticsCache
from app.api.schemas import RouteCreate, RouteResponse
from app.services.route_service import RouteService
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=RouteResponse)
async def create_route(
    route_data: RouteCreate,
    db: AsyncSession = Depends(get_db),
) -> RouteResponse:
    """Create a new bus route."""
    service = RouteService(db)
    route = await service.create_route(route_data.model_dump())
    return RouteResponse.model_validate(route)


@router.get("/", response_model=list[RouteResponse])
async def list_routes(
    active_only: bool = Query(True, description="Filter to active routes only"),
    db: AsyncSession = Depends(get_db),
) -> list[RouteResponse]:
    """List all monitored routes with health badges."""
    service = RouteService(db)
    routes = await service.list_routes(active_only=active_only)
    return [await _route_to_response(r, db) for r in routes]


@router.get("/{route_id}", response_model=RouteResponse)
async def get_route_detail(
    route_id: str,
    db: AsyncSession = Depends(get_db),
) -> RouteResponse:
    """Detailed operational route profile."""
    service = RouteService(db)
    try:
        return await service.get_route_response(route_id)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{route_id}/summary", response_model=dict)
async def get_route_summary(
    route_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Case study required card format (Rating, Top Issues, Worst Period, Monthly Count)."""
    analytics_service = AnalyticsService(db)
    summary = await analytics_service.get_route_summary(route_id)
    return summary.model_dump()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _route_to_response(route: Route, db: AsyncSession) -> RouteResponse:
    """Map Route ORM to RouteResponse with cached analytics."""
    from sqlalchemy import select

    cache_result = await db.execute(select(RouteAnalyticsCache).where(RouteAnalyticsCache.route_id == route.id))
    cache = cache_result.scalars().first()

    return RouteResponse(
        id=route.id,
        name=route.name,
        origin=route.origin,
        destination=route.destination,
        route_type=route.route_type.value if hasattr(route.route_type, "value") else route.route_type,
        total_buses_assigned=route.total_buses_assigned,
        is_active=route.is_active,
        color=route.color,
        health_badge=cache.health_badge if cache else None,
        bayesian_rating=cache.bayesian_rating if cache else None,
        total_complaints_month=cache.total_complaints_month if cache else None,
        worst_period=cache.worst_period if cache else None,
        deterioration_status=cache.deterioration_status if cache else None,
    )