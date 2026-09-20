"""Small JSON bridge to the persona package for the video interview API."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from persona import InterviewSession, build_rubric, llm, review_letter
from persona.data import RoleDoc, load_roles
from persona.grounding import verify_quote


def build_for_posting(posting):
    url = (posting.get("sourceUrl") or "").strip()
    docs = [doc for doc in load_roles(tier=None, min_len=0) if url and doc.url == url]
    index = int(posting.get("personaRoleIndex", 0))
    doc = docs[index] if index < len(docs) else _doc_from_text(posting)
    rubric_path = Path(__file__).resolve().parent.parent / "out" / "rubrics" / f"{doc.role_id}.json"
    rubric = None
    if rubric_path.exists():
        saved = json.loads(rubric_path.read_text(encoding="utf-8"))
        if saved.get("posting", {}).get("url") == doc.url and all(
            verify_quote(item.get("jd_quote", ""), doc.text) for item in saved.get("items", [])
        ):
            rubric = saved
    rubric = rubric or build_rubric(doc)
    session = InterviewSession(rubric, max_questions=min(3, len(rubric["items"])))
    questions = []
    while question := session.next_question():
        questions.append(question)
    return {"rubric": rubric, "questions": questions}


def _doc_from_text(posting):
    """사용자가 직접 등록한 공고를 문서로 만든다.

    수집본(roles.json)에 없는 공고다. 루브릭은 항목마다 공고 원문을 인용하고
    verify_quote 로 그 인용이 본문에 실제로 있는지 확인하므로, 붙여 넣은 원문을
    그대로 text 에 넣어야 한다. 요약하거나 다듬으면 인용 검증이 깨진다.
    """
    text = chr(10).join(posting.get("responsibilities") or []).strip()
    if not text:
        raise ValueError("PERSONA_POSTING_NOT_FOUND")
    return RoleDoc(
        role_id=str(posting.get("postingId") or "user"),
        corp=posting.get("companyName") or "",
        post_title=posting.get("postingTitle") or posting.get("positionTitle") or "",
        role=posting.get("positionTitle") or "",
        job=posting.get("jobFamily") or "",
        tier="",
        url=posting.get("sourceUrl") or "",
        techs=list(posting.get("requiredSkills") or []),
        text=text,
    )


def evaluate(rubric, item_id, answer, followup_answer=""):
    session = InterviewSession(rubric, max_questions=1)
    session.current = next((item for item in rubric["items"] if item["id"] == item_id), None)
    if session.current is None:
        raise ValueError("PERSONA_RUBRIC_ITEM_NOT_FOUND")
    session.queue = []
    result = session.answer(answer)
    if followup_answer.strip() and result["next"]:
        result = session.answer(followup_answer)
    return {
        "itemId": result["item_id"],
        "label": session.current["label"],
        "jdQuote": session.current["jd_quote"],
        "score": result["score"],
        "feedback": result["feedback"],
        "answerEvidence": result["evidence"],
        "followupQuestion": result["next"]["question"] if result["next"] else "",
        "note": "공고 기반 연습용 피드백이며 실제 채용 결과를 예측하지 않습니다.",
        "modelUsed": os.getenv("UPSTAGE_COACH_MODEL", "solar-pro4") if llm.available() else "rule-based"
    }


def main():
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(io.StringIO()) as llm_log:
        if request["action"] == "persona":
            result = build_for_posting(request["posting"])
        elif request["action"] == "evaluate":
            result = evaluate(request["rubric"], request["itemId"], request["answer"], request.get("followupAnswer", ""))
        elif request["action"] == "review":
            result = review_letter(request["rubric"], request["letter"], request.get("experiences") or [])
        else:
            raise ValueError("INVALID_PERSONA_ACTION")
    if llm_log.getvalue():
        print(llm_log.getvalue(), file=sys.stderr, end="")
    if "LLM 호출 실패" in llm_log.getvalue() and request["action"] == "evaluate":
        result["modelUsed"] = "rule-based"
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
