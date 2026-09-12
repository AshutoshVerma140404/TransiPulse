"""Trip API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ResourceNotFound
from app.core.logging import logger
from app.models import Trip
from app.api.schemas import TripCreate, TripResponse
from app.services.trip_service import TripService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=TripResponse)
async def create_trip(
    trip_data: TripCreate,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """Register a new bus trip."""
    service = TripService(db)
    try:
        trip = await service.create_trip(trip_data.model_dump())
        return TripResponse.model_validate(trip)
    except Exception as exc:
        logger.error("Failed to create trip: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/", response_model=list[TripResponse])
async def list_trips(
    route_id: str = Query(None, description="Filter by route ID"),
    active_only: bool = Query(True, description="Filter to active trips"),
    db: AsyncSession = Depends(get_db),
) -> list[TripResponse]:
    """List bus trips."""
    service = TripService(db)
    trips = await service.list_trips(route_id=route_id, active_only=active_only)
    return [TripResponse.model_validate(t) for t in trips]


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip_detail(
    trip_id: str,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """Get a specific trip's details."""
    service = TripService(db)
    try:
        trip = await service.get_trip(trip_id)
        return TripResponse.model_validate(trip)
    except ResourceNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))