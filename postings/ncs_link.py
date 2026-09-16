"""직무추천(NCS) 결과 → 민간 직무군 연결.

기준표는 직무추천 파트의 `overlap/evaluate/cross.py` 의 GOLD
(민간 자체 분류 → 허용 NCS 대분류 코드)를 그대로 쓴다.
recommendation 브랜치가 합쳐져 있으면 그 표를 직접 불러오고,
아니면 아래 사본(2026-09-16 기준)을 쓴다. 표를 고칠 때는 추천 파트 쪽을 고친다.

연결 방법: 소분류 코드(6자리)의 앞 2자리 = 대분류 → GOLD 를 거꾸로 찾는다.
    200102 (정보기술개발) → 20 정보통신 → 개발/SW · 데이터/AI · IT인프라/보안 · 연구개발
한계(추천 파트 README 와 동일): 대분류까지만 이어진다. 정보통신 안에서
개발/데이터/보안 중 어디인지는 가르지 못한다.
"""
from __future__ import annotations

try:  # 추천 파트 코드가 있으면 원본 표 사용
    from overlap.evaluate.cross import GOLD as _GOLD  # type: ignore
    SOURCE = "overlap.evaluate.cross.GOLD"
except Exception:
    _GOLD = {
        "개발/SW": {"20"}, "데이터/AI": {"20"}, "IT인프라/보안": {"20"},
        "경영지원": {"02", "01"},
        "생산/품질": {"15", "16", "17", "19"},
        "안전/환경": {"23"},
        "영업/마케팅": {"10", "02"},
        "건설/플랜트": {"14"},
        "물류/SCM": {"09", "02"},
        "연구개발": {"15", "16", "17", "19", "20"},
        "디자인": {"08"},
    }
    SOURCE = "GOLD 사본 (recommendation 브랜치 cross.py, 09-16)"

GOLD: dict[str, set[str]] = _GOLD

# NCS 대분류 이름 (추천 파트 collect/alio.py 의 NCS_MAJOR 에서 코드만 두 자리로)
NCS_MAJOR = {
    "01": "사업관리", "02": "경영.회계.사무", "03": "금융.보험", "04": "교육.자연.사회과학",
    "05": "법률.경찰.소방", "06": "보건.의료", "07": "사회복지.종교", "08": "문화.예술.디자인.방송",
    "09": "운전.운송", "10": "영업판매", "11": "경비.청소", "12": "이용.숙박.여행.오락",
    "13": "음식서비스", "14": "건설", "15": "기계", "16": "재료", "17": "화학", "18": "섬유.의복",
    "19": "전기.전자", "20": "정보통신", "21": "식품가공", "22": "인쇄.목재.가구",
    "23": "환경.에너지.안전", "24": "농림어업", "25": "연구",
}

MAJOR_TO_JOBS: dict[str, list[str]] = {}
for _job, _codes in GOLD.items():
    for _c in _codes:
        MAJOR_TO_JOBS.setdefault(_c, []).append(_job)


def _code_name(item) -> tuple[str, str]:
    """문자열 코드/이름, dict({code,name}), JobMatch 객체를 모두 받는다."""
    if isinstance(item, dict):
        return str(item.get("code", "")), str(item.get("name", ""))
    if hasattr(item, "code"):
        return str(item.code), str(getattr(item, "name", ""))
    s = str(item).strip()
    return (s, "") if s.isdigit() else ("", s)


def _norm(s: str) -> str:
    return s.replace(".", "").replace("·", "").replace(" ", "")


def link(items) -> list[dict]:
    """직무추천 결과 목록 → [{ncs, major, jobs, how}]"""
    out = []
    for item in items or []:
        code, name = _code_name(item)
        major = code[:2] if len(code) >= 2 else ""
        how = "코드"
        if not major and name:  # 코드가 없으면 대분류 이름과 비교
            major = next((c for c, n in NCS_MAJOR.items()
                          if _norm(n) in _norm(name) or _norm(name) in _norm(n)), "")
            how = "대분류 이름"
        jobs = MAJOR_TO_JOBS.get(major, [])
        out.append({"ncs": name or code, "code": code, "major": major,
                    "major_name": NCS_MAJOR.get(major, ""), "jobs": jobs,
                    "how": how if jobs else "연결 없음"})
    return out
