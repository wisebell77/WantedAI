"""ApplicationTracker 데모 — 담아두고, 이어서 쓰고, 날짜별로 추적.

    python run_tracker.py

포인트:
  1. 자소서는 '한 번' 붙이면 보관된다 → 매일 재입력 X
  2. 며칠에 걸쳐 자소서가 채워지는 과정을 스냅샷으로 기록 → 진행 추이
  3. JSON으로 저장/복원
LLM 없이 휴리스틱으로 동작(크레딧 소모 없음).
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from assistant import (
    ApplicationTracker,
    get_default_client,
    llm_stats_summary,
    make_nudge,
    rank,
)
from assistant.overlap_loader import load_postings

STORE = os.path.join(os.path.dirname(__file__), "data", "tracker_demo.json")

EXPERIENCE = (
    "Python과 SQL로 로그 데이터를 전처리·분석하고, 통계 분석과 대시보드 시각화, "
    "Git 협업, AWS 배포, Excel 지표 관리 경험이 있습니다."
)


def main() -> None:
    # 키 있으면 LLM으로 판정(진행도·fit), 없으면 휴리스틱 — 트래킹 판정도 엔진과 동일
    client = get_default_client()
    print(f"판정 모드: {'LLM' if client else '휴리스틱(키 없음)'}\n")
    tracker = ApplicationTracker(store_path=STORE, client=client)

    # 1) 공고 담기 + 경험 한 번 설정
    for p in [pp for pp in load_postings(tier="A", limit=20)
              if len(pp.required_competencies) >= 3][:3]:
        tracker.add_posting(p)
    tracker.set_experience(EXPERIENCE)

    pid = next(iter(tracker.postings))       # 첫 공고에 자소서를 쓰기 시작한다고 가정
    target = tracker.postings[pid]
    print(f"작성 대상 공고: [{target.company}] {target.role[:30]}")
    print(f"요구 역량: {[c.name for c in target.required_competencies]}\n")

    day1 = date.today()
    day3 = day1 + timedelta(days=2)

    # 2) Day 1 — 자소서 초안 '한 번' 붙임(일부 역량만)
    tracker.attach_draft(pid, text="Python으로 데이터를 분석한 경험이 있습니다.")
    tracker.snapshot(as_of=day1)
    print(f"[{day1}] 초안 작성 시작 — 커버율 {tracker.progress(pid)[-1][1]:.0%}")

    # 3) Day 3 — 자소서를 '이어서' 편집(재붙여넣기 아님, 보관본 수정)
    tracker.update_draft(
        pid,
        "Python과 SQL로 데이터를 분석하고 결과를 시각화해 팀과 공유한 경험이 있습니다.",
    )
    tracker.snapshot(as_of=day3)
    print(f"[{day3}] 이어서 작성   — 커버율 {tracker.progress(pid)[-1][1]:.0%}")

    # 4) 진행 추이(시간축 트래킹)
    print("\n=== 진행 추이 ===")
    prev = None
    for d, cov in tracker.progress(pid):
        delta = "" if prev is None else f"  (▲ {cov - prev:+.0%})"
        print(f"  {d}: 커버율 {cov:.0%}{delta}")
        prev = cov

    # 5) 오늘의 넛지 + 우선순위 (마지막 스냅샷 시점 기준)
    print("\n=== 오늘의 비서 ===")
    analyses = tracker.analyze_all(as_of=day3)
    for item in rank(analyses)[:3]:
        a = item.analysis
        note = make_nudge(a, client=client)
        total = len(a.results)
        matched = len(a.posting.fit_matched or [])
        print(f"  [{a.posting.company}] D-{a.days_left} · 경험 겹침 {matched}/{total}개 "
              f"· 진행 {a.coverage_rate:.0%}")
        print(f"    🎯 {note['today_goal']}")

    # 6) 저장 → 복원 확인
    tracker.save()
    reloaded = ApplicationTracker.load(STORE)
    print(f"\n저장/복원 OK — 공고 {len(reloaded.postings)}건, "
          f"스냅샷 {len(reloaded.snapshots)}일치 (파일: {os.path.relpath(STORE)})")

    print(f"\n[판정 집계] {llm_stats_summary()}")


if __name__ == "__main__":
    main()
