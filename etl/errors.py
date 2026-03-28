"""Custom exceptions for the ETL pipeline."""

from __future__ import annotations


class ETLError(Exception):
    """Base class for all pipeline errors."""


class ExtractError(ETLError):
    """Raised when the extract step cannot produce a usable DataFrame."""


class TransformError(ETLError):
    """Raised when a transform step fails irrecoverably."""


class LoadError(ETLError):
    """Raised when the load step cannot write to the database."""


class ConfigError(ETLError):
    """Raised when required configuration (e.g. env vars) is missing."""
