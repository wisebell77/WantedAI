"""NCS 대분류 ↔ 민간 직무군 대응표를 JSON 으로 내보낸다.

    python pipelines/export_ncs_map.py

**왜 필요한가.** 화면의 두 기능이 서로 다른 분류를 쓴다.

    직무 추천    NCS 소분류      정보기술개발(200102) · 일반사무(020203)
    실시간 공고   민간 자체 분류   개발/SW · 데이터/AI · 경영지원

이을 공통 키가 없어서 "이 직무와 겹친다"는 결과를 보고도 **어느 공고에
지원하면 되는지로 넘어갈 수 없다.** 진단에서 실행으로 가는 다리가 비어 있다.

**원본 표는 `overlap/evaluate/cross.py` 의 GOLD 하나뿐이다.** 교차 평가에서
"민간 공고 이 직무군은 NCS 어느 대분류로 채점하는가"를 정의한 표인데,
거꾸로 읽으면 그대로 연결표가 된다.

    개발/SW → {20}  을 뒤집으면   20(정보통신) → 개발/SW · 데이터/AI · IT인프라/보안 · 연구개발

앱 서버는 Node 라 파이썬 표를 직접 못 읽는다. **JS 쪽에 표를 베껴 두면 반드시
어긋난다** — 그래서 여기서 내보내고 서버는 그 파일만 읽는다. 표를 고칠 일이
있으면 `cross.py` 의 GOLD 를 고치고 이 스크립트를 다시 돌린다.

**한계는 대분류까지다.** 200102(정보기술개발)든 200106(정보보호)든 앞 두 자리가
같은 20 이라 결과가 같다. 정보통신 안에서 개발/데이터/보안을 가르지는 못한다.
`feat/persona` 의 `postings/ncs_link.py` 도 같은 한계를 자기 docstring 에 적어 두었다.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap.config import PATHS
from overlap.evaluate.cross import GOLD

# NCS 대분류 이름. overlap/collect/alio.py 의 NCS_MAJOR 에서 코드만 두 자리로 줄인 것.
NCS_MAJOR = {
    "01": "사업관리", "02": "경영·회계·사무", "03": "금융·보험",
    "04": "교육·자연·사회과학", "05": "법률·경찰·소방", "06": "보건·의료",
    "07": "사회복지·종교", "08": "문화·예술·디자인·방송", "09": "운전·운송",
    "10": "영업판매", "11": "경비·청소", "12": "이용·숙박·여행·오락",
    "13": "음식서비스", "14": "건설", "15": "기계", "16": "재료", "17": "화학",
    "18": "섬유·의복", "19": "전기·전자", "20": "정보통신", "21": "식품가공",
    "22": "인쇄·목재·가구", "23": "환경·에너지·안전", "24": "농림어업", "25": "연구",
}


def build() -> dict:
    major_to_jobs: dict[str, list[str]] = defaultdict(list)
    for job, codes in GOLD.items():
        for c in sorted(codes):
            major_to_jobs[c].append(job)
    return {
        "_설명": "NCS 대분류(2자리) ↔ 민간 직무군. 원본은 overlap/evaluate/cross.py 의 GOLD",
        "_한계": "대분류까지만 잇는다. 정보통신 안에서 개발/데이터/보안은 못 가른다",
        "asof": datetime.date.today().isoformat(),
        "major_names": {k: NCS_MAJOR[k] for k in sorted(major_to_jobs)},
        "major_to_jobs": {k: sorted(v) for k, v in sorted(major_to_jobs.items())},
        "job_to_majors": {j: sorted(c) for j, c in sorted(GOLD.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None,
                    help="기본값 <data>/ncs_job_families.json")
    args = ap.parse_args()

    m = build()
    out = Path(args.out or (PATHS.data / "ncs_job_families.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"직무군 {len(m['job_to_majors'])}개 · 대분류 {len(m['major_to_jobs'])}개")
    for c, jobs in m["major_to_jobs"].items():
        print(f"  {c} {m['major_names'][c]:<16} → {' · '.join(jobs)}")
    print(f"\n저장: {out}  ({out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
