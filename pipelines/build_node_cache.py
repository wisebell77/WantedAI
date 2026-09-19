"""배포용 임베딩 캐시. 노드 벡터만 담는다.

    python pipelines/build_node_cache.py
    python pipelines/build_node_cache.py --out data/l2_emb.npz

**왜 따로 만드나.** `TextProjector` 는 `data/l2_emb.npz` 에서 노드 벡터를 꺼내
쓴다. 그 파일이 없으면 기동 때 노드 2,343 개를 새로 임베딩하는데 **38 초가 더
걸린다**(첫 요청 18.7 초 → 57 초). 심사 기간 가동률이 실격 조건이라 그냥 둘 수 없다.

그런데 군집 파이프라인이 만드는 원본 캐시는 **143.5 MB** 다. 원문 표기 16,820 개를
전부 담고 있어서인데, 프로젝터가 실제로 찾는 건 사전 노드 2,343 개뿐이다.

    원본 l2_emb.npz   core 16,820 개   143.5 MB
    노드만            core  2,343 개     6.9 MB      <- 이걸 만든다

깃에 넣기에도, 이미지에 굽기에도 6.9 MB 면 부담이 없다. 그리고 이 스크립트는
사전(`l2_clusters_*.json`)만 있으면 돌아간다 — 원본 단위 68 MB 가 필요 없어서
컨테이너 빌드 단계에서 그대로 실행할 수 있다.

임베딩은 결정적이라 새로 계산한 값과 원본 캐시에서 꺼낸 값이 같다. 검증은
`--verify` 로 한다(원본 캐시가 있을 때만).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from overlap.competency import CompetencyDictionary, TextProjector
from overlap.config import PATHS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None, help="기본값은 PATHS.l2_embeddings")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--verify", action="store_true",
                    help="원본 캐시와 값이 같은지 대조(원본이 있을 때만)")
    args = ap.parse_args()

    out = Path(args.out or PATHS.l2_embeddings)
    old = None
    if args.verify and out.exists():
        z = np.load(out, allow_pickle=True)
        old = ({w: i for i, w in enumerate(z["core"])}, z["E"])
        print(f"대조용 원본 — core {len(old[0]):,}개 · {out.stat().st_size / 1048576:.1f} MB")

    dic = CompetencyDictionary.load()
    names = list(dic.names)
    print(f"사전 노드 {len(names):,}개 임베딩 중...", flush=True)

    t0 = time.time()
    # 프로젝터를 통해 같은 모델·같은 정규화를 쓴다. 여기서 모델 이름이 갈리면
    # 캐시가 조용히 어긋나 유사도가 통째로 달라진다.
    model = TextProjector(dic).model
    E = model.encode(names, batch_size=args.batch_size,
                     normalize_embeddings=True, show_progress_bar=False)
    E = np.asarray(E, dtype="float32")
    took = time.time() - t0

    if old is not None:
        idx, OLD = old
        both = [(i, idx[n]) for i, n in enumerate(names) if n in idx]
        if both:
            a = E[[i for i, _ in both]]
            b = np.asarray(OLD[[j for _, j in both]], dtype="float32")
            d = float(np.abs(a - b).max())
            print(f"  원본과 겹치는 {len(both):,}개 — 최대 절대오차 {d:.2e} "
                  f"({'같다' if d < 1e-4 else '**다르다 — 모델이 바뀌었는지 확인할 것**'})")

    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, core=np.array(names, dtype=object), E=E)
    print(f"저장: {out}  ({out.stat().st_size / 1048576:.1f} MB · {took:.0f}초)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
