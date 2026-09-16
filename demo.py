"""핵심 엔진 데모.

    python demo.py

- ANTHROPIC_API_KEY 가 있으면 실제 LLM 판정/넛지로 동작
- 없으면 휴리스틱 fallback 으로 동작 (비용 0, 파이프라인 검증용)

* 공고의 '요구 역량'은 Overlap 파트가 산출하는 데이터라고 가정하고,
  여기서는 샘플 역량을 직접 넣었다. (Overlap 스키마 확정 시 이 부분만 연결)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

# Windows 콘솔(cp949)에서도 한글/이모지 출력이 깨지지 않도록 UTF-8 강제
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from assistant import (
    Competency,
    EssayDraft,
    Posting,
    analyze,
    get_default_client,
    make_nudge,
    rank,
)

TODAY = date.today()


def sample_postings() -> list[Posting]:
    return [
        Posting(
            id="P1",
            company="A사",
            role="데이터 분석가",
            deadline=TODAY + timedelta(days=2),
            fit_score=0.85,  # (Overlap 산출 가정) 사용자 경험과 잘 맞는 직무
            required_competencies=[
                Competency("SQL", 1.0, "쿼리를 활용한 분석 경험"),
                Competency("데이터 시각화", 0.8, "대시보드 제작"),
                Competency("통계 분석", 0.9, "가설검정/AB테스트"),
                Competency("Python", 0.7, "pandas 데이터 전처리"),
                Competency("커뮤니케이션", 0.5, "결과 공유 경험"),
            ],
        ),
        Posting(
            id="P2",
            company="B사",
            role="데이터 엔지니어",
            deadline=TODAY + timedelta(days=9),
            fit_score=0.45,  # (Overlap 산출 가정) 상대적으로 덜 맞는 직무
            required_competencies=[
                Competency("Python", 1.0, "파이프라인 구현"),
                Competency("SQL", 0.9, "대용량 쿼리 최적화"),
                Competency("클라우드", 0.8, "AWS/GCP 운영"),
                Competency("데이터 파이프라인", 1.0, "ETL 설계"),
            ],
        ),
    ]


SAMPLE_ESSAY = EssayDraft(
    posting_id="P1",
    text=(
        "학회에서 추천시스템 프로젝트를 진행하며 Python과 pandas로 로그 데이터를 "
        "전처리했습니다. 사용자 행동 데이터를 SQL로 추출해 분석했고, 결과를 팀원들과 "
        "공유하며 방향을 함께 조정했습니다. 다만 통계적 검정이나 대시보드 제작 경험은 "
        "아직 정리해 두지 못했습니다."
    ),
)


def main() -> None:
    client = get_default_client()
    mode = "LLM" if client else "휴리스틱(키 없음)"
    print(f"=== AI 비서 핵심 엔진 데모 · 판정 모드: {mode} ===\n")

    postings = sample_postings()

    # 자소서는 P1에 대해 작성 중이라고 가정. P2는 아직 착수 전(빈 초안).
    essays = {
        "P1": SAMPLE_ESSAY,
        "P2": EssayDraft(posting_id="P2", text=""),
    }

    analyses = [analyze(p, essays[p.id], client=client) for p in postings]

    # ① 공고별 상세 판정
    for a in analyses:
        print(f"[{a.posting.company} {a.posting.role}]  (D-{a.days_left})")
        print(f"  커버율 {a.coverage_rate:.0%} · 격차 {a.gap:.0%}")
        for r in a.results:
            mark = {"covered": "O", "partial": "△", "missing": "X"}[r.status.value]
            line = f"    {mark} {r.competency.name}"
            if r.evidence:
                line += f"  ← \"{r.evidence[:30]}...\""
            print(line)
        note = make_nudge(a, client=client)
        print(f"  💬 {note['nudge']}")
        print(f"  🎯 {note['today_goal']}\n")

    # ③-a 여러 공고 우선순위
    print("=== 오늘의 우선순위 ===")
    for i, item in enumerate(rank(analyses), 1):
        a = item.analysis
        print(f"  {i}. {a.posting.company} {a.posting.role}  "
              f"(점수 {item.score}) — {item.reason}")


if __name__ == "__main__":
    main()
