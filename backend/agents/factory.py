"""Builds agents with their dependencies for a given DB session."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

import providers
from agents.gap_assessment_agent import GapAssessmentAgent
from agents.impact_assessment_agent import ImpactAssessmentAgent
from agents.obligation_extraction_agent import ObligationExtractionAgent
from agents.regulatory_monitoring_agent import RegulatoryMonitoringAgent
from repositories import (AuditRepository, DocumentRepository, EmbeddingCacheRepository, GapRepository,
                          ImpactRepository, MappingRepository, ObligationRepository, RemediationRepository)
from services.clause_splitter import ClauseSplitter
from services.embedding_service import EmbeddingService
from services.gap_analyzer import GapAnalyzer
from services.impact_analysis_service import ImpactAnalysisService
from services.llm_change_analyzer import ChangeAnalyzer
from services.llm_extractor import LLMExtractor
from settings import Settings


def build_extraction_agent(session: AsyncSession, settings: Settings, client=None) -> ObligationExtractionAgent:
    client = client or providers.llm_client()
    return ObligationExtractionAgent(
        session=session,
        documents=DocumentRepository(session),
        obligations=ObligationRepository(session),
        audit=AuditRepository(session),
        blob=providers.blob_service(),
        parsers=providers.parser_factory(),
        splitter=ClauseSplitter(max_clause_chars=settings.max_clause_chars),
        extractor=LLMExtractor(client, settings.azure_openai_deployment, settings.max_completion_tokens),
        embedder=EmbeddingService(client, settings.azure_openai_embedding_deployment, EmbeddingCacheRepository(session)),
        settings=settings,
    )


def build_monitoring_agent(session: AsyncSession, settings: Settings) -> RegulatoryMonitoringAgent:
    return RegulatoryMonitoringAgent(
        session=session,
        documents=DocumentRepository(session),
        audit=AuditRepository(session),
        blob=providers.blob_service(),
        fetcher=providers.source_fetcher(),
        parsers=providers.parser_factory(),
        settings=settings,
    )


def build_gap_agent(session: AsyncSession, settings: Settings, client=None) -> GapAssessmentAgent:
    client = client or providers.llm_client()
    return GapAssessmentAgent(
        session=session,
        documents=DocumentRepository(session),
        obligations=ObligationRepository(session),
        mappings=MappingRepository(session),
        gaps=GapRepository(session),
        audit=AuditRepository(session),
        analyzer=GapAnalyzer(client, settings),
        settings=settings,
    )


def build_impact_agent(session: AsyncSession, settings: Settings, client=None) -> ImpactAssessmentAgent:
    client = client or providers.llm_client()
    return ImpactAssessmentAgent(
        session=session,
        documents=DocumentRepository(session),
        obligations=ObligationRepository(session),
        mappings=MappingRepository(session),
        gaps=GapRepository(session),
        impacts=ImpactRepository(session),
        remediation=RemediationRepository(session),
        audit=AuditRepository(session),
        service=ImpactAnalysisService(ChangeAnalyzer(client, settings), settings),
        settings=settings,
    )
