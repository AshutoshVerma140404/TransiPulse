"""Bonus AI API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.api.schemas import (
    BatchProcessRequest,
    ClassifyRequest,
    ClassifyResponse,
)
from app.services.ai_service import AIService

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse, status_code=status.HTTP_200_OK)
async def classify_comment(
    request: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
) -> ClassifyResponse:
    """On-demand Local LLM classification of comment."""
    try:
        service = AIService(db)
        result = await service.classify_text(request.comment)
        return ClassifyResponse(classification=result)
    except Exception as exc:
        logger.error("AI classification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification failed: {exc}",
        )


@router.post("/batch-process", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def batch_classify(
    request: BatchProcessRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Batch classification of unclassified comments."""
    try:
        service = AIService(db)
        count = await service.batch_classify(
            route_id=request.route_id,
            limit=request.limit,
            force=request.force,
        )
        return {
            "message": f"Batch classification complete",
            "processed": count,
            "route_filter": request.route_id,
        }
    except Exception as exc:
        logger.error("Batch classification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch classification failed: {exc}",
        )
