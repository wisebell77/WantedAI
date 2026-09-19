"""
공채속보 URL에서 채용공고 본문을 수집한다.

원칙:
    - robots.txt 를 URL 단위로 매번 확인하고, 거부하면 건너뛴다.
    - CLAUDE.md 금지 플랫폼(원티드·사람인·잡코리아·링커리어)과
      인크루트 계열은 도메인 단계에서 제외한다.
    - 한 번 받은 페이지는 data/jd/ 에 캐싱해 재요청하지 않는다.
    - 도메인당 요청 간격을 둔다.

사용법:
    python scripts/fetch_jd.py           # 수집 + 추출
    python scripts/fetch_jd.py --report  # 캐시만 읽어 결과 요약
"""

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SRC = Path("data/probe/gongchae_all.json")
CACHE = Path("data/jd")
UA = "Mozilla/5.0 (compatible; OverlapResearch/0.1; student contest research)"
DELAY = 0.8

# 본문 확보 판정 기준. 핵심 신호 2개 이상이면 score 가 4를 보장하므로,
# 길이는 짧아도 완전한 공고(응시자격+우대사항까지 있는 500자대)를 놓치지 않는다.
MIN_LEN = 500
MIN_SIG = 4

# CLAUDE.md 금지 목록 + 채용 플랫폼 ATS(보수적으로 제외)
BANNED = ("wanted.co.kr", "saramin.co.kr", "jobkorea.co.kr", "linkareer.com",
          "incruit.com", "careerlink.kr")

# 이 페이지가 채용공고 본문인지 판단하는 관문.
# 품질 판정이 아니라 "공고 페이지가 맞나"를 거른다.
#
# 개수만 세면 안 된다. 주요업무 + 자격요건 + 우대사항 세 개를 갖춘 공고가
# 잡다한 단어 다섯 개가 흩어진 페이지보다 낮은 점수를 받는 일이 생긴다.
# 그래서 핵심 신호와 보조 신호를 나눈다.

# 이 섹션 제목이 둘 이상 있으면 채용공고가 확실하다.
CORE = ["주요업무", "담당업무", "수행업무", "업무내용", "직무소개",
        "자격요건", "지원자격", "응시자격", "필수사항", "필수역량",
        "우대사항", "우대조건", "우대요건",
        "모집분야", "모집부문", "채용분야", "모집요강"]

# 혼자서는 근거가 약한 표현들. 요즘 공고의 구어체도 여기 둔다.
AUX = ["직무", "경력", "전형", "근무조건", "근무형태", "우대",
       "이런 분", "함께 할", "함께하실", "합류", "찾습니다", "소개합니다"]

SIGNALS = CORE + AUX   # 하위 호환용


def load_urls():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        u = r.get("empWantedHomepgDetail", "")
        if not u.startswith("http"):
            continue
        dom = urlparse(u).netloc
        if any(b in dom for b in BANNED):
            continue
        out.append({
            "url": u,
            "dom": dom,
            "title": r.get("empWantedTitle", ""),
            "corp": r.get("empBusiNm", ""),
            "coClcd": r.get("coClcdNm", ""),
            "seq": r.get("empSeqno", ""),
        })
    return out


_robots = {}


def allowed(url):
    dom = urlparse(url).netloc
    if dom not in _robots:
        rp = RobotFileParser()
        try:
            r = requests.get(f"https://{dom}/robots.txt", timeout=8,
                             headers={"User-Agent": UA})
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[dom] = rp
    try:
        return _robots[dom].can_fetch("*", url)
    except Exception:
        return True


