"""받아 둔 첨부 텍스트 → 직무 단위(JobUnit) + NCS 코드 확정.

    python pipelines/build_units.py

네트워크를 타지 않는다. 캐시(data/jdtext/)만 읽으므로 파싱 규칙을 고칠 때마다
부담 없이 다시 돌리면 된다. 수집과 해석을 나눠 둔 이유가 이것이다.

라벨은 **문서 자신의 분류체계 표**에서 읽는다. 공고 API 가 주는 NCS 라벨은
공고 단위라 한 공고 안 모든 직무에 복사된다(실제로 240건이 잘못 붙었다).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.config import PATHS
from overlap.parse import UnitSplitter, save_units
from overlap.taxonomy import NcsResolver, NcsTaxonomy


def documents() -> dict[str, dict]:
    """jd_docs_*.json 을 합쳐 fileNo → 메타로."""
    out = {}
    for f in PATHS.data.glob("jd_docs_*.json"):
        for d in json.loads(f.read_text(encoding="utf-8")):
            out[str(d["fileNo"])] = d
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None, help="기본값은 data/jd_units.json")
    args = ap.parse_args()

    tax = NcsTaxonomy.load()
    resolver = NcsResolver(tax)
    splitter = UnitSplitter()
    docs = documents()

    units, how = [], Counter()
    files = sorted(PATHS.jd_text.glob("*.json"))
    for i, f in enumerate(files, 1):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            how["텍스트 캐시 손상"] += 1
            continue
        text = rec.get("text") or ""
        if len(text) < 300:
            continue
        meta = docs.get(str(rec["fileNo"]), {})
        for u in splitter.split(text, file_no=str(rec["fileNo"]),
                                institution=meta.get("inst", ""),
                                year=meta.get("year")):
            # 대분류 힌트는 공고 라벨에서 온다. 단, 공고가 분류를 **하나만**
            # 달고 있을 때만 쓴다. 공고의 67% 는 복수 분류라 첫 번째를 집으면
            # 다른 직무에 엉뚱한 대분류가 걸리고, 그 힌트로 표 조회를 제한하면
            # 맞는 후보까지 잘려 나가 '대분류만'으로 떨어진다.
            all_ncs = meta.get("ncs_all") or ([meta["ncs"]] if meta.get("ncs") else [])
            hint = all_ncs[0] if len(all_ncs) == 1 else ""
            region = splitter.taxonomy_region(u.text)
            r = resolver.resolve(region, major_hint=hint)
            how[r.how] += 1
            u.ncs_code = r.code
            u.ncs_path = tax.path(r.code) if r.code else {}
            units.append(u)
        if i % 500 == 0:
            print(f"  {i}/{len(files)}  단위 {len(units)}개", flush=True)

    n = save_units(units, args.out)
    fixed = sum(1 for u in units if u.ncs_code and len(u.ncs_code) >= 6)

    print(f"문서 {len(files):,}건 → 직무 단위 {n:,}개")
    print(f"  소분류 이상 확정 {fixed:,}개 ({fixed / max(n, 1) * 100:.1f}%)")
    print()
    print("분류 확정 경로")
    for k, v in how.most_common():
        print(f"  {k:<20}{v:>6}")
    print()
    print(f"저장: {args.out or PATHS.units}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
