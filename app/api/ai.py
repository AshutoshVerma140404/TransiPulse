"""Bonus AI API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.logging import logger
from app.api.schemas import (
    BatchProcessRequest,
    ClassifyRequest,
    ClassifyResponse,
)
from app.services.ai_service import AIService

router = APIRouter()


@router.get("/status", status_code=status.HTTP_200_OK)
async def ai_status() -> dict:
    """Probe local Ollama server and return health + model availability."""
    probe = await AIService.probe_ollama()
    probe["ai_provider"] = settings.ai_provider
    probe["ai_enabled"] = settings.ai_enabled
    probe["fallback_enabled"] = settings.ai_fallback_enabled
    return probe


@router.get("/models", status_code=status.HTTP_200_OK)
async def list_models() -> dict:
    """List all locally installed Ollama models."""
    probe = await AIService.probe_ollama()
    return {
        "installed_models": probe.get("installed_models", []),
        "configured_model": probe.get("configured_model"),
        "model_available": probe.get("model_available", False),
        "ollama_status": probe.get("status"),
    }


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
            "message": "Batch classification complete",
            "processed": count,
            "route_filter": request.route_id,
        }
    except Exception as exc:
        logger.error("Batch classification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch classification failed: {exc}",
        )
