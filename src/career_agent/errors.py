"""Stable public errors for CLI and service boundaries."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Machine-readable error codes exposed by the CLI."""

    INVALID_INPUT = "invalid_input"
    NOT_READY = "not_ready"
    CONFLICT = "conflict"
    INTEGRITY_ERROR = "integrity_error"
    APPROVAL_REQUIRED = "approval_required"
    UNSAFE_PATH = "unsafe_path"


class CareerError(Exception):
    """Expected application error with safe structured details."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
