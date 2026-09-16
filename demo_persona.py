"""공고 페르소나 end-to-end 데모: 채점표 → 서류 심사 → 텍스트 면접.

    python demo_persona.py                      # 기본: 뷰웍스 SW개발(A등급)
    python demo_persona.py --role 176555-0      # 다른 공고 (role_id 는 build_rubrics 결과 참고)
    python demo_persona.py --interactive        # 면접 답변을 직접 입력

UPSTAGE_API_KEY 가 .env 에 있으면 LLM, 없으면 규칙 기반으로 돈다.
아래 자소서·경험·답변은 데모용 가상 지원자다.
"""
import argparse

from persona import InterviewSession, build_rubric, get_role, llm, review_letter

LETTER = (
    "저는 학부 캡스톤에서 산업용 카메라 영상 뷰어를 C++로 개발했습니다. "
    "영상 처리 라이브러리를 공부하며 필터 기능을 붙였습니다. "
    "팀 프로젝트에서는 Git으로 협업하며 코드 리뷰 문화를 경험했습니다. "
    "앞으로 영상 장비 SW 분야에서 성장하고 싶습니다."
)
EXPERIENCES = [
    "자료구조 수업에서 C로 해시 테이블을 직접 구현하고 성능을 비교하는 보고서를 작성함",
    "학회에서 OpenCV로 불량 이미지 분류 프로젝트를 진행, 전처리 파이프라인을 맡아 처리 시간을 40% 줄임",
]
ANSWERS = [  # 질문 순서: 서류에서 약했던 항목 순
    "자료구조 수업에서 제가 C로 해시 테이블을 직접 구현했고, 충돌 처리 방식별 탐색 시간을 비교해 보고서로 정리했습니다.",
    "수업에서 배운 적이 있습니다.",  # 일부러 약한 답 → 꼬리질문 유도
    "캡스톤에서 C++로 카메라 뷰어를 만들 때 제가 영상 획득 모듈을 맡았습니다. 프레임 드롭이 심해 "
    "버퍼 구조를 바꿨고, 초당 프레임을 12에서 30으로 올렸습니다.",
]


def line(t=""):
    print(f"\n{'─' * 8} {t}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default="175993-3")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    print(f"LLM 사용: {llm.available()}")
    if llm.available() and not args.interactive:
        print("※ AI 모드는 질문이 매번 달라져 미리 적어둔 답변과 어긋날 수 있습니다. --interactive 로 직접 답해 보세요.")
    doc = get_role(args.role)
    rub = build_rubric(doc)

    line(f"① 채점표 · {rub['persona']['name']} ({rub['generated_by']})")
    for it in rub["items"]:
        m = it["market"]
        mk = f"  · 같은 직무군 A등급 {m['n']}건 중 {m['k']}건이 {m['tech']} 요구" if m else ""
        print(f"[{it['id']}] {it['label']}  (가중 {it['weight']}, {it['kind']}){mk}")
        print(f"      근거: “{it['jd_quote']}”")

    line("② 서류 심사")
    rev = review_letter(rub, LETTER, EXPERIENCES)
    s = rev["summary"]
    print(f"반영도 {s['coverage_score']}점 · 충분 {s['strong']} / 약함 {s['weak']} / 없음 {s['missing']}  ({s['note']})")
    for it in rev["items"]:
        print(f"[{it['id']}] {it['status']:7} {it['action']:7} {it['label']}")
        if it["letter_quote"]:
            print(f"      자소서: “{it['letter_quote']}”")
        if it["user_quote"]:
            print(f"      옮길 경험: “{it['user_quote']}”")
        print(f"      → {it['feedback']} {it['suggestion']}")

    line("③ 텍스트 면접 (서류에서 약했던 항목부터)")
    sess = InterviewSession(rub, rev, max_questions=3)
    answers = iter(ANSWERS)
    while (q := sess.next_question()):
        while q:
            print(f"\n면접관: {q['question']}")
            ans = input("나: ") if args.interactive else next(answers, "잘 모르겠습니다.")
            if not args.interactive:
                print(f"나: {ans}")
            r = sess.answer(ans)
            print(f"   → {r['score']}/3 · {r['feedback']}")
            q = r["next"]

    line("면접 리포트")
    for it in sess.report()["items"]:
        print(f"[{it['item_id']}] {it['score']}/3 {it['feedback']}")


if __name__ == "__main__":
    main()
