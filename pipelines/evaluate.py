"""평가 3종. 데이터를 갱신할 때마다 돌려서 문서의 숫자를 갱신한다.

    python pipelines/evaluate.py                # 커버리지 + 내부 + 교차
    python pipelines/evaluate.py --only cross
    python pipelines/evaluate.py --only indomain --sweep

여기서 나오는 숫자는 **그날의 데이터 기준**이다. 공고를 더 받으면 달라진다.
문서에 적을 때는 기준일을 같이 적는다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.collect.base import read_json
from overlap.competency import CompetencyDictionary
from overlap.config import PATHS
from overlap.evaluate import CoverageReport, CrossDomainEvaluator, CrossScore
from overlap.evaluate import InDomainEvaluator, Score
from overlap.parse import load_units
from overlap.taxonomy import NcsTaxonomy


def section(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["coverage", "indomain", "cross"],
                    default=None)
    ap.add_argument("--sweep", action="store_true",
                    help="내부 평가에서 top_k / min_df 를 훑는다")
    ap.add_argument("--no-projection", action="store_true",
                    help="교차 평가에서 문장 투영을 건너뛴다(모델 로딩 회피)")
    ap.add_argument("--clusters", default=None,
                    help="쓸 L2 군집 파일. 임계를 다시 잡을 때 쓴다")
    args = ap.parse_args()

    units = load_units()
    if not units:
        print("직무 단위가 없다. 먼저 pipelines/build_units.py 를 돌릴 것.")
        return 1
    tax = NcsTaxonomy.load() if PATHS.taxonomy.exists() else None
    run = lambda x: args.only in (None, x)

    print(f"기준일 {date.today().isoformat()} · 직무 단위 {len(units):,}개")

    if run("coverage"):
        section("1. 표본 커버리지 — 이 분류를 믿어도 되는가")
        rep = CoverageReport(units, tax)
        print(rep.table(limit=30))
        print()
        print(rep.collection_plan())

    dic = None
    src = Path(args.clusters) if args.clusters else PATHS.l2_clusters
    if src.exists():
        dic = CompetencyDictionary.load(clusters=src)
        if args.clusters:
            print(f"군집 파일 {src.name}")

    if run("indomain"):
        section("2. 내부 평가 — 같은 방언끼리. 설정값 고르기용")
        ev = InDomainEvaluator(units, dic)
        print(ev)
        print(f"질의 가중 평균 단위 수(편향 기준선) {ev.baseline:.0f}")
        print()
        print(Score.header())
        print("-" * 64)
        scores = ev.sweep() if args.sweep else [ev.run()]
        for s in scores:
            print(s.row())
        print()
        print("표본편향은 1.0 근처가 공정하다. 1 보다 크면 표본이 큰 직무로 쏠린 것이다.")

    if run("cross"):
        roles = read_json(PATHS.roles, []) or []
        if not roles:
            print()
            print("민간 직무가 없어 교차 평가를 건너뛴다 "
                  "(pipelines/refresh_private.py).")
            return 0
        section("3. 교차 평가 — 방언이 다른 질의. 진짜 지표")
        ev = CrossDomainEvaluator(units, roles)
        print(ev)
        print()
        print(CrossScore.header())
        print("-" * 64)
        print(ev.string_match().row())
        if dic:
            print(ev.string_match(dic).row())
        if not args.no_projection and dic:
            from overlap.competency import TextProjector
            print(ev.projection(TextProjector(dic)).row())
        print()
        print("정답은 대분류 수준이다. 소분류 안의 구분과 확장 노드의 기여는")
        print("이 지표로 잡히지 않는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
