"""FastAPI dependency wiring. Implementations come from providers.py (the composition root)."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

import providers
from agents.factory import build_extraction_agent, build_gap_agent, build_impact_agent, build_monitoring_agent
from agents.gap_assessment_agent import GapAssessmentAgent
from agents.impact_assessment_agent import ImpactAssessmentAgent
from agents.obligation_extraction_agent import ObligationExtractionAgent
from agents.pipeline import DocumentPipeline, get_pipeline
from agents.regulatory_monitoring_agent import RegulatoryMonitoringAgent
from database import get_session
from settings import Settings, get_settings


def get_llm_client():
    return providers.llm_client()


def get_agent3_service():
    return providers.agent3_service()


def get_pipeline_dep() -> DocumentPipeline:
    return get_pipeline()


def get_extraction_agent(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    client=Depends(get_llm_client),
) -> ObligationExtractionAgent:
    return build_extraction_agent(session, settings, client)


def get_monitoring_agent(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RegulatoryMonitoringAgent:
    return build_monitoring_agent(session, settings)


def get_gap_agent(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    client=Depends(get_llm_client),
) -> GapAssessmentAgent:
    return build_gap_agent(session, settings, client)


def get_impact_agent(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    client=Depends(get_llm_client),
) -> ImpactAssessmentAgent:
    return build_impact_agent(session, settings, client)
