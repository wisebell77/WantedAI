"""
수집한 채용공고 본문을 분석한다 — 어떤 직무가 많고, 어떤 역량을 요구하는가.

데모에서 무엇을 중점으로 보여줄지 정하기 위한 사전 조사다.
결론을 내는 스크립트가 아니라, 사람이 판단할 재료를 뽑는 스크립트다.

입력: data/jd_good.json  (scripts/fetch_jd.py 결과)
출력: 콘솔 리포트 + data/analysis.json
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path("data/jd_good.json")

# ── 직무 분류 (제목 + 본문 앞부분 기준, 우선순위 순서대로 검사)
JOB_RULES = [
    ("개발/SW", ["개발자", "백엔드", "프론트", "서버개발", "SW개발", "S/W", "소프트웨어",
                "프로그래머", "안드로이드", "iOS", "웹개발", "풀스택", "DevOps",
                "코어뱅킹", "임베디드", "펌웨어", "FIRMWARE", "FPGA", "애플리케이션 개발",
                "Application S/W", "Basic S/W", "SW Architect", "자율주행"]),
    ("데이터/AI", ["데이터", "AI", "인공지능", "머신러닝", "딥러닝", "ML", "빅데이터",
                 "데이터분석", "데이터엔지니", "MLOps", "LLM", "비전 AI", "AI엔지니어",
                 "Applied AI", "데이터사이언", "통계"]),
    ("IT인프라/보안", ["인프라", "네트워크", "보안", "시스템운영", "클라우드", "DBA",
                    "Cyber Security", "정보보안", "IT운영", "ERP 운영", "SAP ERP",
                    "전산", "정보기획", "IT보안", "IT Strategy"]),
    ("연구개발", ["연구", "R&D", "선행개발", "소재", "공정개발", "설계", "개발팀",
                "신약", "제제", "합성", "바이오CMC", "기술개발", "제품개발", "회로개발",
                "기구개발", "향료", "전자설계", "구조해석", "터보펌프", "추진", "GNC"]),
    ("생산/품질", ["생산", "제조", "품질", "설비", "공정", "정비", "QA", "QC", "GMP",
                "생산기술", "생산관리", "제조기술", "절개분석", "밸리데이션", "주조",
                "생산계획", "공무", "시험", "검사"]),
    ("안전/환경", ["안전", "보건", "환경", "소방", "방재", "ESG", "지속가능"]),
    ("건설/플랜트", ["건축", "토목", "시공", "플랜트", "배관", "철골", "계장", "설비시공",
                  "전기시공", "인프라 사업", "현장관리", "개발사업", "부동산"]),
    ("물류/SCM", ["물류", "SCM", "구매", "조달", "자재", "포워딩", "해상", "항공",
                "운송", "통관", "재고", "공급망", "트레이딩", "트레이더", "수출입", "배선"]),
    ("영업/마케팅", ["영업", "마케팅", "MD", "세일즈", "브랜드", "상품기획", "홍보", "PR",
                  "기술영업", "해외영업", "국내영업", "커뮤니케이션", "콘텐츠기획", "CRM"]),
    ("경영지원", ["인사", "HR", "총무", "재무", "회계", "자금", "법무", "준법",
                "경영지원", "기획", "감사", "IR", "세무", "결산", "원가", "손익",
                "예산", "경영관리", "전략", "리스크", "투자", "금융", "계리", "보상"]),
    ("디자인", ["디자인", "디자이너", "UX", "UI", "BX", "웹디자인", "영상", "편집"]),
    ("고객/서비스", ["고객", "CS", "상담", "서비스운영", "기술지원", "Trainer",
                  "고객지원", "임상운영", "임상시험", "PV", "인허가", "RA", "IPS"]),
    ("교육/공공", ["교육", "훈련", "ODA", "국제개발", "행정", "인턴", "사무행정",
                 "기관홍보", "일반행정", "사업관리", "정책"]),
]

# ── 역량 사전
TECH = ["Python", "파이썬", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go",
        "Kotlin", "Swift", "React", "Vue", "Spring", "Node", "Django",
        "SQL", "Oracle", "MySQL", "PostgreSQL", "MongoDB", "Redis",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Linux", "Git",
        "Hadoop", "Spark", "Kafka", "Airflow", "Tableau", "PowerBI",
        "TensorFlow", "PyTorch", "R", "SAS", "SPSS", "MATLAB",
        "SAP", "ERP", "Excel", "엑셀", "PPT", "AutoCAD", "CATIA", "SolidWorks",
        "Photoshop", "Illustrator", "Figma", "Premiere", "After Effects"]

LANG = ["토익", "TOEIC", "OPIc", "OPIC", "토익스피킹", "TEPS", "JLPT", "HSK",
        "영어", "중국어", "일본어"]

SOFT = ["커뮤니케이션", "협업", "문제해결", "책임감", "적극적", "꼼꼼", "성실",
        "주도적", "논리적", "분석력", "기획력", "리더십", "원활한 의사소통"]

EDU = ["학사", "석사", "박사", "전문학사", "대졸", "초대졸", "학력무관",
       "상경계열", "이공계", "관련학과", "전공자"]

EXP = ["신입", "경력", "경력무관", "인턴", "3년", "5년", "7년", "10년"]

SECTION_HEADS = ["지원자격", "자격요건", "우대사항", "우대조건", "필수사항",
                 "주요업무", "담당업무", "수행업무", "업무내용", "직무소개", "모집분야"]


def strip_boilerplate(records):
    """같은 도메인 문서의 절반 이상에 나오는 줄은 네비게이션으로 보고 지운다."""
    bydom = defaultdict(list)
    for r in records:
        bydom[r["dom"]].append(r)

    for dom, rs in bydom.items():
        if len(rs) < 3:
            continue
        cnt = Counter()
        for r in rs:
            for line in set(l.strip() for l in r["text"].split("\n")):
                if line:
                    cnt[line] += 1
        boiler = {l for l, c in cnt.items() if c >= len(rs) * 0.5 and len(l) < 60}
        for r in rs:
            r["clean"] = "\n".join(l for l in r["text"].split("\n")
                                   if l.strip() not in boiler)
    for r in records:
        r.setdefault("clean", r["text"])
    return records


def make_pat(term):
    """영문 토큰은 단어 경계를 강제한다. 'R' 이 모든 영단어에 걸리는 사고를 막는다."""
    esc = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9+#.\- ]+", term):
        tail = r"(?![A-Za-z0-9&])" if term == "R" else r"(?![A-Za-z0-9])"
        return re.compile(r"(?<![A-Za-z0-9])" + esc + tail)
    return re.compile(esc)


PATS = {}


def hit(term, text):
    if term not in PATS:
        PATS[term] = make_pat(term)
    return bool(PATS[term].search(text))


def classify(rec):
    """제목을 우선하고(가중치 10), 본문은 보조로만 쓴다."""
    title = rec["title"]
    body = rec["clean"][:4000]
    best, best_s = "분류불가", 0
    for label, kws in JOB_RULES:
        s = sum(10 for k in kws if hit(k, title)) + sum(1 for k in kws if hit(k, body))
        if s > best_s:
            best, best_s = label, s
    return best if best_s >= 2 else "분류불가"


def count_terms(records, terms, field="clean"):
    """공고 단위 등장 여부로 센다 (한 공고에 여러 번 나와도 1)."""
    c = Counter()
    for r in records:
        t = r[field]
        for term in terms:
            if hit(term, t):
                c[term] += 1
    return c


# 구체적 역량을 서술할 때 쓰이는 표현. 등급 판정에 쓴다.
EXPR = ["경험자", "경험 보유", "경험이", "능숙", "활용 능력", "활용 가능", "이해도",
        "수행 경험", "구축 경험", "운영 경험", "분석 경험", "개발 경험", "설계",
        "최적화", "자격증", "우대", "필수"]

# 직무 정보가 없는 그룹 단위 공고
GROUP = ["3급 신입사원", "대졸 신입사원 모집", "종합직", "통합직무",
         "신입사원 채용 일반전형", "하반기 신입사원 채용 공고"]


def tier(rec):
    """A: 역량이 구체적 / B: 요건만 / C: 직무 정보 없음"""
    t = rec["clean"]
    techn = sum(1 for x in TECH if hit(x, t))
    expr = sum(1 for x in EXPR if x in t)
    if any(g in rec["title"] for g in GROUP) and techn < 2 and expr < 5:
        return "C"
    if techn >= 2 or expr >= 6:
        return "A"
    if expr >= 3:
        return "B"
    return "C"


def main():
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    recs = strip_boilerplate(recs)
    n = len(recs)
    print("=" * 66)
    print(f"채용공고 본문 분석 — {n}건 / 기업 {len(set(r['corp'] for r in recs))}개")
    print("=" * 66)

    # 1) 직무 분포
    for r in recs:
        r["job"] = classify(r)
    jobs = Counter(r["job"] for r in recs)
    print("\n[1] 직무 분포")
    for j, c in jobs.most_common():
        bar = "█" * round(c / max(jobs.values()) * 30)
        print(f"  {j:<14} {c:>3}건 {bar}")

    # 2) 섹션 구조
    print("\n[2] 공고 구조 — 섹션 헤더 출현율")
    sec = count_terms(recs, SECTION_HEADS)
    for s, c in sec.most_common():
        print(f"  {s:<10} {c:>3}건 ({c/n*100:>3.0f}%)")

    # 3) 역량
    def block(title, terms, top=18):
        print(f"\n[3] {title}")
        c = count_terms(recs, terms)
        for t, v in c.most_common(top):
            if v == 0:
                continue
            print(f"  {t:<16} {v:>3}건 ({v/n*100:>3.0f}%)")
        return c

    tech = block("기술·도구", TECH)
    lang = block("어학", LANG, 10)
    edu = block("학력·전공", EDU, 10)
    exp = block("경력 요건", EXP, 10)
    soft = block("소프트스킬", SOFT, 12)

    # 4) 직무별 상위 기술
    print("\n[4] 직무별 상위 기술 (건수 5건 이상 직무만)")
    for j, c in jobs.most_common():
        if c < 5 or j == "분류불가":
            continue
        sub = [r for r in recs if r["job"] == j]
        tc = count_terms(sub, TECH)
        top = [f"{t}({v})" for t, v in tc.most_common(6) if v > 0]
        print(f"  {j:<14} n={c:<3} {', '.join(top) if top else '(기술 언급 없음)'}")

    # 5) 품질 등급
    for r in recs:
        r["tier"] = tier(r)
    tc_ = Counter(r["tier"] for r in recs)
    print("\n[5] 공고 품질 등급")
    for t, label in [("A", "역량 구체"), ("B", "요건만"), ("C", "직무정보 없음")]:
        c = tc_.get(t, 0)
        print(f"  {t} {label:<12} {c:>3}건 ({c/n*100:>3.0f}%) {'█'*round(c/n*40)}")

    print("\n[6] 직무 × 등급")
    print(f"  {'직무':<14}{'A':>4}{'B':>4}{'C':>4}   총")
    for j, c in jobs.most_common():
        sub = [r for r in recs if r["job"] == j]
        cc = Counter(x["tier"] for x in sub)
        print(f"  {j:<14}{cc.get('A',0):>4}{cc.get('B',0):>4}{cc.get('C',0):>4}   {len(sub)}")

    print("\n[7] A등급 공고 — 데모 재료")
    for r in [x for x in recs if x["tier"] == "A"]:
        ts = [t for t in TECH if hit(t, r["clean"])][:5]
        print(f"  [{r['job']:<10}] {r['corp'][:12]:<13} {r['title'][:38]:<40} "
              f"{','.join(ts)}")

    print("\n[8] 데모 후보 직무")
    print("  기준: A등급 3건 이상 + 반복 언급 기술 3종 이상")
    for j, c in jobs.most_common():
        if j == "분류불가":
            continue
        sub = [r for r in recs if r["job"] == j]
        a = sum(1 for x in sub if x["tier"] == "A")
        tcc = count_terms(sub, TECH)
        distinct = len([t for t, v in tcc.items() if v >= 2])
        mark = "⭐" if a >= 3 and distinct >= 3 else "  "
        print(f"  {mark} {j:<14} n={c:<3} A={a:<3} 반복 기술 {distinct}종")

    json.dump({
        "n": n,
        "jobs": dict(jobs),
        "tech": dict(tech),
        "lang": dict(lang),
        "edu": dict(edu),
        "exp": dict(exp),
        "soft": dict(soft),
    }, open("data/analysis.json", "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)
    print("\n저장: data/analysis.json")


if __name__ == "__main__":
    main()
