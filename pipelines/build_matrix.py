"""직무 × 역량 행렬 + 근거 인덱스 생성. 서비스가 읽는 최종 산출물이다.

    python pipelines/build_matrix.py
    python pipelines/build_matrix.py --no-l2      # 사전 없이 (L1만)

둘을 같이 만드는 이유가 있다. 근거 인덱스는 행렬에 실제로 들어간 역량에 대해서만
원문을 되찾아야 하고, 그때 **행렬과 똑같은 접기 함수**를 써야 한다.
따로 돌리면 사전이 바뀌었을 때 행렬에는 있는데 근거는 비는 역량이 생긴다.

행렬만 있으면 임베딩 모델 없이도 순위를 낼 수 있다.
모델은 사용자 문장을 역량으로 바꾸는 투영에만 필요하다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.competency import CompetencyDictionary
from overlap.config import PATHS, SETTINGS
from overlap.evaluate import CoverageReport
from overlap.parse import load_units
from overlap.recommend import EvidenceIndex, JobMatrix
from overlap.taxonomy import NcsTaxonomy


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-l2", action="store_true", help="L2 군집을 쓰지 않는다")
    ap.add_argument("--no-extensions", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--evidence-out", default=None)
    ap.add_argument("--quotes", type=int, default=3,
                    help="(직무, 역량) 하나당 보관할 공고 원문 표기 수")
    ap.add_argument("--no-evidence", action="store_true",
                    help="근거 인덱스를 만들지 않는다. 서비스에는 쓰면 안 된다")
    ap.add_argument("--plan", action="store_true",
                    help="미달 분류의 수집 계획도 출력")
    args = ap.parse_args()

    units = load_units()
    if not units:
        print("직무 단위가 없다. 먼저 pipelines/build_units.py 를 돌릴 것.")
        return 1

    tax = NcsTaxonomy.load() if PATHS.taxonomy.exists() else None
    dic = None
    if not args.no_l2:
        dic = CompetencyDictionary.load(use_extensions=not args.no_extensions)
        print(dic)

    matrix = JobMatrix.build(units, dic, tax)
    matrix.save(args.out)

    print(f"직무 단위 {len(units):,}개 → 행렬 {len(matrix)}개 직무")
    print(f"  포함 기준: 유효단위 >= {SETTINGS.min_effective_units} · "
          f"HHI < {SETTINGS.max_hhi} · 기관당 상한 {SETTINGS.institution_cap}")
    print(f"  직무당 역량: 상위 {SETTINGS.top_k}개 (df x IDF 순)")
    print()
    print(f"{'직무':<24}{'단위':>6}{'기관':>5}{'역량':>6}")
    print("-" * 44)
    for p in sorted(matrix, key=lambda p: -p.units)[:20]:
        print(f"  {p.name[:22]:<24}{p.units:>6}{p.institutions:>5}{len(p.weights):>6}")
    print("-" * 44)
    print(f"  총 {len(matrix)}개 직무")
    print()
    print(f"저장: {args.out or PATHS.job_matrix}")

    if not args.no_evidence:
        print()
        ev = EvidenceIndex.build(units, matrix, dic, top=args.quotes)
        p = ev.save(args.evidence_out)
        print(ev)
        print(f"  (직무, 역량) 쌍마다 공고 원문 상위 {args.quotes}개 + 출처 문서")
        print(f"저장: {p}  ({p.stat().st_size / 1048576:.1f} MB)")
        missing = sum(1 for prof in matrix for c in prof.weights
                      if not ev.has(prof.code, c))
        if missing:
            # 행렬에 있는데 근거가 없는 역량은 접기 함수가 어긋났다는 뜻이다.
            print(f"  주의 — 근거를 못 찾은 역량 {missing:,}개. "
                  f"사전과 행렬이 다른 버전일 수 있다")

    if args.plan:
        print()
        rep = CoverageReport(units, tax)
        print(rep.collection_plan())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
