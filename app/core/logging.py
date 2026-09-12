"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys

from app.core.config import settings


def setup_logging() -> logging.Logger:
    """Configure root logging with a clean console handler."""
    level = logging.DEBUG if settings.debug else logging.INFO

    logger = logging.getLogger(settings.app_name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Silence chatty libraries unless debugging
    for noisy in ("sqlalchemy.engine", "urllib3", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger


logger = setup_logging()