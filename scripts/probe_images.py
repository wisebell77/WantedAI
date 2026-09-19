"""
탈락분이 '이미지로 만든 공고'인지 조사한다.

본문이 비어 있는 이유가 셋 중 무엇인지 가른다.
    (a) 공고 내용을 이미지로 붙여넣음  → OCR 로 살릴 수 있다
    (b) 대문/목록 URL                 → 공고 URL 자체가 없어 불가
    (c) 첨부파일로만 안내             → 이미지 PDF, 역시 OCR 영역

판단 기준: 본문 영역 안에 가로 400px 이상인 이미지가 있고,
          그 이미지의 면적 합이 충분히 크면 '이미지형 공고'로 본다.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("data/imgprobe.json")
MIN_W = 400          # 이보다 좁으면 로고·아이콘으로 본다
MIN_AREA = 400 * 600  # 본문 이미지로 치는 최소 면적


def main():
    d = [r for r in json.loads(Path("data/corpus.json").read_text(encoding="utf-8"))
         if r.get("status") == "ok"]
    good = {r["seq"] for r in json.loads(
        Path("data/jd_good.json").read_text(encoding="utf-8"))}
    fail = sorted([r for r in d if r["seq"] not in good], key=lambda x: -x["len"])

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(fail)
    fail = fail[:limit]
    print(f"조사 대상 {len(fail)}건")

    results = []
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        ctx = br.new_context(viewport={"width": 1440, "height": 2000},
                             locale="ko-KR")
        for i, r in enumerate(fail, 1):
            rec = {"seq": r["seq"], "corp": r["corp"], "title": r["title"],
                   "url": r["url"], "len": r["len"], "dom": r["dom"]}
            pg = ctx.new_page()
            try:
                pg.goto(r["url"], wait_until="networkidle", timeout=45000)
                pg.wait_for_timeout(1200)
                imgs = pg.evaluate("""() => {
                    const out = [];
                    for (const el of document.querySelectorAll('img')) {
                      const w = el.naturalWidth || el.width;
                      const h = el.naturalHeight || el.height;
                      if (!w || !h) continue;
                      out.push({w, h, src: (el.currentSrc || el.src || '').slice(0, 200)});
                    }
                    return out;
                }""")
                big = [x for x in imgs if x["w"] >= MIN_W and x["w"] * x["h"] >= MIN_AREA]
                big.sort(key=lambda x: -(x["w"] * x["h"]))
                rec["img_total"] = len(imgs)
                rec["img_big"] = len(big)
                rec["biggest"] = big[:3]
                rec["text_len"] = len(pg.inner_text("body"))
                # 세로로 긴 이미지는 공고문을 통째로 그린 것일 확률이 높다
                rec["tall"] = sum(1 for x in big if x["h"] >= x["w"] * 1.5)
            except Exception as e:
                rec["error"] = type(e).__name__
            finally:
                pg.close()
            results.append(rec)
            if i % 10 == 0:
                print(f"  {i}/{len(fail)} …", flush=True)

        br.close()

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    cand = [r for r in results if r.get("img_big", 0) >= 1 and r.get("text_len", 0) < 1500]
    tall = [r for r in cand if r.get("tall", 0) >= 1]
    print(f"\n큰 이미지 보유 + 텍스트 빈약 : {len(cand)}건")
    print(f"  그 중 세로로 긴 이미지 포함 : {len(tall)}건  ← 공고문 이미지일 가능성 높음")
    print(f"\n저장: {OUT}")


if __name__ == "__main__":
    main()
