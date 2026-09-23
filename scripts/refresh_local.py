"""민간 공고를 로컬에서 수집해 배포본까지 갱신한다.

    python scripts/refresh_local.py                # 전체 (판독 포함)
    python scripts/refresh_local.py --skip-ocr     # 판독 빼고 (LLM 비용 0)
    python scripts/refresh_local.py --ocr-limit 40 # 판독을 40건만

끝나면 바뀐 파일을 커밋·푸시하라고 알려준다. **푸시는 하지 않는다** —
main 에 들어가는 순간 Railway 가 앱을 20분간 다시 굽기 때문에, 언제 나갈지는
사람이 정해야 한다.

**왜 GitHub Actions 대신 여기인가.** 자동 실행은 돌긴 하지만 결과를 확인하는
비용이 얻는 것보다 컸다. 로그를 보려면 브라우저를 열어야 하고, 중간에 끊기면
어디까지 됐는지 알기 어렵고, 크론이 예고 없이 푸시하면 심사 기간에 앱이
재빌드된다. 로컬에서 돌리면 진행이 눈앞에 있고 언제 내보낼지도 내가 정한다.
워크플로의 크론만 껐다. 수동 실행(workflow_dispatch)은 그대로 남아 있다.

단계는 워크플로와 같다. 순서가 중요하다 —

    ① 목록      공채속보에서 공고 목록을 받는다 (본문은 없다)
    ② 본문      정적 페이지에서 본문을 긁는다 (robots.txt 준수)
    ③ 본문      ②가 못 읽은 것을 브라우저로 렌더링해 긁는다
    ④ 판별      본문이 이미지뿐인 공고를 골라낸다
    ⑤ 조각      그 이미지를 판독용 조각으로 자른다
    ⑥ 판독      비전 모델로 읽는다 (여기만 API 비용이 든다)
    ⑦ 병합      수집물을 합치고 직무로 분해한다
    ⑧ 반영      줄어들지 않았을 때만 배포본에 덮어쓴다

①을 refresh_private.py 로 통째로 돌리면 안 된다. 그 스크립트는 목록 갱신과
병합을 같이 하는데, 이 시점에는 본문 캐시가 비어 있어 병합이 0 건을 내고
roles.json 을 0 개로 덮어쓴다. 그래서 목록만 갱신하고 병합은 ⑦ 에서 한다.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIV = "data/overlap/#Ubbfc#Uac04#Uacf5#Uace0"   # 한글 폴더명이 깨진 채 커밋돼 있다

# (배포본, 새로 만들어진 것) — ⑧ 에서 이 짝으로 비교한다
PAIRS = [
    ("data/gongchae_all.json", "data/overlap/gongchae_all.json"),
    ("data/roles.json",        "data/overlap/roles.json"),
    ("data/jd_good.json",      f"{PRIV}/jd_good.json"),
    ("data/corpus.json",       f"{PRIV}/corpus.json"),
    ("data/jd_tiered.json",    "data/overlap/jd_tiered.json"),
]


def load_env() -> None:
    """.env 를 찾아 읽는다. 저장소 안에 없으면 한 단계 위도 본다.

    실제 키는 저장소 밖(공모전/.env)에 두고 있다. 공개 저장소라 안에 두면
    한 번의 실수로 새어 나간다.
    """
    for path in (ROOT / ".env", ROOT.parent / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        print(f"  .env 읽음: {path}")
        return
    print("  .env 를 못 찾았다 — 환경변수에 직접 넣어 두었다면 그대로 진행한다")


def check_behind() -> None:
    """원격보다 뒤처졌으면 먼저 알려 준다.

    낡은 배포본 위에서 수집하면 ⑧ 의 "줄어들면 건너뛴다" 판정이 엉뚱한 기준으로
    돌고, 다 돌리고 나서 푸시가 거절된다. 30분 쓰고 나서 알면 늦다.
    """
    try:
        subprocess.run(["git", "fetch", "--quiet", "origin"], cwd=ROOT, timeout=60)
        out = subprocess.run(["git", "rev-list", "--count", "HEAD..origin/main"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        n = int((out.stdout or "0").strip() or 0)
    except Exception:
        return                               # 네트워크가 없으면 그냥 진행한다
    if n:
        print(f"  원격보다 {n}개 커밋 뒤처져 있다. 먼저 받아야 한다:")
        print()
        print("    git pull origin main")
        print()
        print("  낡은 배포본 위에서 수집하면 다 돌리고 나서 푸시가 거절된다.")
        sys.exit(1)


def run(label: str, args: list[str], *, required: bool = False) -> bool:
    """한 단계를 돌린다. 출력을 그대로 흘려보내 진행이 보이게 한다."""
    print(f"\n{'=' * 62}\n{label}\n{'=' * 62}", flush=True)
    started = time.time()
    code = subprocess.call([sys.executable, *args], cwd=ROOT)
    took = time.time() - started
    mark = "완료" if code == 0 else f"실패(코드 {code})"
    print(f"  → {label.split()[0]} {mark} · {took / 60:.1f}분", flush=True)
    if code != 0 and required:
        sys.exit(f"\n{label} 이 실패해서 멈춘다. 이 단계 없이는 뒤가 의미가 없다.")
    return code == 0


def count(path: str) -> int:
    try:
        data = json.loads(Path(ROOT / path).read_text(encoding="utf-8"))
        return len(data) if isinstance(data, (list, dict)) else 0
    except Exception:
        return 0


def step0_prepare() -> None:
    """배포본을 스크립트가 기대하는 자리로 옮긴다.

    수집 스크립트들이 Path("data/...") 를 하드코딩해 OVERLAP_DATA 를 보지 않는다.
    이 단계를 빼면 ② 가 data/probe/gongchae_all.json 을 못 찾아 한 건도 안 받는다.
    """
    print(f"{chr(10)}{'=' * 62}{chr(10)}⓪ 작업 공간 준비{chr(10)}{'=' * 62}")
    for d in ("data/jd", "data/jd_js", "data/ocr", "data/ocr_img", "data/probe"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    pairs = [
        ("data/overlap/gongchae_all.json", "data/gongchae_all.json"),
        ("data/overlap/gongchae_all.json", "data/probe/gongchae_all.json"),
        ("data/overlap/roles.json",        "data/roles.json"),
        ("data/overlap/jd_tiered.json",    "data/jd_tiered.json"),
        ("data/overlap/analysis.json",     "data/analysis.json"),
        ("data/overlap/imgprobe.json",     "data/imgprobe.json"),
        ("data/overlap/ocr_manifest.json", "data/ocr_manifest.json"),
        (f"{PRIV}/jd_good.json",           "data/jd_good.json"),
        (f"{PRIV}/corpus.json",            "data/corpus.json"),
    ]
    n = 0
    for src, dst in pairs:
        if (ROOT / src).exists():
            shutil.copyfile(ROOT / src, ROOT / dst); n += 1
    # 판독 결과는 덮어쓰지 않는다. 돈이 든 결과라 캐시에 더 최신이 있으면 그게 이긴다.
    kept = 0
    for f in glob.glob(str(ROOT / "data/overlap/ocr/*.json")):
        dst = ROOT / "data/ocr" / Path(f).name
        if not dst.exists():
            shutil.copyfile(f, dst); kept += 1
    print(f"  배포본 {n}개 복사 · 판독 결과 {kept}건 되살림")


def sync_probe() -> None:
    """① 이 갱신한 목록을 ② 가 읽는 자리로 옮긴다.

    **이게 빠지면 파이프라인이 한 박자 늦게 돈다.** ① 은 data/gongchae_all.json 에
    쓰고 ② 는 data/probe/gongchae_all.json 을 읽는다. 준비 단계가 복사해 둔 것은
    갱신 **전** 목록이라, 이번에 새로 들어온 공고의 본문을 한 건도 안 받는다.
    9/20 자동 실행에서 실제로 그랬다 — 공고는 542→639 로 늘었는데 본문은
    291→286 으로 줄었고, 그래서 AI 코치 가능 건수가 그대로였다.
    """
    src = ROOT / "data/gongchae_all.json"
    if src.exists():
        shutil.copyfile(src, ROOT / "data/probe/gongchae_all.json")
        print("  갱신된 목록을 data/probe/ 로 옮겼다 — ② 가 새 공고까지 받는다")


def step1_list() -> None:
    """목록만 갱신한다 (병합은 ⑦)."""
    print(f"\n{'=' * 62}\n① 공채속보 목록 갱신\n{'=' * 62}", flush=True)
    if not os.environ.get("WORK24_KEY_RECRUIT"):
        sys.exit("  WORK24_KEY_RECRUIT 이 없다. .env 에 넣고 다시 돌릴 것.")
    sys.path.insert(0, str(ROOT))
    from overlap.collect import GongchaeClient

    d = GongchaeClient().refresh()
    print(f"  total {d.total} / 누적 {d.stored}건 · 신규 {len(d.new)}건 "
          f"· 목록에서 사라짐 {d.gone}건", flush=True)


def step8_apply() -> list[str]:
    """줄어들지 않았을 때만 배포본에 반영한다.

    수집이 실패하면 병합이 0 건을 낸다. 그걸 그대로 덮어쓰고 커밋하면 앱이
    빈 목록으로 뜬다 — 첫 자동 실행에서 실제로 jd_good 0 건이 나왔다.
    """
    print(f"\n{'=' * 62}\n⑧ 배포본에 반영 (줄어들면 건너뛴다)\n{'=' * 62}")
    skipped = []
    for src, dst in PAIRS:
        ns, nd = count(src), count(dst)
        if ns == 0 or ns < nd * 0.8:            # 20% 넘게 줄면 의심한다
            print(f"  건너뜀  {dst}  새 {ns}건 / 기존 {nd}건")
            skipped.append(dst)
            continue
        shutil.copyfile(ROOT / src, ROOT / dst)
        print(f"  반영    {dst}  {nd} → {ns}건")

    # 판독 결과는 배포본에 둔다. 캐시(data/ocr)만 믿으면 지우는 순간 돈을 두 번 낸다.
    (ROOT / "data/overlap/ocr").mkdir(parents=True, exist_ok=True)
    moved = 0
    for f in glob.glob(str(ROOT / "data/ocr/*.json")):
        dst = ROOT / "data/overlap/ocr" / Path(f).name
        if not dst.exists() or os.path.getsize(f) != dst.stat().st_size:
            shutil.copyfile(f, dst)
            moved += 1
    for name in ("ocr_manifest.json", "imgprobe.json"):
        src = ROOT / "data" / name
        if src.exists():
            shutil.copyfile(src, ROOT / "data/overlap" / name)
    total_ocr = len(glob.glob(str(ROOT / "data/overlap/ocr/*.json")))
    print(f"  판독 결과 {moved}건 반영 (누적 {total_ocr}건)")
    return skipped


def summary(skipped: list[str]) -> None:
    gong = json.loads((ROOT / "data/overlap/gongchae_all.json").read_text(encoding="utf-8"))
    roles = json.loads((ROOT / "data/overlap/roles.json").read_text(encoding="utf-8"))
    today = date.today().strftime("%Y%m%d")
    live = [x for x in gong if str(x.get("empWantedEndt", "")) >= today]
    good = count(f"{PRIV}/jd_good.json")

    print(f"\n{'=' * 62}\n결과\n{'=' * 62}")
    print(f"  누적 공고    {len(gong)}건")
    print(f"  모집 중      {len(live)}건      ← 화면에 뜨는 수")
    print(f"  본문 확보    {good}건")
    print(f"  직무         {len(roles)}개")
    if skipped:
        print(f"\n  ⚠ {len(skipped)}개 파일이 줄어서 반영하지 않았다. 위 수집 로그를 볼 것.")

    changed = subprocess.run(["git", "status", "--porcelain", "data/overlap"],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not changed:
        print("\n  바뀐 것이 없다. 푸시할 필요 없다.")
        return
    n = len(changed.splitlines())
    print(f"\n  바뀐 파일 {n}개. 내보내려면:\n")
    print("    git add data/overlap")
    print(f'    git commit -m "데이터: 민간 공고 갱신 ({date.today()})"')
    print("    git push origin main")
    print("\n  푸시하면 Railway 가 앱을 다시 굽는다(약 20분). 그동안 기존 배포는 계속 돈다.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-ocr", action="store_true",
                    help="⑤⑥ 을 건너뛴다. 이미지형 공고는 본문 없이 남는다")
    ap.add_argument("--ocr-limit", type=int, default=0,
                    help="판독할 공고 수 상한 (0 = 제한 없음)")
    args = ap.parse_args()

    print(f"{'=' * 62}\n민간 공고 로컬 갱신  ·  {date.today()}\n{'=' * 62}")
    check_behind()
    load_env()
    started = time.time()

    step0_prepare()
    step1_list()
    sync_probe()
    # ②③④ 는 끊겨도 받은 만큼 쓴다. 외부 사이트가 느리거나 막는 건 흔한 일이라
    # 여기서 멈추면 아무것도 못 얻는다.
    run("② 본문 수집 (정적)", ["scripts/fetch_jd.py"])
    run("③ 본문 수집 (브라우저 렌더링)", ["scripts/fetch_jd_js.py"])
    run("④ 이미지형 공고 판별", ["scripts/probe_images.py"])

    if args.skip_ocr:
        print("\n⑤⑥ 판독 건너뜀 (--skip-ocr)")
    else:
        run("⑤ 판독용 조각 준비", ["scripts/ocr_prep.py"])
        ocr = ["scripts/ocr_read.py"]
        if args.ocr_limit:
            ocr += ["--limit", str(args.ocr_limit)]
        # **UPSTAGE_API_KEY 로 대신 돌게 두지 않는다.** ocr_read.py 는 키가 없으면
        # UPSTAGE_API_KEY 로 넘어가는데, solar-mini 는 비전 모델이 아니라 이미지를
        # 못 읽는다. 돈만 쓰고 빈 본문이 쌓이므로 차라리 건너뛴다.
        if not os.environ.get("LLM_API_KEY"):
            print()
            print("  ⑥ 을 건너뛴다 — LLM_API_KEY 가 없다.")
            print("  판독하려면 .env 에 세 줄을 넣을 것 (Railway 에 넣은 값과 같다):")
            print("      LLM_API_KEY=sk-...")
            print("      LLM_BASE_URL=https://api.openai.com/v1/chat/completions")
            print("      LLM_FAST_MODEL=gpt-5.6-terra")
        else:
            run("⑥ 이미지 판독 (비전 모델)", ocr)

    # ⑦ 은 실패하면 멈춘다. 병합이 안 됐는데 ⑧ 이 돌면 낡은 걸 그대로 덮어쓴다.
    run("⑦ 병합", ["pipelines/refresh_private.py", "--merge-only"], required=True)
    # post_tier 를 RoleSplitter 가 안 넣는다. 이걸 빼먹으면 persona 의
    # load_roles(tier="A") 가 0 개를 반환해 job_market() 의 시장 수요 가중치가 죽는다.
    run("⑦ 직무 분해 (post_tier 복구)", ["scripts/split_roles.py"], required=True)
    # jd_tiered 는 앱이 공고 본문을 읽는 유일한 통로다. 이걸 빼먹으면 본문을
    # 아무리 모아도 앱은 지난번 것만 본다 — 실제로 221건에 멈춰 있었고 그래서
    # AI 코치가 17건에만 붙었다. split_roles 와 같은 입력(jd_good)을 쓰므로
    # 순서는 상관없지만 같은 실행 안에서 반드시 같이 돈다.
    run("⑦ 공고 본문 가공 (jd_tiered)", ["scripts/build_tiered.py"], required=True)

    summary(step8_apply())
    print(f"\n  전체 {(time.time() - started) / 60:.0f}분")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
