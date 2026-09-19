"""
공고를 직무 단위로 쪼갠다.

공고 하나가 직무 여러 개를 담는 경우가 많아(이미지 공고는 평균 2.8개),
'공고 1건 = 직무 1개'로 세면 분포가 왜곡된다.
역방향 매칭(F3)은 직무 단위로 계산하므로 이 단위가 맞다.

방법: '주요업무/담당업무/수행업무/직무상세' 표제를 앵커로 잡고,
     앵커 직전의 짧은 줄을 직무명으로, 다음 앵커까지를 그 직무의 본문으로 본다.
     앵커가 없으면 공고 전체를 직무 1개로 본다.

이건 휴리스틱이다. 정확한 분해는 LLM 이 할 일이고,
여기서는 분포를 가늠하기 위한 근사치를 낸다.

출력: data/roles.json + 콘솔 분포표
"""

import json
import re
from collections import Counter
from pathlib import Path

from analyze_jd import strip_boilerplate, classify, tier, TECH, hit

SRC = Path("data/jd_good.json")
OUT = Path("data/roles.json")

ANCHOR = re.compile(
    r"(주요\s?업무(?:내용)?|담당\s?업무|담당\s?직무|수행\s?업무|직무\s?상세(?:설명)?"
    r"|세부업무내용|핵심\s?업무|업무\s?내용|직무소개)\s*[:：]?"
)

# 직무명으로 보기에 부적절한 줄
#  - 표 헤더("모집분야 (부문 / 직무 /"), 주소, 날짜, 공고 제목, 안내 문구
NOISE = re.compile(
    r"^(https?://"
    r"|[-=·•▪■□○◎※*]+$"
    r"|\d[\d\s.\-~년월일]*$"
    r"|.{0,1}$"
    r"|.*[(/]\s*(부문|직무|구분|신입|경력|모집|담당|자격)\s*[/)]"      # 표 헤더
    r"|(모집|채용|전형|지원|응시|접수|근무|학력|전공|우대|필수)[\s가-힣]*[:：(]"
    r"|.*(대한민국|특별시|광역시|[가-힣]+시\s|[가-힣]+구\s|[가-힣]+로\d)"  # 주소
    r"|.*(채용\s?공고|신입사원\s?(채용|모집)|인재\s?모집|수시채용|공개채용|공동채용)"
    r"|※.*|\[.*\]$"
    r")")


def role_name(before: str) -> str:
    """앵커 직전 텍스트에서 직무명으로 쓸 짧은 줄을 고른다."""
    lines = [l.strip(" ·•-–—■□○●[]()") for l in before.split("\n")]
    for l in reversed(lines[-6:]):
        if not l or NOISE.match(l):
            continue
        if 2 <= len(l) <= 40:
            return l
    return ""


def split_one(rec):
    t = rec["clean"]
    hits = list(ANCHOR.finditer(t))
    if not hits:
        return [{"role": rec["title"][:40], "text": t}]

    out = []
    for i, m in enumerate(hits):
        start = m.start()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(t)
        name = role_name(t[max(0, start - 400):start])
        out.append({"role": name or rec["title"][:40], "text": t[start:end]})
    return out


def main():
    recs = strip_boilerplate(json.loads(SRC.read_text(encoding="utf-8")))
    roles = []
    for r in recs:
        r["tier"] = tier(r)
        for piece in split_one(r):
            techs = [x for x in TECH if hit(x, piece["text"])]
            fake = {"title": piece["role"], "clean": piece["text"]}
            roles.append({
                "corp": r.get("corp", ""),
                "post_title": r.get("title", ""),
                "post_tier": r["tier"],
                "role": piece["role"],
                "job": classify(fake),
                "techs": techs,
                # 직무별 본문. 근거 문장을 이 안에서만 찾아야
                # 다른 직무의 문장이 근거로 붙는 일이 없다.
                "text": piece["text"],
                "len": len(piece["text"]),
                "src": r.get("src", ""),
                "url": r.get("url", ""),
            })

    OUT.write_text(json.dumps(roles, ensure_ascii=False, indent=1), encoding="utf-8")

    n_post, n_role = len(recs), len(roles)
    print("=" * 62)
    print(f"공고 {n_post}건 → 직무 {n_role}개 (공고당 {n_role / n_post:.1f})")
    print("=" * 62)

    jobs = Counter(r["job"] for r in roles)
    post_jobs = Counter(classify(r) for r in recs)
    mx = max(jobs.values())

    print(f"\n{'직무':<14}{'직무수':>6}{'공고수':>6}   분포")
    print("-" * 62)
    for j, c in jobs.most_common():
        bar = "█" * round(c / mx * 26)
        print(f"{j:<14}{c:>6}{post_jobs.get(j, 0):>6}   {bar}")
    print("-" * 62)
    print(f"{'합계':<14}{n_role:>6}{n_post:>6}")

    # 기술이 붙은 직무만 따로
    print(f"\n기술·도구가 1개 이상 언급된 직무: "
          f"{sum(1 for r in roles if r['techs'])}개")
    print(f"\n{'직무':<14}{'기술언급':>7}{'비율':>7}")
    print("-" * 32)
    for j, c in jobs.most_common():
        w = sum(1 for r in roles if r["job"] == j and r["techs"])
        print(f"{j:<14}{w:>7}{w / c * 100:>6.0f}%")

    print(f"\n저장: {OUT}")


if __name__ == "__main__":
    main()
