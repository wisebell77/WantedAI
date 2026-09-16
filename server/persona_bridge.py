"""Small JSON bridge to the persona package for the video interview API."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from persona import InterviewSession, build_rubric, llm
from persona.data import load_roles
from persona.grounding import verify_quote


def build_for_posting(posting):
    docs = [doc for doc in load_roles(tier=None, min_len=0) if doc.url == posting["sourceUrl"]]
    index = int(posting.get("personaRoleIndex", 0))
    if index >= len(docs):
        raise ValueError("PERSONA_POSTING_NOT_FOUND")
    doc = docs[index]
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
        else:
            raise ValueError("INVALID_PERSONA_ACTION")
    if llm_log.getvalue():
        print(llm_log.getvalue(), file=sys.stderr, end="")
    if "LLM 호출 실패" in llm_log.getvalue() and request["action"] == "evaluate":
        result["modelUsed"] = "rule-based"
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
