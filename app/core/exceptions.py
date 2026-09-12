"""Custom exception hierarchy for the TransiPulse API."""

from __future__ import annotations


class TransiPulseError(Exception):
    """Base class for all TransiPulse domain errors."""


class ResourceNotFound(TransiPulseError):
    """Raised when a route, trip, or feedback record cannot be located."""

    def __init__(self, resource: str, identifier: str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} not found: {identifier}")


class ValidationFailure(TransiPulseError):
    """Raised when domain-level validation fails (beyond Pydantic)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AIEngineError(TransiPulseError):
    """Raised when the local LLM pipeline fails irrecoverably."""

    def __init__(self, message: str) -> None:
        super().__init__(message)