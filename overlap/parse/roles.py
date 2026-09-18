"""민간 공고 본문 → 직무 단위.

공고 하나가 직무 여럿을 담는 경우가 많다(이미지형 공고는 평균 2.8개).
'공고 1건 = 직무 1개'로 세면 분포가 왜곡되고, 역방향 매칭도 직무 단위로
계산하므로 이 단위가 맞다. 실측 285공고 → 510직무.

분해 방법
    `주요업무/담당업무/수행업무/직무상세` 표제를 앵커로 잡는다.
    앵커 직전의 짧은 줄이 직무명, 다음 앵커까지가 그 직무의 본문이다.
    앵커가 없으면 공고 전체를 직무 하나로 본다.

    이건 휴리스틱이다. 정확한 분해는 LLM 의 몫이고 여기서는 근사치를 낸다.
    다만 본문을 직무별로 잘라 두는 건 정확도 문제가 아니라 원칙 문제다 —
    근거 문장을 직무 본문 안에서만 찾아야 다른 직무의 문장이 근거로 붙지 않는다.

본문 정리
    같은 도메인 문서의 절반 이상에 나오는 줄은 네비게이션·푸터로 보고 지운다.
    도메인당 3건 이상일 때만 판단한다. 2건으로 '절반 이상'을 재면
    우연히 겹친 본문 줄까지 지워 버린다.

직무 분류(job)는 민간 자체 라벨이다. NCS 가 아니다.
교차 평가(evaluate.cross)에서 NCS 대분류 묶음에 대응시켜 정답으로 쓴다.
제목에 가중치 10, 본문은 1 — 본문에는 다른 직무 얘기가 섞이기 때문이다.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

JOB_RULES: list[tuple[str, list[str]]] = [
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

TECH = ["Python", "파이썬", "Java", "JavaScript", "TypeScript", "C++", "C#", "Go",
        "Kotlin", "Swift", "React", "Vue", "Spring", "Node", "Django",
        "SQL", "Oracle", "MySQL", "PostgreSQL", "MongoDB", "Redis",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Linux", "Git",
        "Hadoop", "Spark", "Kafka", "Airflow", "Tableau", "PowerBI",
        "TensorFlow", "PyTorch", "R", "SAS", "SPSS", "MATLAB",
        "SAP", "ERP", "Excel", "엑셀", "PPT", "AutoCAD", "CATIA", "SolidWorks",
        "Photoshop", "Illustrator", "Figma", "Premiere", "After Effects"]

ANCHOR = re.compile(
    r"(주요\s?업무(?:내용)?|담당\s?업무|담당\s?직무|수행\s?업무|직무\s?상세(?:설명)?"
    r"|세부업무내용|핵심\s?업무|업무\s?내용|직무소개)\s*[:：]?")

# 직무명으로 보기에 부적절한 줄 — 표 헤더·주소·날짜·공고 제목·안내 문구
NOISE = re.compile(
    r"^(https?://"
    r"|[-=·•▪■□○◎※*]+$"
    r"|\d[\d\s.\-~년월일]*$"
    r"|.{0,1}$"
    r"|.*[(/]\s*(부문|직무|구분|신입|경력|모집|담당|자격)\s*[/)]"
    r"|(모집|채용|전형|지원|응시|접수|근무|학력|전공|우대|필수)[\s가-힣]*[:：(]"
    r"|.*(대한민국|특별시|광역시|[가-힣]+시\s|[가-힣]+구\s|[가-힣]+로\d)"
    r"|.*(채용\s?공고|신입사원\s?(채용|모집)|인재\s?모집|수시채용|공개채용|공동채용)"
    r"|※.*|\[.*\]$"
    r")")

_PATS: dict[str, re.Pattern] = {}


def term_pattern(term: str) -> re.Pattern:
    """영문 토큰은 단어 경계를 강제한다. `R` 이 모든 영단어에 걸리는 사고를 막는다."""
    esc = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9+#.\- ]+", term):
        tail = r"(?![A-Za-z0-9&])" if term == "R" else r"(?![A-Za-z0-9])"
        return re.compile(r"(?<![A-Za-z0-9])" + esc + tail)
    return re.compile(esc)


def mentions(term: str, text: str) -> bool:
    if term not in _PATS:
        _PATS[term] = term_pattern(term)
    return bool(_PATS[term].search(text))


@dataclass
class Role:
    """민간 공고에서 떼어낸 직무 하나."""

    corp: str
    role: str
    text: str
    job: str = ""                                     # 민간 자체 분류
    post_title: str = ""
    techs: list[str] = field(default_factory=list)
    url: str = ""
    src: str = ""

    def to_dict(self) -> dict:
        return {"corp": self.corp, "role": self.role, "job": self.job,
                "post_title": self.post_title, "techs": self.techs,
                "text": self.text, "len": len(self.text),
                "url": self.url, "src": self.src}


class BoilerplateStripper:
    """도메인별 공통 줄을 지운다. 호출자는 {'dom','text'} 를 가진 레코드를 준다."""

    def __init__(self, min_docs: int = 3, share: float = 0.5,
                 max_line: int = 60):
        self.min_docs, self.share, self.max_line = min_docs, share, max_line

    def __call__(self, records: list[dict]) -> list[dict]:
        nl = chr(10)
        bydom = defaultdict(list)
        for r in records:
            bydom[r.get("dom", "")].append(r)
        for rs in bydom.values():
            if len(rs) < self.min_docs:
                continue
            cnt: Counter = Counter()
            for r in rs:
                for line in {l.strip() for l in r["text"].split(nl)}:
                    if line:
                        cnt[line] += 1
            boiler = {l for l, c in cnt.items()
                      if c >= len(rs) * self.share and len(l) < self.max_line}
            for r in rs:
                r["clean"] = nl.join(l for l in r["text"].split(nl)
                                     if l.strip() not in boiler)
        for r in records:
            r.setdefault("clean", r["text"])
        return records


class JobClassifier:
    """제목 우선(가중치 10), 본문 보조(1). 근거가 약하면 분류불가로 둔다."""

    def __init__(self, rules=JOB_RULES, min_score: int = 2):
        self.rules, self.min_score = rules, min_score

    def __call__(self, title: str, body: str = "") -> str:
        best, best_s = "분류불가", 0
        body = (body or "")[:4000]
        for label, kws in self.rules:
            s = (sum(10 for k in kws if mentions(k, title))
                 + sum(1 for k in kws if mentions(k, body)))
            if s > best_s:
                best, best_s = label, s
        return best if best_s >= self.min_score else "분류불가"


class RoleSplitter:
    """공고 레코드 목록 → Role 목록.

    >>> rs = RoleSplitter()
    >>> roles = rs.split_all(records)
    >>> roles[0].job
    '데이터/AI'
    """

    def __init__(self, classifier: JobClassifier | None = None,
                 stripper: BoilerplateStripper | None = None):
        self.classify = classifier or JobClassifier()
        self.strip = stripper or BoilerplateStripper()

    def role_name(self, before: str) -> str:
        """앵커 직전 텍스트에서 직무명으로 쓸 짧은 줄을 고른다."""
        lines = [l.strip(" ·•-–—■□○●[]()") for l in before.split(chr(10))]
        for l in reversed(lines[-6:]):
            if l and not NOISE.match(l) and 2 <= len(l) <= 40:
                return l
        return ""

    def split_one(self, rec: dict) -> list[Role]:
        text = rec.get("clean") or rec.get("text", "")
        title = rec.get("title", "")
        hits = list(ANCHOR.finditer(text))
        pieces = []
        if not hits:
            pieces.append((title[:40], text))
        else:
            for i, m in enumerate(hits):
                end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
                name = self.role_name(text[max(0, m.start() - 400):m.start()])
                pieces.append((name or title[:40], text[m.start():end]))
        return [Role(corp=rec.get("corp", ""), role=n, text=t,
                     job=self.classify(n, t), post_title=title,
                     techs=[x for x in TECH if mentions(x, t)],
                     url=rec.get("url", ""), src=rec.get("src", ""))
                for n, t in pieces]

    def split_all(self, records: list[dict]) -> list[Role]:
        out = []
        for r in self.strip(records):
            out += self.split_one(r)
        return out
