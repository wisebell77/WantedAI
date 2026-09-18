"""AI 비서(실행 레이어) 핵심 엔진.

파이프라인:
    공고(요구 역량) + 자소서 초안 + 마감일
      -> judge_coverage : 역량별 커버 판정 (①)
      -> PostingAnalysis : 커버율/격차/마감 계산 (②)
      -> make_nudge      : 넛지 문구 + 오늘의 목표 (③-b)
      -> rank            : 여러 공고 우선순위 (③-a)
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .briefing import daily_briefing, render_briefing
from .coverage import judge_coverage
from .fit import FitResult, apply_fit, estimate_fit, fit_detail
from .llm import (
    LLMClient,
    get_default_client,
    llm_stats_summary,
    reset_llm_stats,
)
from .models import (
    Competency,
    CoverageResult,
    CoverageStatus,
    EssayDraft,
    EssaySection,
    Posting,
    PostingAnalysis,
)
from .nudge import make_nudge
from .scheduler import PriorityItem, priority_score, rank, urgency
from .tracker import ApplicationTracker, DraftRef, Snapshot

__all__ = [
    "Competency",
    "Posting",
    "EssayDraft",
    "EssaySection",
    "CoverageResult",
    "CoverageStatus",
    "PostingAnalysis",
    "judge_coverage",
    "estimate_fit",
    "fit_detail",
    "FitResult",
    "apply_fit",
    "make_nudge",
    "daily_briefing",
    "render_briefing",
    "rank",
    "priority_score",
    "urgency",
    "PriorityItem",
    "ApplicationTracker",
    "DraftRef",
    "Snapshot",
    "LLMClient",
    "get_default_client",
    "llm_stats_summary",
    "reset_llm_stats",
    "analyze",
]


def analyze(
    posting: Posting,
    essay: EssayDraft,
    client: Optional[LLMClient] = None,
    as_of: Optional[date] = None,
) -> PostingAnalysis:
    """공고+자소서를 받아 커버 판정까지 끝난 분석 객체를 돌려주는 진입점."""
    results = judge_coverage(posting, essay, client)
    return PostingAnalysis(posting=posting, results=results, as_of=as_of or date.today())
