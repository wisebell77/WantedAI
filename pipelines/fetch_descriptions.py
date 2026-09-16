"""NCS 분류에 공식 설명을 붙인다. 고용24 표준직무기술서(215L01).

    python pipelines/fetch_descriptions.py
    python pipelines/fetch_descriptions.py --force     # 이미 받은 것도 다시

이름만으로는 무슨 일인지 안 와닿는다 — `정보기술전략·계획`, `건축설비설계·시공`,
`산업안전관리공통직무`. 추천 결과로 내밀면서 설명을 못 하면 곤란하다.

분류표(NCS-KECO 연계표)에는 코드와 이름뿐이라 설명을 따로 받아야 한다.
받아 온 문장은 **공식 능력단위 정의 그대로**다. 요약하거나 다시 쓰지 않는다 —
근거 없는 문장을 화면에 올리지 않는다는 규칙이 여기에도 걸린다.

한 번 받으면 data/ncs_descriptions.json 에 쌓이고 다음부터는 건너뛴다.
분류 체계는 몇 년에 한 번 바뀌므로 자주 돌릴 일이 없다.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.collect import DescriptionStore, JobInfoClient
from overlap.config import PATHS
from overlap.parse import load_units
from overlap.recommend import JobMatrix
from overlap.taxonomy import NcsTaxonomy


def targets(min_units: int = 5) -> list[tuple[str, str]]:
    """설명이 필요한 분류. 행렬에 든 소분류 + 그 안의 세분류."""
    tax = NcsTaxonomy.load()
    M = JobMatrix.load()
    out = [(p.code, p.name) for p in M]
    sub: dict[str, Counter] = defaultdict(Counter)
    for u in load_units():
        c = u.ncs_code or ""
        if len(c) >= 8 and c[:6] in M:
            sub[c[:6]][c[:8]] += 1
    for counts in sub.values():
        for code, n in counts.items():
            if n >= min_units and tax.name(code):
                out.append((code, tax.name(code)))
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--min-units", type=int, default=5,
                    help="이만큼도 안 되는 세분류는 건너뛴다")
    args = ap.parse_args()

    if not PATHS.job_matrix.exists():
        print("행렬이 없다. 먼저 pipelines/build_matrix.py 를 돌릴 것.")
        return 1

    store = DescriptionStore.load()
    client = JobInfoClient()
    if not client.key:
        print("WORK24_KEY_JOBDUTY 가 비어 있다. .env 를 확인할 것.")
        return 1

    todo = targets(args.min_units)
    print(f"대상 {len(todo)}개 (이미 받은 것 {len(store)}개)", flush=True)
    got = miss = skip = 0
    for i, (code, name) in enumerate(todo, 1):
        if not args.force and code in store:
            skip += 1
            continue
        d = client.describe(code, name)
        if d.ok:
            store.put(d)
            got += 1
        else:
            miss += 1
        if i % 20 == 0:
            print(f"  {i}/{len(todo)}  확보 {got} · 미확보 {miss} · 건너뜀 {skip}",
                  flush=True)
            store.save()

    p = store.save()
    print()
    print(f"확보 {got} · 미확보 {miss} · 건너뜀 {skip}")
    print(f"설명 보유 {len(store)}개 → {p}")
    if miss:
        print()
        print("미확보는 API 가 이름으로 못 찾은 것이다. 매칭이 소박한 문자열 비교라")
        print("가운뎃점·괄호가 든 이름에서 자주 빈다. 그 분류는 설명 없이 나간다 —")
        print("지어내지 않는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
