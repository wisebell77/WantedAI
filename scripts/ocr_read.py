"""이미지형 공고를 비전 모델로 판독한다. `ocr_prep.py` 다음, `build_corpus.py` 앞.

    python scripts/ocr_read.py                  # 미판독분 전부
    python scripts/ocr_read.py --limit 5        # 5건만
    python scripts/ocr_read.py --dry-run        # 대상만 세어 보고 호출 안 함

**여기가 파이프라인에서 유일하게 사람이 붙던 자리였다.**

    probe_images.py   이미지형 공고 판별                  자동
    ocr_prep.py       내려받아 폭 정규화 · 세로 분할        자동
    ocr_read.py       조각 → 텍스트                      <- 사람이 하던 것
    build_corpus.py   data/ocr/{seq}.json 병합            자동

이 한 칸 때문에 수집 전체가 수동이었다. 채워 두면 GitHub Actions 로 끝까지 돈다.

**왜 Tesseract 가 아니라 비전 모델인가.** 한국어 채용 포스터는 단이 나뉘고 표와
장식이 섞여 있어 전통 OCR 이 줄 순서를 자주 뒤섞는다. 뒤섞인 텍스트는 역량 추출에
쓸 수 없다 — 문장이 깨지면 임베딩이 엉뚱한 데로 간다. 비전 모델은 배치를 읽는다.

**폭은 줄이지 않는다.** `ocr_prep.py` 가 이미 1568px 로 맞춰 둔다 — 비전 모델이
더 줄이지 않는 최대 폭이고, 그 주석대로 *"1000 으로 줄이면 원본이 넓은 공고(6000px 급)의
글자가 뭉개져 판독 불가가 된다."* `--max-width` 로 더 줄일 수 있지만 토큰 몇 푼
아끼자고 판독을 망치는 거래다. 기본값은 건드리지 않는 1568 이다.

**비용.** 신규 공고만 처리하므로 주당 수십 조각이다. `--model` 로 싼 모델을 쓸 수
있고 기본값은 LLM_FAST_MODEL 이다 — 판독은 판단이 아니라 전사라 큰 모델이 필요 없다.

**지어내지 않게 한다.** 프롬프트가 요약·보완을 금지한다. 안 보이면 안 보인다고
두게 한다. 없는 문장을 채우면 그게 그대로 '공고가 요구한 역량'이 되어 버린다.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "ocr_manifest.json"
OUT_DIR = ROOT / "data" / "ocr"

PROMPT = (
    "채용공고 이미지의 일부다. 보이는 텍스트를 그대로 옮겨라.\n"
    "- 요약하거나 설명하지 마라. 원문만 옮긴다.\n"
    "- 보이지 않거나 읽을 수 없는 부분은 비워 둔다. 추측해서 채우지 마라.\n"
    "- 표는 행마다 줄을 바꿔 풀어 쓴다.\n"
    "- 장식 문구·이미지 설명·로고는 옮기지 않는다.\n"
    "- 여러 장이면 위에서 아래 순서로 이어 붙인다.\n"
    "텍스트만 출력한다."
)


def endpoint() -> str:
    return (os.getenv("LLM_BASE_URL")
            or "https://api.upstage.ai/v1/chat/completions")


def api_key() -> str:
    return os.getenv("LLM_API_KEY") or os.getenv("UPSTAGE_API_KEY") or ""


def load_env() -> None:
    """저장소 루트(또는 그 위)의 .env 를 읽는다. 이미 있는 값은 덮지 않는다."""
    for p in (ROOT / ".env", ROOT.parent / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def chunk_path(raw: str) -> Path:
    """manifest 는 Windows 에서 만들어져 역슬래시가 들어 있다.

    GitHub Actions(리눅스)에서 그대로 열면 파일을 못 찾는다.
    """
    return ROOT / raw.replace("\\", "/")


def encode(path: Path, max_width: int) -> str | None:
    """PNG → data URI. 폭이 넘치면 줄여 토큰을 아낀다."""
    try:
        from PIL import Image
    except ImportError:                       # Pillow 없으면 원본 그대로
        return "data:image/png;base64," + base64.b64encode(
            path.read_bytes()).decode()
    try:
        im = Image.open(path)
        if im.width > max_width:
            h = round(im.height * max_width / im.width)
            im = im.resize((max_width, h), Image.LANCZOS)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"    이미지 열기 실패 {path.name}: {e}", file=sys.stderr)
        return None


def ask(images: list[str], model: str, timeout: int) -> str:
    content = [{"type": "text", "text": PROMPT}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    body = {"model": model, "stream": False, "temperature": 0,
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(
        endpoint(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {api_key()}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"] or ""


def read_posting(seq: str, entry: dict, *, model: str, batch: int,
                 max_width: int, timeout: int, retries: int) -> str:
    """한 공고의 조각들을 순서대로 읽어 이어 붙인다."""
    files = [chunk_path(f) for f in entry.get("files") or []]
    files = [f for f in files if f.exists()]
    if not files:
        return ""
    parts: list[str] = []
    for i in range(0, len(files), batch):
        group = [u for u in (encode(f, max_width) for f in files[i:i + batch]) if u]
        if not group:
            continue
        for attempt in range(retries + 1):
            try:
                parts.append(ask(group, model, timeout).strip())
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:160]
                if e.code == 429 and attempt < retries:   # 속도 제한 — 물러섰다 다시
                    time.sleep(4 * (attempt + 1))
                    continue
                print(f"    HTTP {e.code} {detail}", file=sys.stderr)
                break
            except Exception as e:
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                print(f"    실패: {type(e).__name__}: {e}", file=sys.stderr)
                break
    return "\n".join(p for p in parts if p).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="처리할 공고 수 상한")
    ap.add_argument("--model", default=None,
                    help="기본값 LLM_FAST_MODEL — 판독은 전사라 큰 모델이 필요 없다")
    ap.add_argument("--batch", type=int, default=4, help="한 요청에 보낼 조각 수")
    ap.add_argument("--max-width", type=int, default=1568,
                    help="ocr_prep 이 맞춘 폭. 더 줄이면 토큰은 아끼지만 판독이 나빠진다")
    ap.add_argument("--min-length", type=int, default=200,
                    help="이보다 짧으면 판독 실패로 보고 저장하지 않는다")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--redo", action="store_true", help="이미 있는 것도 다시 읽는다")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    if not MANIFEST.exists():
        print(f"{MANIFEST} 가 없다. 먼저 scripts/ocr_prep.py 를 돌릴 것.")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = [(s, e) for s, e in manifest.items()
            if args.redo or not (OUT_DIR / f"{s}.json").exists()]
    if args.limit:
        todo = todo[:args.limit]

    chunks = sum(len(e.get("files") or []) for _, e in todo)
    print(f"manifest {len(manifest)}건 · 미판독 {len(todo)}건 · 조각 {chunks}개")
    if args.dry_run:
        for s, e in todo[:20]:
            print(f"  {s}  조각 {len(e.get('files') or []):>2}  "
                  f"{str(e.get('corp'))[:12]:<14}{str(e.get('title'))[:40]}")
        return 0
    if not todo:
        print("판독할 것이 없다.")
        return 0
    if not api_key():
        print("LLM_API_KEY(또는 UPSTAGE_API_KEY)가 없다.")
        return 1

    model = args.model or os.getenv("LLM_FAST_MODEL") or os.getenv(
        "UPSTAGE_FAST_MODEL") or "solar-mini"
    print(f"모델 {model} · 조각 {args.batch}개씩 · 폭 {args.max_width}px 로 축소\n")

    ok = short = fail = 0
    for n, (seq, entry) in enumerate(todo, 1):
        head = f"[{n}/{len(todo)}] {seq} {str(entry.get('corp'))[:12]}"
        text = read_posting(seq, entry, model=model, batch=args.batch,
                            max_width=args.max_width, timeout=args.timeout,
                            retries=args.retries)
        if not text:
            print(f"  {head}  판독 실패")
            fail += 1
            continue
        if len(text) < args.min_length:
            # 짧은 판독은 대개 표지·로고만 있는 조각이다. 남기면 usable() 을
            # 통과해 빈 공고가 코퍼스에 들어간다.
            print(f"  {head}  {len(text)}자 — 너무 짧아 버린다")
            short += 1
            continue
        (OUT_DIR / f"{seq}.json").write_text(json.dumps(
            {"seq": seq, "text": text, "len": len(text), "src": "ocr"},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {head}  {len(text)}자 저장")
        ok += 1

    print(f"\n판독 {ok}건 · 너무 짧음 {short}건 · 실패 {fail}건")
    print("다음: python scripts/build_corpus.py  (또는 pipelines/refresh_private.py --merge-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
