"""Agent 3 routes, mounted by main.py."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .service import Agent3Service

router = APIRouter(prefix="/api/mapping", tags=["Agent 3 - Policy & Control Mapping"])


@lru_cache
def get_service() -> Agent3Service:
    return Agent3Service()


def _svc() -> Agent3Service:
    import providers  # composition root (lets tests / demos swap the LLM client)

    return providers.agent3_service()


class ObligationIds(BaseModel):
    obligation_ids: list[int]


class ReviewUpdate(BaseModel):
    review_status: Literal["PROPOSED", "CONFIRMED", "REJECTED"]


@router.post("/ingest")
async def ingest_enterprise_repository(svc: Agent3Service = Depends(_svc)):
    """Re-index policies, SOPs and the control/system registers. Unchanged files are skipped."""
    return await svc.ingest()


@router.post("/map/pending")
async def map_pending(limit: int | None = None, svc: Agent3Service = Depends(_svc)):
    return await svc.map_pending(limit)


@router.post("/map/document/{doc_code}")
async def map_document(doc_code: str, svc: Agent3Service = Depends(_svc)):
    return await svc.map_document(doc_code)


@router.post("/map/obligations")
async def map_obligations(body: ObligationIds, svc: Agent3Service = Depends(_svc)):
    return await svc.map_obligations(body.obligation_ids)


@router.get("/impact/{doc_code}")
async def impact(doc_code: str, svc: Agent3Service = Depends(_svc)):
    """Policies, controls and systems impacted by each obligation of a regulatory document."""
    return await svc.impact(doc_code)


@router.patch("/mappings/{mapping_id}")
async def review_mapping(mapping_id: int, body: ReviewUpdate, svc: Agent3Service = Depends(_svc)):
    if not await svc.set_review(mapping_id, body.review_status):
        raise HTTPException(404, "Mapping not found")
    return {"id": mapping_id, "review_status": body.review_status}
