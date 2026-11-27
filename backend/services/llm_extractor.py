"""Clause -> structured obligations with Azure OpenAI GPT-4o (strict JSON schema output)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from openai import APIError, BadRequestError

from services.clause_splitter import Clause
from services.obligation_rules import ALLOWED_TYPES

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "obligation_extraction_prompt.txt"

OBLIGATION_SCHEMA = {
    "name": "obligation_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["obligations"],
        "properties": {
            "obligations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["clause_number", "requirement", "obligation_type", "owner_function", "severity",
                                 "citation", "confidence_score", "target_system"],
                    "properties": {
                        "clause_number": {"type": "string"},
                        "requirement": {"type": "string"},
                        "obligation_type": {"type": "string", "enum": ALLOWED_TYPES},
                        "owner_function": {"type": "string"},
                        "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                        "citation": {"type": "string"},
                        "confidence_score": {"type": "number"},
                        "target_system": {"type": "string"},
                    },
                },
            }
        },
    },
}


class ExtractionLLMError(Exception):
    pass


@dataclass
class ExtractedObligation:
    clause_number: str
    requirement: str
    obligation_type: str
    owner_function: str
    severity: str
    citation: str
    confidence_score: float
    target_system: str = ""


@dataclass
class ClauseExtraction:
    clause: Clause
    obligations: list[ExtractedObligation] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


@dataclass
class DocumentContext:
    regulator: str
    title: str
    doc_code: str


class LLMExtractor:
    def __init__(self, client, deployment: str, max_completion_tokens: int = 2000, prompt_path: Path = PROMPT_PATH):
        self.client = client
        self.deployment = deployment
        self.max_tokens = max_completion_tokens
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    async def extract(self, clause: Clause, ctx: DocumentContext) -> ClauseExtraction:
        result = ClauseExtraction(clause=clause)
        user = (
            f"Regulator: {ctx.regulator}\nDocument: {ctx.title} ({ctx.doc_code})\n"
            f"Section heading: {clause.heading or 'n/a'}\nClause number: {clause.clause_number}\n"
            f"Clause text:\n\"\"\"\n{clause.text}\n\"\"\""
        )
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user}]

        for attempt in (1, 2):  # one retry for malformed / truncated JSON
            try:
                resp = await self.client.chat.completions.create(
                    model=self.deployment,
                    messages=messages,
                    temperature=0,
                    max_tokens=self.max_tokens,
                    response_format={"type": "json_schema", "json_schema": OBLIGATION_SCHEMA},
                )
            except BadRequestError as exc:  # content filter, context length: retrying will not help
                result.error = f"bad_request: {exc.message}"[:500]
                return result
            except APIError as exc:
                result.error = f"api_error: {exc}"[:500]
                return result

            if resp.usage:
                result.prompt_tokens += resp.usage.prompt_tokens
                result.completion_tokens += resp.usage.completion_tokens
            choice = resp.choices[0]
            try:
                payload = json.loads(choice.message.content or "")
                result.obligations = [self._coerce(o, clause) for o in payload.get("obligations", [])]
                return result
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                log.warning("Invalid JSON from LLM", extra={"clause": clause.clause_number, "attempt": attempt,
                                                             "finish_reason": choice.finish_reason})
                result.error = f"invalid_json: {exc}"[:500]
        return result

    @staticmethod
    def _coerce(raw: dict, clause: Clause) -> ExtractedObligation:
        return ExtractedObligation(
            clause_number=(raw.get("clause_number") or clause.clause_number).strip()[:100],
            requirement=(raw.get("requirement") or "").strip(),
            obligation_type=raw.get("obligation_type") or "Other",
            owner_function=raw.get("owner_function") or "",
            severity=raw.get("severity") or "LOW",
            citation=(raw.get("citation") or "").strip(),
            confidence_score=float(raw.get("confidence_score") or 0.0),
            target_system=(raw.get("target_system") or "").strip()[:100],
        )
