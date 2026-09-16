"""오늘 할 일 브리핑 — 여러 공고를 종합한 '한 가지 집중 행동'.

공고별 넛지가 흩어져 있으면 "그래서 오늘 뭐 해?"가 안 보인다.
이 모듈은 우선순위를 종합해 (1) 오늘 집중할 공고 하나 (2) 마감 경보
(3) 그다음 할 것 을 뽑아, 비서의 '오늘의 한마디'를 만든다.
"""

from __future__ import annotations

from typing import Optional

from .llm import LLMClient
from .models import EssayDraft, PostingAnalysis
from .nudge import make_nudge
from .scheduler import PriorityItem, rank


def daily_briefing(
    analyses: list[PostingAnalysis],
    essays: Optional[dict[str, EssayDraft]] = None,
    client: Optional[LLMClient] = None,
) -> dict:
    """오늘 할 일 브리핑을 만든다.

    반환:
      focus      : 오늘 집중할 PriorityItem (없으면 None)
      focus_goal : 그 공고의 오늘 목표 문구 (어느 문항에 무엇을)
      next_up    : 그다음 PriorityItem (없으면 None)
      urgent     : 마감 임박(D-1 이내)인데 미완성인 공고 목록 (경보)
      ranked     : 전체 우선순위
    """
    ranked = rank(analyses)
    # 오늘 '할 일이 있는'(격차>0, 점수>0) 공고만 집중 후보
    actionable = [it for it in ranked if it.score > 0 and it.analysis.gap > 0]
    focus = actionable[0] if actionable else (ranked[0] if ranked else None)
    next_up = actionable[1] if len(actionable) > 1 else None

    # 마감 경보: 오늘~내일 마감인데 아직 다 못 채운 공고
    urgent = [a for a in analyses if 0 <= a.days_left <= 1 and a.coverage_rate < 1.0]
    urgent.sort(key=lambda a: (a.days_left, -a.gap))

    focus_goal = None
    if focus is not None:
        essay = essays.get(focus.analysis.posting.id) if essays else None
        focus_goal = make_nudge(focus.analysis, client, essay).get("today_goal")

    return {
        "focus": focus,
        "focus_goal": focus_goal,
        "next_up": next_up,
        "urgent": urgent,
        "ranked": ranked,
    }


def render_briefing(b: dict) -> str:
    """브리핑 dict 를 사람이 읽는 '오늘 할 일' 텍스트로."""
    lines: list[str] = []

    for a in b["urgent"]:
        lines.append(
            f"🔴 마감 임박: [{a.posting.company}] "
            f"D-{a.days_left} · 커버율 {a.coverage_rate:.0%} — 오늘 안에 마무리 필요"
        )

    focus: Optional[PriorityItem] = b["focus"]
    if focus is None:
        lines.append("담아둔 공고가 없어요. 관심 공고를 담아보세요.")
        return "\n".join(lines)

    a = focus.analysis
    when = "오늘 마감" if a.days_left == 0 else f"D-{a.days_left}"
    lines.append(
        f"🎯 오늘은 [{a.posting.company}]에 집중하세요 "
        f"({when} · 적합도 {(a.posting.fit_score or 0):.0%})."
    )
    if b["focus_goal"]:
        lines.append(f"   → {b['focus_goal']}")

    nxt: Optional[PriorityItem] = b["next_up"]
    if nxt is not None:
        na = nxt.analysis
        lines.append(
            f"   그다음: [{na.posting.company}] D-{na.days_left} "
            f"(적합도 {(na.posting.fit_score or 0):.0%}, 진행 {na.coverage_rate:.0%})"
        )
    return "\n".join(lines)
