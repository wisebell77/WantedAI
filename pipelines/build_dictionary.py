"""역량 사전 구축 — L2 의미 군집 + 확장 노드.

    python pipelines/build_dictionary.py                 # 둘 다
    python pipelines/build_dictionary.py --skip-cluster  # 확장 노드만
    python pipelines/build_dictionary.py --threshold 0.30 0.35 0.40

임베딩이 오래 걸리지만 캐시(data/l2_emb.npz)가 남아 임계만 바꿀 때는 즉시 끝난다.

Anaconda 환경에서 torch 를 쓰면 OpenMP 가 두 번 로드돼 죽는 경우가 있다.
그때는 KMP_DUPLICATE_LIB_OK=TRUE 를 걸고 돌린다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.competency import ExtensionBuilder, L2Clusterer
from overlap.config import PATHS
from overlap.parse import load_units
from overlap.collect.base import read_json


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold", type=float, nargs="+", default=[0.35],
                    help="군집 거리 임계. 여러 개면 각각 저장한다")
    ap.add_argument("--min-df", type=int, default=3, help="군집 대상 최소 등장 단위 수")
    ap.add_argument("--skip-cluster", action="store_true")
    ap.add_argument("--skip-extensions", action="store_true")
    ap.add_argument("--ext-min-df", type=int, default=3)
    ap.add_argument("--ext-min-corp", type=int, default=2)
    args = ap.parse_args()

    units = load_units()
    if not units:
        print("직무 단위가 없다. 먼저 pipelines/build_units.py 를 돌릴 것.")
        return 1

    # ── L2 군집
    if not args.skip_cluster:
        vocab = L2Clusterer.vocabulary(units)
        print(f"어휘 {len(vocab):,}종 (단위 {len(units):,}개)")
        clusterer = L2Clusterer(cache=PATHS.l2_embeddings)
        for th in args.threshold:
            res = clusterer.fit(vocab, threshold=th, min_df=args.min_df)
            out = PATHS.data / f"l2_clusters_{int(th * 100)}.json"
            res.save(out)
            print(f"  거리 {th:.2f} → 군집 {len(res.groups):,}개  저장 {out.name}")
        print()

    # ── 확장 노드
    if args.skip_extensions:
        return 0
    roles = read_json(PATHS.roles, []) or []
    if not roles:
        print("민간 직무가 없다. pipelines/refresh_private.py 를 먼저 돌릴 것.")
        return 1

    public = public_nodes()
    builder = ExtensionBuilder(min_df=args.ext_min_df, min_corp=args.ext_min_corp)
    res = builder.build(roles, public)
    res.save()

    print(f"민간 {res.roles}직무 → 후보 {res.candidates:,}종")
    for k, v in res.dropped.most_common():
        print(f"  {k:<24}{v:>6} 탈락")
    linked = sum(1 for n in res.nodes if n.parent and not n.is_new_axis)
    new_axis = sum(1 for n in res.nodes if n.is_new_axis)
    print()
    print(f"확장 노드 {len(res.nodes)}개")
    print(f"  공공 노드 하위로 연결      {linked}")
    print(f"  신설 상위 축               {new_axis}")
    print(f"  연결 미정(사람 확인 필요)   {len(res.nodes) - linked - new_axis}")
    if res.new or res.gone:
        print(f"  직전 대비 신규 {len(res.new)} · 소멸 {len(res.gone)}")
    print()
    print(f"저장: {PATHS.ext_nodes}")
    return 0


def public_nodes() -> list[str]:
    """공공 축의 모든 노드 이름.

    정보통신 축만 쓰면 `안전관리` 같은 다른 소분류 개념이 빈 것처럼 보인다.
    전 분류의 노드를 합쳐서 '공공에 이미 있는가'를 판정한다.
    """
    from overlap.competency import ClusterResult
    if PATHS.l2_clusters.exists():
        return list(ClusterResult.load(PATHS.l2_clusters).groups)
    return list(L2Clusterer.vocabulary(load_units()))


if __name__ == "__main__":
    raise SystemExit(main())
