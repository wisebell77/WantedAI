"""텍스트 모의면접 — 공고 페르소나가 채점표로 묻고, 답변을 채점하고, 약하면 꼬리질문.

승민 님 화상면접과의 분담: 이 모듈은 '면접의 두뇌'(질문 생성·내용 평가·동적 꼬리질문)만 맡는다.
녹화·전사·전달 지표는 화상면접 쪽. 텍스트 모드는 같은 두뇌를 카메라 없이 쓰는 것.
서류 심사 결과를 넘기면 가장 약했던 항목부터 묻는다(서류 → 면접 연결).
"""
from __future__ import annotations

import re

from . import llm
from .grounding import find_sentence, verify_quote

_ACTION = re.compile(r"(제가|저는|직접|담당|주도|맡)")
_RESULT = re.compile(r"(\d|결과|성과|개선|단축|증가|감소|달성|배웠|회고)")

_Q_SYSTEM = ("너는 {name}다. {prompt} 아래 채점 항목 하나를 확인하는 면접 질문을 한 문장으로 만든다. "
             "공고 구절을 자연스럽게 녹이고, 경험을 묻는 행동 질문으로 쓴다. "
             "이전 서류 심사 피드백이 있으면 그 빈틈을 겨냥한다. "
             "지원자는 신입이다. 자소서·피드백에 없는 경험을 이미 한 것처럼 가정하지 않는다. "
             "한 번에 한 가지만 묻고 70자 이내로 쓴다. 형식: {{\"question\":\"...\"}}")
_E_SYSTEM = ("너는 {name}다. 지원자 답변을 채점 항목 하나에 대해 0~3점으로 평가한다. "
             "3=본인 행동·판단·결과가 구체적, 2=행동은 있으나 결과나 근거가 약함, 1=언급만, 0=무관. "
             "지원자는 신입이다. 수업·과제·학회·동아리·공모전 경험도 실무와 같게 인정하고, 실무가 아니라는 이유로 감점하지 않는다. "
             "evidence 는 답변에서 글자 그대로 복사한다. 점수가 2 미만이면 빠진 부분을 겨냥한 꼬리질문을 만든다. "
             "feedback 은 80자 이내, followup 은 한 가지만 묻는 60자 이내 질문. "
             "형식: {{\"score\":0,\"evidence\":\"\",\"feedback\":\"1~2문장\",\"followup\":\"\"}}")


class InterviewSession:
    def __init__(self, rubric: dict, review: dict | None = None, max_questions: int = 3,
                 use_llm: bool = True):
        self.rubric = rubric
        self.persona = rubric["persona"]
        self.review = {x["id"]: x for x in (review or {}).get("items", [])}
        self.use_llm = use_llm and llm.available()
        items = {it["id"]: it for it in rubric["items"]}
        order = (review or {}).get("weakest") or [it["id"] for it in
                                                  sorted(rubric["items"], key=lambda x: -x["weight"])]
        self.queue = [items[i] for i in order][:max_questions]
        self.current: dict | None = None
        self.in_followup = False
        self.answers: list[str] = []
        self.log: list[dict] = []

    # ---- 질문 ----
    def next_question(self) -> dict | None:
        if not self.queue:
            return None
        self.current, self.in_followup, self.answers = self.queue.pop(0), False, []
        it = self.current
        q = None
        if self.use_llm:
            res = llm.chat_json(_Q_SYSTEM.format(name=self.persona["name"], prompt=self.persona["system_prompt"]),
                                {"item": {k: it[k] for k in ("label", "jd_quote", "kind")},
                                 "doc_review": self.review.get(it["id"], {}).get("feedback", "")},
                                fast=True, label="면접 질문")
            q = (res or {}).get("question")
        if not q:
            q = f"공고에 '{it['jd_quote']}'라는 내용이 있습니다. 이와 관련해 직접 해 본 경험을 말씀해 주세요."
            if self.review.get(it["id"], {}).get("status") in ("weak", "missing"):
                q += " 자소서에서는 이 부분이 잘 드러나지 않아 여쭙습니다."
        turn = {"item_id": it["id"], "label": it["label"], "jd_quote": it["jd_quote"],
                "question": q, "type": "main"}
        self.log.append(turn)
        return turn

    # ---- 답변 평가 ----
    def _evaluate(self, answer: str) -> dict:
        it = self.current
        if self.use_llm:
            res = llm.chat_json(_E_SYSTEM.format(name=self.persona["name"]),
                                {"item": {k: it[k] for k in ("label", "jd_quote", "followup")},
                                 "answer": answer}, label="답변 채점")
            if res and isinstance(res.get("score"), (int, float)):
                ev = res.get("evidence", "")
                score = int(res["score"])
                if ev and not verify_quote(ev, answer):
                    ev, score = "", min(score, 1)  # 근거 인용이 가짜면 점수를 믿지 않는다
                return {"score": max(0, min(3, score)), "evidence": ev,
                        "feedback": res.get("feedback", ""), "followup": res.get("followup", "")}
        ev = find_sentence(answer, it["keywords"])
        score = sum([bool(ev), bool(_ACTION.search(answer)), bool(_RESULT.search(answer))])
        missing = [n for n, ok in (("항목과 연결되는 내용", ev), ("본인이 한 행동", _ACTION.search(answer)),
                                   ("결과나 배운 점", _RESULT.search(answer))) if not ok]
        fb = "구체적입니다." if not missing else f"{', '.join(missing)}이(가) 부족합니다."
        return {"score": score, "evidence": ev, "feedback": fb, "followup": it["followup"]}

    def answer(self, text: str) -> dict:
        if not self.current:
            raise RuntimeError("next_question() 을 먼저 호출하세요.")
        self.answers.append(text)
        result = self._evaluate("\n".join(self.answers))  # 꼬리질문 답은 최초 답과 합쳐 재평가
        result["item_id"] = self.current["id"]
        if result["score"] < 2 and not self.in_followup and result.get("followup"):
            self.in_followup = True
            result["next"] = {"item_id": self.current["id"], "question": result["followup"],
                              "type": "followup"}
        else:
            result["next"] = None
            result["followup"] = ""
        self.log.append({"type": "answer", "text": text, **result})
        return result

    def report(self) -> dict:
        finals = {}
        for row in self.log:
            if row["type"] == "answer":
                finals[row["item_id"]] = row
        return {"rubric_id": self.rubric["rubric_id"], "interviewer": self.persona["name"],
                "items": [{"item_id": k, "score": v["score"], "evidence": v["evidence"],
                           "feedback": v["feedback"]} for k, v in finals.items()],
                "note": "채점표 기준 연습용 피드백이며 실제 면접 결과를 예측하지 않습니다.",
                "log": self.log}
