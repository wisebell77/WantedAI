"""적합도(fit) 간이 추정기 — Overlap 진단 연동 전까지 쓰는 로컬 대체.

핵심 통찰: fit과 coverage는 '같은 커버 판정 로직'을 서로 다른 입력에 돌린 것이다.
  - coverage(진행도): 이 공고용 '자소서 초안' vs 공고 요구 역량
  - fit(적합도):     사용자 '전체 경험'      vs 공고 요구 역량  ← 초안과 무관

따라서 judge_coverage 를 사용자의 '전체 경험 텍스트'에 대해 돌리고, 그 중요도
가중 커버율을 fit 으로 쓴다. Overlap 이 정식 적합도를 산출하면 그 값으로 교체하면 된다.

주의: 이건 근사값이다. 진짜 적합도는 Overlap 이 사용자 경험을 정규화된 역량 체계로
매핑해 산출한다(요구 수준까지 고려). 여기서는 그 자리를 임시로 채운다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from .coverage import judge_coverage
from .llm import LLMClient
from .models import CoverageStatus, EssayDraft, Posting


@dataclass
class FitResult:
    """적합도 상세 — 정렬용 연속값(score) + 화면용 근거(개수/목록)."""

    score: float                              # 0~1 (우선순위 계산용)
    matched: list[str] = field(default_factory=list)   # 경험과 겹치는 역량
    partial: list[str] = field(default_factory=list)   # 부분적으로 겹침
    missing: list[str] = field(default_factory=list)   # 경험에 없는 역량
    total: int = 0                            # 요구 역량 총개수


def fit_detail(
    posting: Posting,
    experience: Union[str, EssayDraft],
    client: Optional[LLMClient] = None,
) -> FitResult:
    """경험 ↔ 요구역량 겹침을 상세히 판정.

    coverage 와 동일한 판정을 '자소서 초안'이 아닌 '전체 경험'에 대해 수행한다.
    score(정렬용)는 중요도 가중·partial 0.5, 화면엔 matched 개수/목록을 쓴다.
    """
    if isinstance(experience, str):
        experience = EssayDraft.from_text(posting.id, experience)

    results = judge_coverage(posting, experience, client)
    total_w = sum(r.competency.importance for r in results)
    score = 0.0 if total_w == 0 else round(
        sum(r.competency.importance * r.credit for r in results) / total_w, 3
    )
    return FitResult(
        score=score,
        matched=[r.competency.name for r in results if r.status == CoverageStatus.COVERED],
        partial=[r.competency.name for r in results if r.status == CoverageStatus.PARTIAL],
        missing=[r.competency.name for r in results if r.status == CoverageStatus.MISSING],
        total=len(results),
    )


def estimate_fit(
    posting: Posting,
    experience: Union[str, EssayDraft],
    client: Optional[LLMClient] = None,
) -> float:
    """적합도 연속값(0~1)만 필요할 때 (정렬용)."""
    return fit_detail(posting, experience, client).score


def apply_fit(
    postings: list[Posting],
    experience: Union[str, EssayDraft],
    client: Optional[LLMClient] = None,
) -> list[Posting]:
    """여러 공고에 fit_score(정렬용) + fit_matched(표시용)를 채운다(제자리 수정)."""
    for p in postings:
        d = fit_detail(p, experience, client)
        p.fit_score = d.score
        p.fit_matched = d.matched
    return postings
