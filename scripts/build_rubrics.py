"""A등급 공고 전체의 채점표를 미리 만들어 out/rubrics/ 에 저장한다(오프라인 단계).

    python scripts/build_rubrics.py              # A등급 전체
    python scripts/build_rubrics.py --job 개발/SW --limit 5
    python scripts/build_rubrics.py --no-llm     # 키 없이 규칙 기반만

out/ 은 공고 원문 인용을 담으므로 .gitignore 로 막혀 있다.
index.json 에 채점표 목록, interview/ 에 승민 님 화상면접용 형식을 함께 쓴다.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from persona import load_or_build, load_roles, to_interview_rubric  # noqa: E402
from persona.data import ROOT  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--job")
ap.add_argument("--limit", type=int)
ap.add_argument("--no-llm", action="store_true")
ap.add_argument("--min-items", type=int, default=3, help="이보다 항목이 적으면 제외")
ap.add_argument("--refresh", action="store_true", help="저장본이 있어도 다시 만든다")
ap.add_argument("--open-only", action="store_true", help="지금 모집 중인 공고만")
args = ap.parse_args()

out_dir = os.path.join(ROOT, "out", "rubrics")
os.makedirs(os.path.join(out_dir, "interview"), exist_ok=True)
docs = [d for d in load_roles(tier=None if args.open_only else "A")
        if not args.job or d.job == args.job]
if args.open_only:
    from postings import OpenCatalog
    open_ids = {r.doc.role_id for r in OpenCatalog().roles}
    docs = [d for d in docs if d.role_id in open_ids]
docs = docs[: args.limit]

index, skipped = [], 0
for i, doc in enumerate(docs, 1):
    rub = load_or_build(doc, use_llm=not args.no_llm, refresh=args.refresh)
    if len(rub["items"]) < args.min_items:
        skipped += 1
        continue
    with open(os.path.join(out_dir, "interview", f"{doc.role_id}.json"), "w", encoding="utf-8") as f:
        json.dump(to_interview_rubric(rub), f, ensure_ascii=False, indent=2)
    index.append({"rubric_id": doc.role_id, "corp": doc.corp, "role": doc.role, "job": doc.job,
                  "items": len(rub["items"]), "generated_by": rub["generated_by"]})
    print(f"[{i}/{len(docs)}] {doc.corp} · {doc.role[:30]} → {len(rub['items'])}항목 ({rub['generated_by']})")

with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
print(f"\n저장 {len(index)}건 · 항목 부족으로 제외 {skipped}건 → {out_dir}")
