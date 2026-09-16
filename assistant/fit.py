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

from typing import Optional, Union

from .coverage import judge_coverage
from .llm import LLMClient
from .models import EssayDraft, Posting


def estimate_fit(
    posting: Posting,
    experience: Union[str, EssayDraft],
    client: Optional[LLMClient] = None,
) -> float:
    """사용자 전체 경험이 이 공고 요구 역량과 얼마나 겹치는지 (0~1).

    coverage 와 동일한 판정을 '자소서 초안'이 아닌 '전체 경험'에 대해 수행한다.
    partial 은 0.5로 부분 인정, 중요도로 가중한다.
    """
    if isinstance(experience, str):
        experience = EssayDraft.from_text(posting.id, experience)

    results = judge_coverage(posting, experience, client)
    total = sum(r.competency.importance for r in results)
    if total == 0:
        return 0.0
    got = sum(r.competency.importance * r.credit for r in results)
    return round(got / total, 3)


def apply_fit(
    postings: list[Posting],
    experience: Union[str, EssayDraft],
    client: Optional[LLMClient] = None,
) -> list[Posting]:
    """여러 공고에 추정 fit_score 를 채워 넣는다(제자리 수정 후 반환)."""
    for p in postings:
        p.fit_score = estimate_fit(p, experience, client)
    return postings
