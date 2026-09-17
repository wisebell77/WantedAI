"""③-a 우선순위 산정.

여러 공고를 동시에 굴릴 때 "오늘 뭐부터?"를 정한다.
사용자 기획의 아이디어(격차 × 마감임박도 × 커버율)를 구현하되,
'거의 다 됐고 마감 임박'인 공고를 놓치지 않도록 격차·마감을 중심으로 잡았다.
가중치는 상수로 빼서 팀에서 쉽게 튜닝할 수 있게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import PostingAnalysis


def urgency(days_left: int) -> float:
    """마감임박도 (0~1). 지났거나 임박할수록 1에 가깝다."""
    if days_left <= 0:
        return 1.0
    if days_left <= 1:
        return 0.95
    if days_left <= 3:
        return 0.8
    if days_left <= 7:
        return 0.5
    if days_left <= 14:
        return 0.3
    return 0.15


# 각 신호의 영향력(지수). 팀에서 튜닝하는 지점.
#   지수 1.0 = 그대로 반영, 0.0 = 해당 신호 무시, >1 = 더 강하게 반영.
#   fit 을 gap 보다 높게 둬, '내 경험과 잘 맞는 직무'에 더 집중하도록 했다.
PRIORITY_EMPHASIS = {
    "gap": 1.0,       # 아직 채울 게 남았나 (오늘 할 일의 존재)
    "urgency": 1.0,   # 마감 임박도
    "fit": 1.5,       # 내 경험과의 적합도 — 격차보다 조금 더 강하게
}


@dataclass
class PriorityItem:
    analysis: PostingAnalysis
    score: float
    reason: str


def priority_score(analysis: PostingAnalysis) -> float:
    """우선순위 점수 = 격차 × 마감임박도 × 적합도.

    - gap    : 아직 채울 게 남아 있을수록 ↑ (다 됐으면 오늘 할 일이 없다)
    - urgency: 마감이 가까울수록 ↑
    - fit    : 내 경험에 적합한 직무일수록 ↑  → 격차만 큰 '안 맞는 공고'가
               위로 올라오는 것을 막고, 적합한 직무에 집중하게 한다.
    적합도(fit)가 없으면(미연동) 중립 1.0으로 둬 기존 동작을 해치지 않는다.
    """
    g = analysis.gap
    u = urgency(analysis.days_left)
    f = analysis.posting.fit_score
    f = 1.0 if f is None else max(0.0, min(1.0, f))

    e = PRIORITY_EMPHASIS
    score = (g ** e["gap"]) * (u ** e["urgency"]) * (f ** e["fit"])
    return round(score, 4)


def rank(analyses: list[PostingAnalysis]) -> list[PriorityItem]:
    """공고들을 우선순위 높은 순으로 정렬."""
    items = []
    for a in analyses:
        d = a.days_left
        deadline_phrase = (
            "마감 지남" if d < 0 else "오늘 마감" if d == 0 else f"마감 D-{d}"
        )
        total = len(a.results)
        # 적합도는 '겹침 개수'로(합격확률 오해 방지), 진행도는 그대로 %로
        matched = a.posting.fit_matched
        overlap_phrase = f"겹침 {len(matched)}/{total} · " if matched is not None else ""
        reason = (
            f"{deadline_phrase} · {overlap_phrase}진행 {a.coverage_rate:.0%} · "
            f"미충족 {len(a.missing())}개"
        )
        items.append(PriorityItem(a, priority_score(a), reason))
    items.sort(key=lambda it: it.score, reverse=True)
    return items
