"""③-b 넛지 문구 생성.

분석 결과(커버율·격차·마감)를 사람이 읽는 '비서의 한마디'로 바꾼다.
데모의 얼굴이 되는 부분. LLM이 있으면 자연스러운 문장을, 없으면 템플릿을 쓴다.

기획서의 목표 톤:
  "1번 공고 마감 이틀 남았는데, 요구 역량 5개 중 3개만 자소서에 드러나 있어요.
   이 속도면 빠듯하니 오늘은 나머지 2개까지 넣는 걸 목표로 하죠."
"""

from __future__ import annotations

from typing import Optional

from .llm import LLMClient
from .models import CoverageStatus, PostingAnalysis

_SYSTEM = """너는 취업 준비생의 개인 비서다.
자소서 진행 상황 분석 결과를 받아, 오늘 무엇을 어디까지 할지 짚어주는
'비서의 한마디'를 한국어 2~3문장으로 만든다.
- 근거가 되는 수치(마감일, 커버율, 미충족 역량명)를 구체적으로 언급한다.
- 다그치지 않되 실행을 자연스럽게 넛지하는 톤.
- 반드시 JSON으로만 답한다: {"nudge": "...", "today_goal": "..."}"""


def make_nudge(analysis: PostingAnalysis, client: Optional[LLMClient] = None) -> dict:
    """{'nudge': str, 'today_goal': str} 반환."""
    if client is not None:
        try:
            return _nudge_with_llm(analysis, client)
        except Exception:
            pass
    return _nudge_template(analysis)


def _facts(analysis: PostingAnalysis) -> str:
    p = analysis.posting
    d = analysis.days_left
    deadline = "이미 마감" if d < 0 else "오늘 마감" if d == 0 else f"마감까지 {d}일"
    missing = [r.competency.name for r in analysis.missing()]
    partial = [r.competency.name for r in analysis.partial()]
    return (
        f"공고: {p.company} {p.role}\n"
        f"마감: {deadline}\n"
        f"요구 역량 {len(analysis.results)}개 중 커버율 {analysis.coverage_rate:.0%}\n"
        f"미충족(missing): {', '.join(missing) if missing else '없음'}\n"
        f"보완필요(partial): {', '.join(partial) if partial else '없음'}"
    )


def _nudge_with_llm(analysis: PostingAnalysis, client: LLMClient) -> dict:
    data = client.complete_json(_SYSTEM, _facts(analysis))
    return {
        "nudge": data.get("nudge", "").strip(),
        "today_goal": data.get("today_goal", "").strip(),
    }


def _nudge_template(analysis: PostingAnalysis) -> dict:
    p = analysis.posting
    d = analysis.days_left
    total = len(analysis.results)
    covered = sum(1 for r in analysis.results if r.status == CoverageStatus.COVERED)
    missing = [r.competency.name for r in analysis.missing()]
    partial = [r.competency.name for r in analysis.partial()]
    todo = missing + partial

    if d < 0:
        deadline = "마감이 지났어요"
    elif d == 0:
        deadline = "오늘이 마감이에요"
    elif d <= 2:
        deadline = f"마감이 {d}일밖에 안 남았어요"
    else:
        deadline = f"마감까지 {d}일 남았어요"

    nudge = (
        f"{p.company} {p.role} 공고는 {deadline}. "
        f"요구 역량 {total}개 중 {covered}개가 자소서에 드러나 있어요"
        f"(커버율 {analysis.coverage_rate:.0%})."
    )
    if todo:
        focus = ", ".join(todo[:2])
        tail = "까지" if len(todo) <= 2 else " 등을"
        goal = f"오늘은 '{focus}'{tail} 자소서에 녹이는 걸 목표로 해요."
    else:
        goal = "요구 역량은 모두 반영됐어요. 오늘은 전체 흐름을 다듬어 마무리해요."
    return {"nudge": nudge, "today_goal": goal}