def extract(html):
    """DOM 텍스트를 우선 쓰고, 비면 스크립트에 박힌 JSON 문자열을 훑는다."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["style", "noscript", "svg"]):
        t.decompose()
    for t in soup(["script"]):
        t.extract()
    txt = soup.get_text("\n")
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    txt = re.sub(r"\n{2,}", "\n", txt).strip()

    if len(txt) < 500:
        # __NEXT_DATA__ / JSON-LD / 인라인 JSON 안의 한글 문장을 긁는다
        blobs = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
        pool = []
        for b in blobs:
            for m in re.findall(r'"([^"]{40,})"', b):
                s = m.encode("utf-8", "ignore").decode("unicode_escape", "ignore")
                if re.search(r"[가-힣]", s) and len(s) > 40:
                    pool.append(re.sub(r"<[^>]+>", " ", s))
        if pool:
            alt = re.sub(r"\s{2,}", " ", "\n".join(dict.fromkeys(pool)))
            if len(alt) > len(txt):
                txt = alt
    return txt


def compact(txt):
    """공백을 전부 지운 사본. 공고는 '주요 업무'로 쓰고 사전은 '주요업무'라
    붙여 쓰므로, 띄어쓰기 차이로 놓치는 일을 막는다."""
    return re.sub(r"\s+", "", txt)


def score(txt):
    """핵심 신호 2개 이상이면 그것만으로 충분하다고 본다.
    반환값은 (총점, 핵심개수) 중 총점 — 하위 호환을 위해 정수 하나만 준다.
    핵심 2개 이상이면 최소 4점을 보장해 기준선을 통과시킨다."""
    c = compact(txt)
    core = sum(1 for k in CORE if compact(k) in c)
    aux = sum(1 for k in AUX if compact(k) in c)
    if core >= 2:
        return max(4, core + aux)
    return core + aux


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    items = load_urls()
    print(f"대상 {len(items)}건 (금지 플랫폼 제외 후)")

    report_only = "--report" in sys.argv
    last_hit = defaultdict(float)
    results = []

    for i, it in enumerate(items, 1):
        f = CACHE / f"{it['seq']}.json"
        if f.exists():
            results.append(json.loads(f.read_text(encoding="utf-8")))
            continue
        if report_only:
            continue

        if not allowed(it["url"]):
            rec = {**it, "status": "robots차단", "text": "", "len": 0, "sig": 0}
        else:
            wait = DELAY - (time.time() - last_hit[it["dom"]])
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(it["url"], timeout=15, headers={"User-Agent": UA})
                last_hit[it["dom"]] = time.time()
                if r.status_code != 200:
                    rec = {**it, "status": f"HTTP{r.status_code}", "text": "", "len": 0, "sig": 0}
                else:
                    # apparent_encoding(추측)에 맡기면 한글이 깨진다.
                    # 실제로 13건이 모지바케로 들어왔다.
                    # 서버가 밝힌 charset → 문서 meta → UTF-8 순으로 신뢰한다.
                    ct = (r.headers.get("Content-Type") or "").lower()
                    m = re.search(r"charset=([\w\-]+)", ct)
                    if m:
                        r.encoding = m.group(1)
                    else:
                        head = r.content[:2048].decode("ascii", "ignore").lower()
                        m2 = re.search(r'charset=["\']?([\w\-]+)', head)
                        r.encoding = m2.group(1) if m2 else "utf-8"
                    txt = extract(r.text)
                    rec = {**it, "status": "ok", "text": txt, "len": len(txt), "sig": score(txt)}
            except Exception as e:
                rec = {**it, "status": type(e).__name__, "text": "", "len": 0, "sig": 0}

        f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        results.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(items)} …")

    # ── 요약
    ok = [r for r in results if r["status"] == "ok"]
    good = [r for r in ok if r["len"] >= MIN_LEN and r["sig"] >= MIN_SIG]
    print(f"\n수신 성공 {len(ok)}건 / 본문 확보 {len(good)}건")
    st = defaultdict(int)
    for r in results:
        st[r["status"]] += 1
    print("상태:", dict(st))

    bydom = defaultdict(lambda: [0, 0])
    for r in results:
        bydom[r["dom"]][0] += 1
        if r in good:
            bydom[r["dom"]][1] += 1
    print("\n도메인별 (상위 15, 전체/본문확보)")
    for d, (n, g) in sorted(bydom.items(), key=lambda x: -x[1][0])[:15]:
        print(f"  {d:<38} {n:>3} / {g:>3}")

    json.dump(good, open("data/jd_good.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n본문 확보분 저장: data/jd_good.json ({len(good)}건)")


if __name__ == "__main__":
    main()
