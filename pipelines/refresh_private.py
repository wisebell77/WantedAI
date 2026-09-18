"""민간 공고 코퍼스 최신화.

    python pipelines/refresh_private.py          # 목록 갱신 + 병합 + 직무 분해
    python pipelines/refresh_private.py --merge-only

공채속보는 '현재 열려 있는 공채'의 스냅샷이라 과거 조회가 안 된다.
4일 만에 93건이 새로 올라오고 132건이 마감돼 목록에서 사라졌다.
주기적으로 받아 누적하는 수밖에 없고, 마감분은 우리 쪽에 계속 보관한다.

**순서를 지켜야 한다.** 본문 병합(PrivateCorpus.merge)은 static·browser·ocr
세 캐시를 모두 읽는다. static 수집만으로 코퍼스를 덮어쓰면 browser·ocr 로 건진
것이 조용히 사라진다 — 실제로 221건이 131건으로 줄었다.
그래서 이 스크립트를 거치지 않고 본문 파일을 직접 쓰지 않는다.

본문 수집(requests/Playwright)과 이미지 판독은 이 스크립트 밖에 있다.
브라우저 렌더링과 사람의 판독은 자동화 대상이 아니기 때문이다.
판독 결과를 data/ocr/{seq}.json 에 넣은 뒤 --merge-only 로 반영한다.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.collect import GongchaeClient, PrivateCorpus
from overlap.config import PATHS
from overlap.parse import RoleSplitter
from overlap.collect.base import write_json


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--merge-only", action="store_true",
                    help="목록 갱신을 건너뛰고 병합·직무분해만 (판독 반영 후)")
    args = ap.parse_args()

    PATHS.ensure()
    if not args.merge_only:
        diff = GongchaeClient().refresh()
        print(f"공채속보 total {diff.total} / 누적 {diff.stored}건")
        print(f"  새 공고          {len(diff.new)}건")
        print(f"  목록에서 사라짐   {diff.gone}건 (마감 — 보관분은 유지)")
        for r in diff.new[:15]:
            print(f"   {r['empWantedStdt']}~{r['empWantedEndt']}  "
                  f"{r['empBusiNm'][:16]:<18} {r['empWantedTitle'][:40]}")
        print()

    corpus = PrivateCorpus()
    good = corpus.merge()
    path = corpus.save(good)
    print(f"본문 확보 {len(good)}건 → {path}")
    print("  출처:", dict(corpus.stats))

    roles = RoleSplitter().split_all(good)
    write_json(PATHS.roles, [r.to_dict() for r in roles], indent=1)
    print(f"공고 {len(good)}건 → 직무 {len(roles)}개 "
          f"(공고당 {len(roles) / max(len(good), 1):.1f})")

    jobs = Counter(r.job for r in roles)
    mx = max(jobs.values()) if jobs else 1
    print()
    print(f"{'직무':<14}{'직무수':>6}   분포")
    print("-" * 52)
    for j, c in jobs.most_common():
        print(f"{j:<14}{c:>6}   {'#' * round(c / mx * 24)}")
    print()
    print(f"저장: {PATHS.roles}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
