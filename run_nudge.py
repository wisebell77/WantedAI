"""실제 Overlap 공고 데이터로 핵심 엔진(fit·커버판정·넛지·우선순위) 돌려보기.

    python run_nudge.py

data/overlap/ 의 실제 A등급 공고를 로드해, 사용자의 경험/자소서와 대조한다.
- 판정 모드: ANTHROPIC_API_KEY 있으면 LLM, 없으면 휴리스틱
- fit_score 는 이제 mock 이 아니라 사용자 '전체 경험'으로 자체 추정한다(간이 추정기).
- deadline 은 데이터에 없어 데모용 임시값(로더가 부여).

두 축의 차이가 데모의 핵심:
  fit(적합도)  = 내 '전체 경험' vs 공고 요구   → 이 직무가 나한테 맞나
  coverage(진행도) = 이 공고용 '자소서 초안' vs 공고 요구 → 얼마나 써놨나
"""

from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from assistant import (
    EssayDraft,
    EssaySection,
    analyze,
    apply_fit,
    daily_briefing,
    get_default_client,
    llm_stats_summary,
    make_nudge,
    rank,
    render_briefing,
)
from assistant.overlap_loader import load_postings

# 사용자의 '전체 경험' — fit(적합도) 추정의 기준. 모든 공고에 대해 계산된다.
EXPERIENCE = (
    "학회에서 추천시스템 프로젝트를 진행하며 Python과 pandas로 대용량 로그 데이터를 "
    "전처리했습니다. SQL로 사용자 행동 데이터를 추출하고 통계 분석과 AB 테스트로 가설을 "
    "검증했으며, 결과를 대시보드로 시각화해 팀과 공유했습니다. Git으로 협업했고, "
    "간단한 웹 서비스를 AWS에 배포한 경험, Excel로 지표를 관리한 경험도 있습니다."
)

def build_active_draft(active) -> EssayDraft:
    """'작성 중' 공고의 자소서를 문항별로 만든다(A 입력 구조)."""
    names = [c.name for c in active.required_competencies[:2]]
    joined = "과 ".join(names) if names else "핵심 역량"
    return EssayDraft(
        posting_id=active.id,
        sections=[
            EssaySection(
                question="지원 동기",
                answer="데이터로 문제를 푸는 일에 매력을 느껴 지원했습니다.",
            ),
            EssaySection(
                question="본인의 강점과 관련 경험",
                answer=f"저는 {joined}을 활용한 학회 프로젝트 경험이 있습니다.",
            ),
        ],
    )


def main() -> None:
    client = get_default_client()
    mode = "LLM" if client else "휴리스틱(키 없음)"
    print(f"=== 실제 공고 데이터 · 판정 모드: {mode} ===\n")

    # A등급 공고 로드 후, 역량 3개 이상인 것만 6건 (역량 1~2개짜리는 fit 노이즈가 커서 제외)
    postings = [p for p in load_postings(tier="A", limit=20)
                if len(p.required_competencies) >= 3][:6]
    apply_fit(postings, EXPERIENCE, client=client)

    # 적합도가 가장 높은 공고를 '지금 작성 중'으로 가정 → 그 공고만 초안 존재, 나머지는 미착수
    active = max(postings, key=lambda p: p.fit_score or 0)
    active_essay = build_active_draft(active)

    analyses, essays = [], {}
    for p in postings:
        essay = active_essay if p is active else EssayDraft.from_text(p.id, "")
        essays[p.id] = essay
        analyses.append(analyze(p, essay, client=client))

    # ── 오늘 할 일 (여러 공고 종합 → 한 가지 집중) — 맨 위에 ──
    brief = daily_briefing(analyses, essays=essays, client=client)
    print("┏━━ 오늘 할 일 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for line in render_briefing(brief).splitlines():
        print("┃ " + line)
    print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    print("── 공고별 상세 ──")
    for a in analyses:
        p = a.posting
        tag = " ← 작성 중" if p is active else ""
        total = len(a.results)
        matched = len(p.fit_matched or [])
        print(f"[{p.company}] {p.role[:34]}{tag}")
        # 적합도는 '겹침 개수'로(합격확률 오해 방지), 진행도는 그대로 %로
        print(f"  D-{a.days_left} · 경험 겹침 {matched}/{total}개 · 진행도 {a.coverage_rate:.0%}")
        print(f"    요구역량({total}): " + ", ".join(
            f"{'●' if r.status.value=='covered' else '○'}{r.competency.name}" for r in a.results))
        # 문항별 근거(어느 문항에서 확인됐나)
        for r in a.results:
            if r.status.value == "covered" and r.section:
                print(f"      └ {r.competency.name} ← '{r.section}' 문항")
        note = make_nudge(a, client=client, essay=essays[p.id])
        print(f"  💬 {note['nudge']}")
        print(f"  🎯 {note['today_goal']}\n")

    print("=== 오늘의 우선순위 (경험 겹침 × 마감임박도 × 남은 작업) ===")
    for i, item in enumerate(rank(analyses), 1):
        a = item.analysis
        print(f"  {i}. [{a.posting.company}] {a.posting.role[:24]}  "
              f"(점수 {item.score}) — {item.reason}")

    print(f"\n[판정 집계] {llm_stats_summary()}")


if __name__ == "__main__":
    main()
