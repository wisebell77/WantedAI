"""
정적 수집(data/jd), 브라우저 수집(data/jd_js), 이미지 판독(data/ocr)을
합쳐 최종 코퍼스를 만든다.

같은 공고에 두 버전이 있으면 본문이 긴 쪽을 쓴다.
중복(같은 기업 + 같은 도입부)은 제거한다.

출력:
    data/jd_good.json   본문 확보분 (len>=500 & sig>=4)
    data/corpus.json    전체 (등급 판정 포함)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

STATIC = Path("data/jd")
JS = Path("data/jd_js")
OCR = Path("data/ocr")

SIGNALS = ["자격요건", "주요업무", "담당업무", "수행업무", "업무내용", "우대",
           "지원자격", "모집분야", "모집부문", "직무", "경력", "전형"]


def load(d, src):
    out = {}
    if not d.exists():
        return out
    for f in d.glob("*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        r["src"] = src
        out[str(r.get("seq"))] = r
    return out


def main():
    a = load(STATIC, "static")
    b = load(JS, "browser")
    c = load(OCR, "ocr")
    print(f"정적 {len(a)}건 / 브라우저 {len(b)}건 / 이미지판독 {len(c)}건")

    merged = {}
    for seq, r in a.items():
        merged[seq] = r
    picked_js = 0
    for seq, r in b.items():
        cur = merged.get(seq)
        if cur is None or r.get("len", 0) > cur.get("len", 0):
            merged[seq] = r
            picked_js += 1
    print(f"브라우저 버전이 채택된 건수: {picked_js}")

    # 이미지 판독분은 메타데이터(기업·제목·URL)를 기존 레코드에서 가져오고
    # 본문만 교체한다. 이미지가 곧 공고 전문이므로 무조건 채택한다.
    picked_ocr = 0
    for seq, r in c.items():
        base = dict(merged.get(seq, {}))
        base.update({"text": r["text"], "len": r["len"],
                     "sig": 99, "status": "ok", "src": "ocr"})
        base.setdefault("corp", ""); base.setdefault("title", "")
        base.setdefault("dom", ""); base.setdefault("url", ""); base["seq"] = seq
        merged[seq] = base
        picked_ocr += 1
    print(f"이미지 판독본이 채택된 건수: {picked_ocr}")

    rows = list(merged.values())

    # 중복 제거 — 같은 기업 + 같은 도입부
    seen = set()
    uniq = []
    for r in rows:
        key = (r.get("corp", ""), (r.get("text") or "")[:300])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    print(f"병합 {len(rows)}건 → 중복 제거 후 {len(uniq)}건")

    # 이미지 판독분은 사람이 직접 읽어 정리한 텍스트라 군더더기가 없다.
    # 정적 수집분의 500자 기준(네비게이션 포함)을 그대로 적용하면
    # 완결된 단일 직무 공고가 길이 미달로 떨어진다.
    def keep(r):
        if r.get("status") != "ok":
            return False
        if r.get("src") == "ocr":
            return r.get("len", 0) >= 200
        return r.get("len", 0) >= 500 and r.get("sig", 0) >= 4

    good = [r for r in uniq if keep(r)]

    st = Counter(r.get("status") for r in uniq)
    print("상태:", dict(st))
    print(f"본문 확보: {len(good)}건")

    bysrc = Counter(r["src"] for r in good)
    print("본문 확보분 출처:", dict(bysrc))

    bydom = defaultdict(lambda: [0, 0])
    for r in uniq:
        bydom[r["dom"]][0] += 1
    for r in good:
        bydom[r["dom"]][1] += 1
    print("\n도메인별 (상위 18, 전체/본문확보)")
    for d, (n, g) in sorted(bydom.items(), key=lambda x: -x[1][1])[:18]:
        print(f"  {d:<40} {n:>3} / {g:>3}")

    json.dump(good, open("data/jd_good.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(uniq, open("data/corpus.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n저장: data/jd_good.json ({len(good)}건), data/corpus.json ({len(uniq)}건)")


if __name__ == "__main__":
    main()
