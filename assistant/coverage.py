"""① 역량별 커버 판정.

자소서 초안이 공고의 각 요구 역량을 얼마나 드러내는지 판정한다.
이 부분이 AI 비서의 차별점(작업물 자체에서 진행도를 '추정')이자 구현 난이도 최상 지점.

- LLM 클라이언트가 있으면: 근거 문장까지 뽑아 정밀 판정
- 없으면: 키워드 기반 휴리스틱으로 fallback (키 없이도 데모 가능)
"""

from __future__ import annotations

from typing import Optional

from .llm import LLMClient
from .models import (
    Competency,
    CoverageResult,
    CoverageStatus,
    EssayDraft,
    Posting,
)

_SYSTEM = """너는 취업 자소서 첨삭 보조 엔진이다.
주어진 채용 공고의 '요구 역량 목록'과 사용자의 '자소서 초안'을 비교해,
각 역량이 자소서에 얼마나 드러나는지 판정한다.

반드시 지켜라:
- 판정은 오직 자소서 본문에 실제로 쓰인 내용에만 근거한다. 추측/창작 금지.
- evidence는 자소서에서 그대로 발췌한 문장이어야 한다. 없으면 null.
- status는 covered(충분), partial(언급되나 근거·수준 부족), missing(없음) 중 하나.
- 반드시 아래 JSON 형식으로만 답한다."""

_USER_TEMPLATE = """[요구 역량]
{competencies}

[자소서 — 문항별]
{essay}

위 각 역량에 대해 판정하라. 근거가 나온 '문항 제목'을 section 에 넣어라(없으면 null).
출력 형식:
{{
  "results": [
    {{"name": "역량명", "status": "covered|partial|missing",
      "evidence": "자소서 발췌 문장 또는 null",
      "section": "근거가 나온 문항 제목 또는 null",
      "comment": "수준/보완점 한 줄"}}
  ]
}}"""


def _render_sections(essay: EssayDraft) -> str:
    """자소서를 '문항별' 형태로 렌더 (LLM 입력용)."""
    blocks = []
    for i, s in enumerate(essay.sections, 1):
        if not (s.answer and s.answer.strip()):
            continue
        head = f"[문항 {i}] {s.question}" if s.question else f"[문항 {i}]"
        blocks.append(f"{head}\n답변: {s.answer.strip()}")
    return "\n\n".join(blocks) if blocks else "(작성된 답변 없음)"


def judge_coverage(
    posting: Posting,
    essay: EssayDraft,
    client: Optional[LLMClient] = None,
) -> list[CoverageResult]:
    """공고의 요구 역량 각각에 대해 자소서 커버 여부를 판정."""
    if client is not None:
        try:
            return _judge_with_llm(posting, essay, client)
        except Exception:
            # 호출 실패 시에도 데모가 멈추지 않도록 휴리스틱으로 강등
            pass
    return _judge_heuristic(posting, essay)


def _judge_with_llm(
    posting: Posting, essay: EssayDraft, client: LLMClient
) -> list[CoverageResult]:
    comp_lines = "\n".join(
        f"- {c.name}"
        + (f" (요구수준: {c.required_level})" if c.required_level else "")
        for c in posting.required_competencies
    )
    user = _USER_TEMPLATE.format(competencies=comp_lines, essay=_render_sections(essay))
    data = client.complete_json(_SYSTEM, user)

    by_name = {c.name: c for c in posting.required_competencies}
    results: list[CoverageResult] = []
    for row in data.get("results", []):
        comp = by_name.get(row.get("name"))
        if comp is None:
            continue
        results.append(
            CoverageResult(
                competency=comp,
                status=_parse_status(row.get("status")),
                evidence=row.get("evidence") or None,
                section=row.get("section") or None,
                comment=row.get("comment", ""),
            )
        )
    # 모델이 빠뜨린 역량은 missing으로 보정
    seen = {r.competency.name for r in results}
    for comp in posting.required_competencies:
        if comp.name not in seen:
            results.append(CoverageResult(comp, CoverageStatus.MISSING))
    return results


def _judge_heuristic(posting: Posting, essay: EssayDraft) -> list[CoverageResult]:
    """LLM 없이 쓰는 단순 키워드 매칭. 정밀하진 않지만 파이프라인 검증용."""
    # 문항별로 답변을 들고 있어 근거가 '어느 문항'에서 나왔는지 표시할 수 있다.
    sections = [(s.question, s.answer) for s in essay.sections if s.answer and s.answer.strip()]
    if not sections:  # from_text 등으로 섹션이 비면 전체 텍스트를 한 덩어리로
        sections = [("", essay.text)]

    results: list[CoverageResult] = []
    for comp in posting.required_competencies:
        tokens = [t for t in _keywords(comp) if t]
        hit_token = hit_section = evidence = None
        for question, answer in sections:
            found = [t for t in tokens if t.lower() in answer.lower()]
            if found:
                hit_token, hit_section = found[0], question
                evidence = _find_sentence(answer, found[0])
                break

        if hit_token is None:
            status = CoverageStatus.MISSING
        else:
            # 토큰이 전부 어딘가에 있으면 covered, 일부면 partial
            all_text = essay.text.lower()
            status = (CoverageStatus.COVERED
                      if all(t.lower() in all_text for t in tokens)
                      else CoverageStatus.PARTIAL)
        results.append(
            CoverageResult(
                competency=comp,
                status=status,
                evidence=evidence,
                section=hit_section or None,
                comment="(휴리스틱 판정 — 실제 LLM 판정으로 교체 권장)",
            )
        )
    return results


def _keywords(comp: Competency) -> list[str]:
    """역량명을 매칭용 토큰으로 분해 (간이)."""
    raw = comp.name.replace("/", " ").replace(",", " ")
    return [w.strip() for w in raw.split() if len(w.strip()) >= 2]


def _find_sentence(text: str, needle: str) -> Optional[str]:
    for sep in ("\n", "."):
        for part in text.split(sep):
            if needle.lower() in part.lower():
                return part.strip()
    return None


def _parse_status(value: Optional[str]) -> CoverageStatus:
    try:
        return CoverageStatus(str(value).strip().lower())
    except ValueError:
        return CoverageStatus.MISSING
