"""맞춤 공고 추천 데모: 내 경험 → 지금 모집 중인 공고 → (선택) 그 공고로 서류 심사·면접.

    python demo_postings.py                 # 개발 지망 예시
    python demo_postings.py --profile biz   # 경영지원 지망 예시
    python demo_postings.py --today 2026-09-12   # 기준일 바꾸기(발표 시연 재현용)
"""
import argparse
from datetime import date

from persona import llm
from postings import OpenCatalog, UserProfile, recommend_postings

PROFILES = {
    "dev": UserProfile(
        experiences=[
            "학부 캡스톤에서 C++로 산업용 카메라 영상 뷰어를 개발, 영상 획득 모듈을 맡아 초당 프레임을 12에서 30으로 개선",
            "학회에서 OpenCV와 Python으로 불량 이미지 분류 프로젝트, 전처리 파이프라인 담당",
            "자료구조 수업에서 C로 해시 테이블 구현 후 성능 비교 보고서 작성",
            "팀 프로젝트에서 Git으로 협업하며 코드 리뷰 진행",
        ],
        target_jobs=["개발/SW"], ncs_matches=["정보기술개발"], major="컴퓨터공학"),
    "biz": UserProfile(
        experiences=[
            "회계원리·재무관리 수강, 엑셀로 동아리 예산 결산표를 만들어 매월 보고",
            "학생회 사무국장으로 행사 예산 집행과 증빙 서류 관리",
            "ERP 교육 과정 수료, SAP 기초 모듈 실습",
        ],
        target_jobs=["경영지원"], major="경영학"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="dev", choices=PROFILES)
    ap.add_argument("--today")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    today = date.fromisoformat(args.today) if args.today else None
    catalog = OpenCatalog(today=today)
    print(f"LLM 사용: {llm.available()}")
    print(catalog.summary())

    res = recommend_postings(PROFILES[args.profile], catalog, limit=args.limit)
    print(f"내 경험에서 찾은 기술: {', '.join(res['user_techs']) or '-'} · 관심 직무군: {', '.join(res['user_jobs'])}\n")
    for r in res["results"]:
        dday = f"D-{r['days_left']}" if r["days_left"] is not None else "상시"
        tag = r["status"] + (f" ({', '.join(r['reasons'])})" if r["reasons"] else "")
        print(f"{r['rank']}. [{tag}] {r['corp']} · {r['role'][:40]}  ({r['job']}, {dday}, 겹침 {r['score']})")
        if r["shared_techs"]:
            print(f"   겹치는 기술: {', '.join(r['shared_techs'])}")
        for m in r["matched"][:2]:
            print(f"   공고 “{m['jd_quote'][:45]}”")
            if m["user_quote"]:
                print(f"     ↔ 내 경험 “{m['user_quote'][:45]}”")
        if "review" in r:
            rv = r["review"]
            print(f"   서류 반영도 {rv['coverage_score']}점 ({rv['generated_by']}) · 준비 필요: {', '.join(rv['to_prepare'][:3]) or '없음'}")
        print(f"   원문: {r['url']}\n   → 이 공고로 연습: python demo_persona.py --role {r['role_id']}\n")
    if res["new_without_body"]:
        print("새로 올라왔지만 본문 미수집 (제목 기준 관련):")
        for p in res["new_without_body"]:
            print(f"   {p['corp']} · {p['title']} (~{p['end']}) {p['url']}")
    print(f"\n※ {res['note']}")


if __name__ == "__main__":
    main()
