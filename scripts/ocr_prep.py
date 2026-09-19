"""
이미지형 공고를 판독 가능한 조각으로 준비한다.

data/imgprobe.json 에서 '공고문 이미지' 후보를 골라
    → 이미지 다운로드
    → 폭 1000px 로 정규화
    → 세로 2200px 단위로 분할
    → data/ocr_img/{seq}_{i}.png 로 저장
    → data/ocr_manifest.json 에 목록 기록

판독(이미지 → 텍스트)은 이 스크립트가 하지 않는다.
사람이 조각을 읽어 data/ocr/{seq}.json 에 넣으면 build_corpus 가 병합한다.

사용법:
    python scripts/ocr_prep.py 15      # 우선순위 상위 15건만 준비
    python scripts/ocr_prep.py         # 전부
"""

import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

OUT_IMG = Path("data/ocr_img")
MANIFEST = Path("data/ocr_manifest.json")
WIDTH = 1568      # Claude 가 이미지를 축소하지 않는 최대 폭. 1000 으로 줄이면
                  # 원본이 넓은 공고(6000px 급)의 글자가 뭉개져 판독 불가가 된다.
CHUNK_H = 1500
UA = "Mozilla/5.0 (compatible; OverlapResearch/0.1; student contest research)"

# 역방향 매칭의 병목이 IT·연구개발이므로 그쪽을 먼저 판독한다.
PRIORITY = ["세미콘", "로템", "엘아이지", "뷰웍스", "인터내셔널", "글로비스",
            "솔루션", "에스티", "디펜스", "일렉트릭", "이노베", "시스템",
            "소프트", "테크", "전자", "반도체"]


def biggest(rec):
    b = rec.get("biggest") or []
    if not b:
        return None
    return max(b, key=lambda x: x["w"] * x["h"])


def priority_key(rec):
    hay = rec["corp"] + " " + rec["title"]
    for i, k in enumerate(PRIORITY):
        if k in hay:
            return (0, i)
    return (1, 0)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    probe = json.loads(Path("data/imgprobe.json").read_text(encoding="utf-8"))

    cand = []
    seen = set()
    for r in probe:
        b = biggest(r)
        if not b or b["h"] < 1500 or r.get("text_len", 0) >= 1500:
            continue
        if not b["src"].startswith("http") or r["url"] in seen:
            continue
        seen.add(r["url"])
        cand.append(r)

    cand.sort(key=priority_key)
    if limit:
        cand = cand[:limit]
    print(f"준비 대상 {len(cand)}건")

    OUT_IMG.mkdir(parents=True, exist_ok=True)
    done = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}

    for n, r in enumerate(cand, 1):
        seq = str(r["seq"])
        if seq in done:
            continue
        src = biggest(r)["src"]
        try:
            raw = requests.get(src, timeout=90, headers={"User-Agent": UA}).content
            im = Image.open(io.BytesIO(raw))
            # 팔레트 PNG + 투명도인 경우가 있다. 그냥 RGB 로 바꾸면 투명 픽셀이
            # 검게 깔려 글자가 배경에 묻힌다. 반드시 흰 배경에 합성해야 한다.
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, rgba).convert("RGB")
            w, h = im.size
            if w != WIDTH:
                im = im.resize((WIDTH, max(1, int(h * WIDTH / w))), Image.LANCZOS)
            w, h = im.size
            parts = max(1, -(-h // CHUNK_H))
            files = []
            for i in range(parts):
                top, bot = h * i // parts, h * (i + 1) // parts
                p = OUT_IMG / f"{seq}_{i}.png"
                im.crop((0, top, w, bot)).save(p)
                files.append(str(p))
            done[seq] = {"corp": r["corp"], "title": r["title"], "url": r["url"],
                         "img": src, "size": [w, h], "files": files}
            print(f"  [{n:>2}] {r['corp'][:16]:<16} {h:>6}px → {parts}장")
        except Exception as e:
            print(f"  [{n:>2}] {r['corp'][:16]:<16} 실패 {type(e).__name__}")

    MANIFEST.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(v["files"]) for v in done.values())
    print(f"\n매니페스트 {len(done)}건 / 조각 {total}장 → {MANIFEST}")


if __name__ == "__main__":
    main()
