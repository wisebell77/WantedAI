"""서류 심사 페르소나 — 자소서 초안을 채점표로 읽는다.

근하 님 커버 판정(역량이 '드러났나')과 달리, 여기서는 심사자 관점에서
'설득되나(구체적 행동·결과가 있나)'를 보고 고칠 방향을 준다.
원칙: 자소서·경험에 없는 내용을 지어내지 않는다. 근거 경험이 없으면 action='prepare'.
"""
from __future__ import annotations

import re

from . import llm
from .grounding import find_sentence, verify_quote

STATUS_SCORE = {"strong": 1.0, "weak": 0.5, "missing": 0.0}
_ACTION = re.compile(r"(제가|저는|직접|담당|주도|구현|개발|설계|분석|개선|작성|운영)")
_RESULT = re.compile(r"(\d|결과|성과|개선|단축|증가|감소|달성|수상|배포)")


def _action(status: str, user_quote: str, llm_action: str = "") -> str:
    """판정과 할 일이 모순되지 않게 코드로 정한다(LLM이 'missing인데 keep'을 낸 사례 대응)."""
    if status == "strong":
        return "keep"
    if status == "missing":
        return "insert" if user_quote else "prepare"
    return "prepare" if (llm_action == "prepare" and not user_quote) else "revise"


def _heuristic(rubric: dict, letter: str, experiences: list[str]) -> list[dict]:
    out = []
    for it in rubric["items"]:
        sent = find_sentence(letter, it["keywords"])
        if sent and _ACTION.search(sent) and _RESULT.search(sent):
            status, fb = "strong", "행동과 결과가 함께 드러납니다."
        elif sent:
            status, fb = "weak", "언급은 있지만 본인이 한 일이나 결과가 흐립니다. 맡은 역할과 수치를 더해 보세요."
        else:
            status, fb = "missing", "자소서에서 이 항목의 근거를 찾지 못했습니다."
        user_quote = ""
        if status != "strong":
            user_quote = next((e for e in experiences
                               if find_sentence(e, it["keywords"])), "")
        action = _action(status, user_quote)
        if action == "insert":
            fb += " 입력한 경험 중 관련 내용이 있으니 자소서에 옮겨 보세요."
        elif action == "prepare":
            fb += " 입력한 경험에도 근거가 없어 '준비 필요' 항목으로 둡니다."
        elif user_quote:
            fb += " 입력한 경험 중 보강에 쓸 내용이 있습니다."
        out.append({"status": status, "letter_quote": sent, "user_quote": user_quote,
                    "feedback": fb, "suggestion": "", "action": action})
    return out


_SYSTEM = (
    "너는 {persona} 이다. 채점표 항목별로 자소서를 심사한다. "
    "letter_quote 는 자소서에서, user_quote 는 경험 목록에서 글자 그대로 복사한다(없으면 빈 문자열). "
    "status 는 자소서만 보고 판정한다. 경험 목록에만 있고 자소서에 없으면 missing 이다. "
    "status 기준: strong=본인 행동과 결과가 구체적, weak=언급만 있음, missing=자소서에 근거 없음. "
    "지원자는 신입이다. 수업·과제·학회·동아리·공모전 경험도 실무와 같은 근거로 인정하고, 실무가 아니라는 이유로 낮추지 않는다. "
    "자소서·경험에 없는 기술·수치를 사실처럼 쓰지 않는다. 필요하면 '(해당 경험이 있다면)'처럼 조건을 단다. "
    "feedback 은 80자 이내, suggestion 은 100자 이내. "
    "형식: {{\"items\":[{{\"id\":\"r1\",\"status\":\"strong|weak|missing\",\"letter_quote\":\"\","
    "\"user_quote\":\"\",\"feedback\":\"심사자 관점 1~2문장\",\"suggestion\":\"고쳐 쓸 방향 또는 예시 문장\","
    "\"action\":\"keep|revise|insert|prepare\"}}]}}"
)


def _llm(rubric: dict, letter: str, experiences: list[str]) -> list[dict] | None:
    res = llm.chat_json(_SYSTEM.format(persona=rubric["persona"]["name"]), {
        "rubric": [{k: it[k] for k in ("id", "label", "jd_quote", "kind")} for it in rubric["items"]],
        "cover_letter": letter, "experiences": experiences},
        label=f"서류심사 {rubric['posting'].get('corp', '')}")
    if not res:
        return None
    by_id = {r.get("id"): r for r in res.get("items", [])}
    out = []
    exp_text = "\n".join(experiences)
    for it in rubric["items"]:
        r = by_id.get(it["id"], {})
        lq, uq = r.get("letter_quote", ""), r.get("user_quote", "")
        status = r.get("status", "missing")
        if lq and not verify_quote(lq, letter):      # 자소서에 없는 인용 → 근거로 인정 안 함
            lq, status = "", "missing"
        if uq and not verify_quote(uq, exp_text):
            uq = ""
        if status not in STATUS_SCORE or (status != "missing" and not lq):
            status = "missing"  # 자소서 인용 없이 충분/약함 판정 불가
        action = _action(status, uq, r.get("action", ""))
        out.append({"status": status,
                     "letter_quote": lq, "user_quote": uq,
                     "feedback": r.get("feedback", ""), "suggestion": r.get("suggestion", ""),
                     "action": action})
    return out


def review_letter(rubric: dict, letter: str, experiences: list[str] | None = None,
                  use_llm: bool = True) -> dict:
    experiences = experiences or []
    rows = (_llm(rubric, letter, experiences) if use_llm and llm.available() else None)
    source = "llm" if rows else "heuristic"
    rows = rows or _heuristic(rubric, letter, experiences)

    items, score = [], 0.0
    for it, r in zip(rubric["items"], rows):
        score += it["weight"] * STATUS_SCORE[r["status"]]
        items.append({"id": it["id"], "label": it["label"], "kind": it["kind"],
                      "jd_quote": it["jd_quote"], "market": it.get("market"), **r})
    weakest = [x["id"] for x in sorted(
        items, key=lambda x: (STATUS_SCORE[x["status"]],
                              -next(i["weight"] for i in rubric["items"] if i["id"] == x["id"])))]
    counts = {s: sum(x["status"] == s for x in items) for s in STATUS_SCORE}
    return {"rubric_id": rubric["rubric_id"], "reviewer": rubric["persona"]["name"],
            "generated_by": source,
            "summary": {**counts, "coverage_score": round(score * 100),
                        "note": "채점표 가중 반영도이며 합격 가능성이 아닙니다."},
            "items": items, "weakest": weakest}
