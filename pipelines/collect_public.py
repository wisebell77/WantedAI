"""공공 직무기술서 수집.

    python pipelines/collect_public.py --years 2023 2025 --per-ncs 200 --budget 2500

중단돼도 캐시가 남는다. 같은 명령을 다시 돌리면 받은 것은 건너뛰고 이어서 받는다.
일일 한도(1만)를 초과하면 자정에 초기화되므로 다음 날 같은 명령을 다시 돌린다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.collect import Budget, PublicCollector, QuotaExceeded
from overlap.config import PATHS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, nargs="+", required=True)
    ap.add_argument("--per-ncs", type=int, default=40,
                    help="NCS 대분류별로 받을 공고 수")
    ap.add_argument("--budget", type=int, default=4000,
                    help="이번 실행에서 쓸 최대 호출 수 (목록+상세+파일)")
    ap.add_argument("--max-per-inst", type=int, default=8,
                    help="한 기관이 한 분류에 기여할 직무 단위 상한")
    ap.add_argument("--max-files", type=int, default=250,
                    help="한 번에 새로 받을 첨부 수 상한. 차단을 피해 나눠 받는다")
    ap.add_argument("--file-delay", type=float, default=1.5)
    ap.add_argument("--only", default="",
                    help="쉼표로 구분한 NCS 대분류 이름(부분 일치)")
    args = ap.parse_args()

    PATHS.ensure()
    from overlap.collect.attachments import AttachmentFetcher
    collector = PublicCollector(
        fetcher=AttachmentFetcher(delay=args.file_delay),
        max_per_inst=args.max_per_inst, max_files=args.max_files)
    only = [w.strip() for w in args.only.split(",") if w.strip()]
    budget = Budget(args.budget)

    def progress(i, n, got, left):
        print(f"  {i}/{n}  확보 {got}건  예산 {left}", flush=True)

    for year in args.years:
        if not budget:
            print("예산 소진 — 남은 연도는 다음 실행에서")
            break
        print(f"=== {year}년 수집 (per-ncs {args.per_ncs}, 예산 {budget.left}) ===",
              flush=True)
        try:
            res = collector.collect(year, args.per_ncs, budget, only, progress)
        except QuotaExceeded:
            print()
            print("[중단] 공공데이터포털 일일 호출 한도를 초과했다.")
            print("  자정(00:00)에 초기화된다. 캐시는 남아 있으므로 내일 같은 명령을")
            print("  다시 돌리면 받은 것은 건너뛰고 나머지만 이어서 받는다.")
            return 2

        total = res.merge_into(PATHS.data / f"jd_docs_{year}.json")
        print(f"{year}년 결과")
        for k, v in res.stats.most_common():
            print(f"  {k:<24}{v:>6}")
        print(f"  기관 상한으로 건너뜀     {res.skipped:>6}")
        print(f"  직무기술서 누적          {total:>6}건")
        print(f"  남은 예산                {budget.left:>6}")
        if res.down:
            print()
            print(f"[중단] 첨부 파일 서버에 연결할 수 없다 — {res.down}")
            print("       API 는 정상이다. 복구되면 같은 명령을 다시 돌리면 된다.")
            print("       상세 조회 결과는 캐시에 남아 호출을 다시 쓰지 않는다.")
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
