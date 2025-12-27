"""
Query-Adaptive Frame Selection Services (Epic P12-4)

This module provides enhanced query-adaptive frame selection functionality:
- BatchEmbedder: Batch processing for ~40% faster embedding generation
- DiversityFilter: Prevents selection of near-duplicate frames
- QueryCache: In-memory caching with 5-minute TTL
- QuerySuggester: Smart suggestions based on event type
"""

from app.services.query_adaptive.batch_embedder import BatchEmbedder, get_batch_embedder
from app.services.query_adaptive.diversity_filter import DiversityFilter
from app.services.query_adaptive.query_cache import QueryCache, CachedQueryResult
from app.services.query_adaptive.query_suggester import QuerySuggester

__all__ = [
    "BatchEmbedder",
    "get_batch_embedder",
    "DiversityFilter",
    "QueryCache",
    "CachedQueryResult",
    "QuerySuggester",
]
