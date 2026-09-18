# AIMETA P=services_package_exports|R=avoid_heavy_test_imports|NR=service_impl|E=-|X=internal|A=-|D=none|S=none|RD=./README.ai
"""Service package exports.

The package is intentionally light during pytest collection so focused unit
tests can import a single service without pulling optional NLP/vector
dependencies into the local test environment.
"""

from __future__ import annotations

import os


if os.getenv("XUANQIONG_TEST_LIGHT_IMPORTS") == "1":
    __all__: list[str] = []
else:
    from .blueprint_service import BlueprintService
    from .consistency_service import (
        ConsistencyCheckResult,
        ConsistencyService,
        ConsistencyViolation,
        ViolationSeverity,
    )
    from .embedding_service import EmbeddingService
    from .enrichment_service import EnrichmentResult, EnrichmentService
    from .finalize_service import FinalizeService
    from .knowledge_retrieval_service import FilteredContext, KnowledgeRetrievalService, RetrievedKnowledge
    from .llm_service import LLMService
    from .vector_store_service import RetrievedChunk, RetrievedSummary, VectorStoreService
    from .vector_store_service_ext import VectorStoreServiceExt

    __all__ = [
        "LLMService",
        "VectorStoreService",
        "VectorStoreServiceExt",
        "EmbeddingService",
        "RetrievedChunk",
        "RetrievedSummary",
        "FinalizeService",
        "ConsistencyService",
        "ConsistencyCheckResult",
        "ConsistencyViolation",
        "ViolationSeverity",
        "KnowledgeRetrievalService",
        "FilteredContext",
        "RetrievedKnowledge",
        "EnrichmentService",
        "EnrichmentResult",
        "BlueprintService",
    ]
