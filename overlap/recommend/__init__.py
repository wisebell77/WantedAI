"""대조 엔진 — 직무 × 역량 행렬과 정방향·역방향 매칭."""

from .matrix import JobMatrix, JobProfile
from .scorer import Evidence, GapReport, JobMatch, Recommender

__all__ = ["JobMatrix", "JobProfile", "Recommender", "JobMatch",
           "GapReport", "Evidence"]
