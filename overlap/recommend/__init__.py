"""대조 엔진 — 직무 × 역량 행렬, 근거 인덱스, 정방향·역방향 매칭."""

from .evidence import EvidenceIndex, MarketSignal, Quote, RelatedPosting, Source
from .matrix import JobMatrix, JobProfile
from .scorer import Evidence, Gap, GapReport, JobMatch, Recommender, Subdivision

__all__ = ["JobMatrix", "JobProfile", "Recommender", "JobMatch",
           "GapReport", "Evidence", "EvidenceIndex", "Quote", "Source",
           "MarketSignal", "RelatedPosting", "Subdivision", "Gap"]
