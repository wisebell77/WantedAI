"""jd_good.json 에 본문·직무군·등급·기술을 붙여 jd_tiered.json 을 만든다.

    python scripts/build_tiered.py

**이 파일이 없어서 AI 코치가 막혀 있었다.** jd_tiered.json 은 앱이 공고 본문을
읽는 유일한 통로인데(server/local-server.mjs 의 postingByUrl), 이걸 다시 만드는
코드가 저장소에 없었다. 그래서 본문을 411건 모아도 앱이 보는 것은 옛날에 한 번
만들어 둔 221건뿐이었고, 직무가 연결된 공고 148건 중 38건만 코치가 붙었다.

jd_tiered = jd_good + clean·job·tier·techs 다. 넷 다 analyze_jd 에 있는
함수로 뽑는다. 새 규칙을 만들지 않는다 — split_roles.py 가 roles.json 을 만들 때
쓰는 것과 같은 함수를 같은 순서로 부른다. 두 파일이 다른 기준으로 갈리면
"직무는 있는데 본문이 없는" 공고가 다시 생긴다.

    clean   strip_boilerplate — 머리말·꼬리말·메뉴를 걷어낸 본문
    tier    tier()            — A/B/C. persona 의 load_roles(tier="A") 가 본다
    job     classify()        — 민간 직무군(개발/SW, 경영지원 …)
    techs   TECH 사전과 hit() — 공고에 실제로 나온 도구 이름
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from analyze_jd import TECH, classify, hit, strip_boilerplate, tier

SRC = Path("data/jd_good.json")
OUT = Path("data/jd_tiered.json")


def main() -> int:
    if not SRC.exists():
        print(f"{SRC} 가 없다. 먼저 수집을 돌릴 것.")
        return 1

    before = len(json.loads(OUT.read_text(encoding="utf-8"))) if OUT.exists() else 0
    recs = strip_boilerplate(json.loads(SRC.read_text(encoding="utf-8")))

    for r in recs:
        r["job"] = classify(r)
        r["tier"] = tier(r)
        r["techs"] = [x for x in TECH if hit(x, r.get("clean", ""))]

    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")

    # 본문이 비면 앱에서 그 공고는 코치가 안 붙는다. 몇 건이 그런지 같이 찍는다.
    empty = sum(1 for r in recs if not r.get("clean"))
    with_tech = sum(1 for r in recs if r["techs"])
    print("=" * 62)
    print(f"  {before}건 → {len(recs)}건")
    print(f"  본문 없음   {empty}건")
    print(f"  도구명 있음 {with_tech}건")
    print()
    print("  등급:", dict(sorted(Counter(r["tier"] for r in recs).items())))
    print()
    print("  직무군 상위 8개")
    for job, n in Counter(r["job"] for r in recs).most_common(8):
        print(f"    {job:<16}{n:>5}")
    print()
    print(f"  저장: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
