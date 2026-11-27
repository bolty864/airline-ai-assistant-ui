"""Exceptions shared by several agents (mapped to HTTP status codes in main.py)."""
from __future__ import annotations


class DocumentNotFoundError(Exception):
    pass


class DocumentNotReadyError(Exception):
    """Document is MISSING or HEALING (Agent 1 is restoring it)."""


class EnterpriseRepositoryEmptyError(Exception):
    """No controls are registered, so every obligation would wrongly come out as a Missing Control."""


class GapAnalysisError(Exception):
    pass


class InvalidComparisonError(Exception):
    """The requested comparison makes no sense (for example a document against itself)."""
