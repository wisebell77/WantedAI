"""실제 Overlap 공고 데이터로 핵심 엔진 돌려보기.

    python demo_real.py

data/overlap/ 의 실제 A등급 공고를 직무 카테고리별로 로드해, 사용자의 자소서
초안과 대조한다.
- 판정 모드: ANTHROPIC_API_KEY 있으면 LLM, 없으면 휴리스틱
- fit_score/deadline 은 이 번들에 없어 데모용 임시값을 부여한다(하단 주석 참고).
"""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from assistant import EssayDraft, analyze, get_default_client, make_nudge, rank
from assistant.overlap_loader import job_categories, load_postings

# 사용자의 자소서 초안 (분석/데이터 지향 경험 예시)
ESSAY_TEXT = (
    "학회에서 추천시스템 프로젝트를 진행하며 Python과 pandas로 로그 데이터를 "
    "전처리하고, SQL로 사용자 행동 데이터를 추출해 분석했습니다. 결과는 팀원들과 "
    "공유하며 방향을 조정했고, 간단한 시각화 자료도 만들었습니다. Excel로 지표를 "
    "정리한 경험도 있습니다."
)

# 데모용 임시 적합도 (실제 값 아님).
#   실제로는 Overlap이 '사용자 경험 ↔ 직무 요구'를 대조해 직무별 적합도를 산출해 넘겨준다.
#   여기서는 분석/데이터 지향 사용자를 가정하고 카테고리별로 임의 부여했다.
CATEGORY_FIT = {
    "데이터/AI": 0.90,
    "개발/SW": 0.72,
    "경영지원": 0.35,
    "생산/품질": 0.30,
}


def main() -> None:
    client = get_default_client()
    mode = "LLM" if client else "휴리스틱(키 없음)"
    print(f"=== 실제 공고 데이터 · 판정 모드: {mode} ===\n")

    cats = job_categories()
    print("코퍼스 직무 분포:", ", ".join(f"{k} {v}" for k, v in cats.items()), "\n")

    # 카테고리별로 A등급 공고를 조금씩 모아, 적합도(fit)의 영향이 드러나게 한다.
    postings = []
    for category, fit in CATEGORY_FIT.items():
        for p in load_postings(tier="A", job=category, limit=2):
            p.fit_score = fit           # 데모용 임시 적합도
            postings.append(p)

    essay = EssayDraft(posting_id=postings[0].id if postings else "", text=ESSAY_TEXT)
    analyses = [analyze(p, essay, client=client) for p in postings]

    for a in analyses:
        p = a.posting
        print(f"[{p.company}] {p.role[:38]}  (D-{a.days_left}, 적합도 {p.fit_score:.0%})")
        print(f"  요구 역량 {len(a.results)}개 · 커버율 {a.coverage_rate:.0%}")
        covered = [r.competency.name for r in a.results if r.status.value == "covered"]
        if covered:
            print(f"    O 이미 드러남: {', '.join(covered)}")
        note = make_nudge(a, client=client)
        print(f"  💬 {note['nudge']}")
        print(f"  🎯 {note['today_goal']}\n")

    print("=== 오늘의 우선순위 (적합도 × 마감임박도 × 격차) ===")
    for i, item in enumerate(rank(analyses), 1):
        a = item.analysis
        print(f"  {i}. [{a.posting.company}] {a.posting.role[:26]}  "
              f"(점수 {item.score}) — {item.reason}")


if __name__ == "__main__":
    main()
