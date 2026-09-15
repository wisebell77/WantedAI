"""엔진을 한 번 돌려 본다. 화면 문구의 기준형이 여기 있다.

    python pipelines/recommend_demo.py --text "학회 운영진으로 8명 일정 조율" \\
                                       --text "설문 300건 정리해 보고서 작성"
    python pipelines/recommend_demo.py --preset 데이터분석
    python pipelines/recommend_demo.py --target 경영기획 --text "..."

출력에 퍼센트가 없다는 점을 눈으로 확인하는 용도이기도 하다.
겹치는 역량 **개수**와 **근거 문장**, 그리고 그 역량을 요구한 **공고 건수**만 나온다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap import Recommender

# 랜딩에 둘 샘플 프로필. 로그인·업로드 없이 클릭 한 번으로 결과를 보여 준다.
PRESETS = {
    "데이터분석": [
        "교내 학술동아리에서 공공데이터 30만 행을 파이썬으로 정리하고 시각화했다",
        "설문 300건을 수집해 교차분석하고 결과를 보고서로 정리했다",
        "학회 운영진으로 8명의 일정을 조율하고 예산 집행 내역을 관리했다",
    ],
    "마케팅": [
        "교내 홍보팀에서 SNS 채널을 운영하며 콘텐츠를 기획하고 반응을 분석했다",
        "신입생 대상 행사를 기획해 참가자 200명을 모집했다",
        "협찬사 5곳과 연락하며 제안서를 작성하고 조건을 조율했다",
    ],
    "개발": [
        "팀 프로젝트에서 웹 백엔드를 맡아 API 를 설계하고 데이터베이스를 구성했다",
        "깃으로 브랜치를 나눠 협업하고 코드 리뷰를 진행했다",
        "서버 배포 자동화를 시도해 배포 시간을 줄였다",
    ],
}


def competency(e, indent: str = "     ") -> None:
    """역량 하나. 사용자 쪽 근거와 공고 쪽 근거를 함께 낸다."""
    print(f"{indent}· {e.competency}  (공고 {e.postings}건에서 요구)")
    if e.sentence:
        print(f"{indent}    당신의 경험 — {e.sentence[:56]}")
    for q in e.quotes[:1]:
        print(f"{indent}    공고 원문   — {q.text[:56]}")
        src = e.source_label()
        if src:
            print(f"{indent}                  {src[:52]}")


def show(m, limit: int = 4) -> None:
    print(f"  {m.sentence()}")
    for e in m.have[:limit]:
        competency(e)
    print()


def show_market(signals) -> None:
    if not signals:
        return
    print("[민간 축] 공공 직무기술서에는 없지만 시장이 요구하는 것")
    print("  (민간 공고는 본문을 인용하지 않고 출처만 표시합니다)")
    print()
    for s in signals:
        print(f"     · {s.sentence()}")
        for corp, role in s.examples[:2]:
            print(f"         {corp}" + (f" — {role[:40]}" if role else ""))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", action="append", default=[],
                    help="경험 원문. 여러 번 줄 수 있다")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--target", default="", help="정방향으로 볼 목표 직무")
    ap.add_argument("--seen", action="append", default=[],
                    help="이미 보고 있는 직무. 역방향에서 같은 대분류를 뺀다")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    texts = args.text or PRESETS.get(args.preset or "", [])
    if not texts:
        ap.error("--text 또는 --preset 중 하나가 필요하다")

    r = Recommender()
    print("입력")
    for t in texts:
        print(f"  · {t}")
    print()

    res = r.profile(texts)          # 투영을 한 번만 하고 돌려 쓴다

    if args.target:
        rep = r.forward(texts, args.target)
        print(f"[정방향] {rep.target.name}")
        show(rep.target, args.limit)
        print("  아직 겹치지 않는 역량 (공고에서 자주 요구되는 순)")
        print()
        for e in rep.target.lack[:args.limit]:
            competency(e)
        print()
        print("  비교 — 같은 경험으로 본 다른 직무")
        for m in rep.compare:
            print(f"     {m.name}: 겹침 {m.overlap}개")
        print()
        show_market(rep.market)
        if rep.unmatched:
            print(f"  사전에 붙지 않은 문장 {len(rep.unmatched)}개 "
                  f"(확장 노드 후보로 쌓인다)")
        return 0

    matches = (r.unexpected(texts, seen=args.seen, limit=args.limit)
               if args.seen else r.reverse_from(res, limit=args.limit))
    print("[역방향] 겹침이 많은 직무" +
          (" — 안 보던 분야만" if args.seen else ""))
    print()
    for m in matches:
        show(m)
    if not matches:
        print("  근거가 충분한 직무가 없다. 경험 원문을 더 넣어 보라.")
    show_market(r.market_signals(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
