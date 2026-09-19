"""
정적 추출에 실패한 공고를 브라우저로 렌더링해 다시 수집한다.

scripts/fetch_jd.py 가 남긴 캐시 중 본문을 못 건진 것만 대상으로 한다.
recruiter.co.kr 계열, 현대·LG·HD 등이 여기 해당한다.

브라우저 바이너리는 D 드라이브에 있다:
    set PLAYWRIGHT_BROWSERS_PATH=D:\\playwright-browsers

사용법:
    python scripts/fetch_jd_js.py
"""

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"D:\playwright-browsers")
from playwright.sync_api import sync_playwright  # noqa: E402

SRC_CACHE = Path("data/jd")
OUT = Path("data/jd_js")
UA = "Mozilla/5.0 (compatible; OverlapResearch/0.1; student contest research)"
SIGNALS = ["자격요건", "주요업무", "담당업무", "수행업무", "업무내용", "우대",
           "지원자격", "모집분야", "모집부문", "직무", "경력", "전형"]
DELAY = 1.0
NAV_TIMEOUT = 30000


def score(t):
    return sum(1 for k in SIGNALS if k in t)


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


def targets():
    """정적 수집에서 본문을 못 건진 것들."""
    out = []
    for f in sorted(SRC_CACHE.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["status"] == "robots차단":
            continue
        good = r.get("len", 0) >= 800 and r.get("sig", 0) >= 4
        if good:
            continue
        out.append(r)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = targets()
    print(f"재수집 대상 {len(items)}건")
    bydom = defaultdict(int)
    for r in items:
        bydom[r["dom"]] += 1
    print("상위 도메인:", dict(sorted(bydom.items(), key=lambda x: -x[1])[:8]))

    done = ok = good = 0
    last = defaultdict(float)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, locale="ko-KR",
                                  viewport={"width": 1280, "height": 900},
                                  ignore_https_errors=True)
        ctx.set_default_timeout(NAV_TIMEOUT)

        for i, r in enumerate(items, 1):
            f = OUT / f"{r['seq']}.json"
            if f.exists():
                rec = json.loads(f.read_text(encoding="utf-8"))
                done += 1
                if rec["status"] == "ok":
                    ok += 1
                    if rec["len"] >= 800 and rec["sig"] >= 4:
                        good += 1
                continue

            if not allowed(r["url"]):
                rec = {**r, "status": "robots차단", "text": "", "len": 0, "sig": 0}
            else:
                wait = DELAY - (time.time() - last[r["dom"]])
                if wait > 0:
                    time.sleep(wait)
                page = ctx.new_page()
                try:
                    page.goto(r["url"], wait_until="domcontentloaded",
                              timeout=NAV_TIMEOUT)
                    try:
                        page.wait_for_load_state("networkidle", timeout=12000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1200)
                    txt = page.inner_text("body")
                    txt = re.sub(r"[ \t\xa0]+", " ", txt)
                    txt = re.sub(r"\n{2,}", "\n", txt).strip()
                    rec = {**r, "status": "ok", "text": txt,
                           "len": len(txt), "sig": score(txt)}
                    ok += 1
                    if rec["len"] >= 800 and rec["sig"] >= 4:
                        good += 1
                except Exception as e:
                    rec = {**r, "status": type(e).__name__,
                           "text": "", "len": 0, "sig": 0}
                finally:
                    last[r["dom"]] = time.time()
                    page.close()

            f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(items)}  수신 {ok} / 본문확보 {good}")

        browser.close()

    print(f"\n완료: 대상 {len(items)} / 수신 {ok} / 본문확보 {good}")


if __name__ == "__main__":
    main()
