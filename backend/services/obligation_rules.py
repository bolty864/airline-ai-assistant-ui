"""Deterministic business rules: taxonomy, owner mapping, severity, mandatory language.

These are the source of truth. GPT proposes a type, but owner and severity always come from here,
so the same clause always gets the same owner and severity.
"""
from __future__ import annotations

import re

OBLIGATION_TAXONOMY: dict[str, str] = {
    "Data Retention": "Data Governance",
    "Data Deletion": "Data Governance",
    "Data Archival": "Data Governance",
    "Record Keeping": "Data Governance",
    "Cyber Security": "Information Security",
    "Incident Management": "Information Security",
    "Access Control": "Information Security",
    "Data Privacy": "Privacy Office",
    "Consent Management": "Privacy Office",
    "Training Compliance": "Flight Operations",
    "Certification Compliance": "Flight Operations",
    "Audit Compliance": "Internal Audit",
}
OTHER_TYPE = "Other"
OTHER_OWNER = "Compliance Office"
ALLOWED_TYPES: list[str] = [*OBLIGATION_TAXONOMY, OTHER_TYPE]

MANDATORY_RE = re.compile(r"\b(shall|must|mandatory|required|obligated\s+to)\b", re.I)
_HIGH_RE = re.compile(r"\b(shall|must)\b", re.I)
_MEDIUM_RE = re.compile(r"\brequired\b", re.I)


def has_mandatory_language(text: str) -> bool:
    return bool(MANDATORY_RE.search(text or ""))


def owner_for(obligation_type: str) -> str:
    return OBLIGATION_TAXONOMY.get(obligation_type, OTHER_OWNER)


def normalize_type(value: str | None) -> str:
    if not value:
        return OTHER_TYPE
    for t in ALLOWED_TYPES:
        if t.lower() == value.strip().lower():
            return t
    return OTHER_TYPE


def severity_for(text: str) -> str:
    """shall / must -> HIGH, required -> MEDIUM, otherwise LOW."""
    if _HIGH_RE.search(text or ""):
        return "HIGH"
    if _MEDIUM_RE.search(text or ""):
        return "MEDIUM"
    return "LOW"
