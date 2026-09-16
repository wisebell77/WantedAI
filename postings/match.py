"""내 경험 ↔ 모집 중 공고 대조.

점수는 설명 가능한 세 가지로만 만든다.
  기술 겹침   내 경험에 나온 기술 ∩ 공고 기술. 드문 기술일수록 무겁게(IDF) — 직무추천 파트와 같은 원리
  요건 겹침   공고 요건 문장(채점표 항목)과 내 경험 문장이 얼마나 닮았나
  직무 적합   희망 직무군 또는 직무추천 결과와 같은 직무군인가
자격은 걸러내지 않고 표시만 한다: [지금 지원 가능] / [준비 필요: 경력 3년 이상 …]
상위 몇 건만 서류 심사 엔진(persona.review_letter)으로 다시 본다 — 키가 있으면 AI 판정.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from concurrent.futures import ThreadPoolExecutor

from persona import load_or_build, review_letter
from persona.grounding import sentences
from persona.rubric import _heuristic_items

from .catalog import OpenCatalog, OpenRole

SYNONYM = {"파이썬": "python", "엑셀": "excel", "자바": "java", "리액트": "react",
           "오라클": "oracle", "리눅스": "linux", "깃": "git", "깃허브": "git", "github": "git"}

# 직무추천(NCS) 결과 → 민간 직무군. 추천 파트와 합의 필요한 임시 표.
NCS_TO_JOB = {
    "정보통신": ["개발/SW", "데이터/AI", "IT인프라/보안"], "데이터": ["데이터/AI"],
    "소프트웨어": ["개발/SW"], "보안": ["IT인프라/보안"],
    "경영": ["경영지원"], "회계": ["경영지원"], "사무": ["경영지원"], "인사": ["경영지원"],
    "영업": ["영업/마케팅"], "마케팅": ["영업/마케팅"], "홍보": ["영업/마케팅"],
    "기계": ["생산/품질", "연구개발"], "재료": ["생산/품질", "연구개발"], "화학": ["생산/품질", "연구개발"],
    "전기": ["생산/품질", "연구개발"], "전자": ["생산/품질", "연구개발"], "품질": ["생산/품질"],
    "건설": ["건설/플랜트"], "디자인": ["디자인"], "안전": ["안전/환경"], "환경": ["안전/환경"],
    "물류": ["물류/SCM"], "교육": ["교육/공공"],
}

_CAREER = re.compile(r"경력\s*(\d+)\s*년|(\d+)\s*년\s*이상")
_GRAD = re.compile(r"(석사|박사)\s*(학위)?\s*(이상|소지|보유|취득)")


@dataclass
class UserProfile:
    experiences: list[str]
    target_jobs: list[str] = field(default_factory=list)   # 민간 직무군 이름 (예: 개발/SW)
    ncs_matches: list[str] = field(default_factory=list)  # 직무추천 결과 이름 (예: 정보기술개발)
    major: str = ""
    newcomer: bool = True
    education: str = "학사"  # 학사 / 석사 / 박사

    @property
    def text(self) -> str:
        return "\n".join(self.experiences)

    def jobs(self) -> set[str]:
        out = set(self.target_jobs)
        for name in self.ncs_matches:
            for key, jobs in NCS_TO_JOB.items():
                if key in name:
                    out.update(jobs)
        return out


def _norm_tech(t: str) -> str:
    t = t.lower()
    return SYNONYM.get(t, t)


def _has(term: str, text: str) -> bool:
    if len(term) <= 2 and term.isascii():  # R, C, Go 같은 짧은 말은 단어 경계로
        return re.search(rf"(?<![A-Za-z&+#]){re.escape(term)}(?![A-Za-z&+#])", text, re.I) is not None
    return term.lower() in text.lower()


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s.lower())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _sim(a: str, b: str) -> float:
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


def _eligibility(role: OpenRole, user: UserProfile) -> list[str]:
    text = f"{role.doc.post_title}\n{role.doc.role}\n{role.doc.text}"
    # '우대' 가 붙은 줄은 요구 조건이 아니다
    lines = [l for l in text.splitlines() if "우대" not in l]
    body = "\n".join(lines)
    reasons = []
    if user.newcomer and "신입" not in text:
        m = _CAREER.search(body)
        if m:
            reasons.append(f"경력 {m.group(1) or m.group(2)}년 이상 요구")
    m = _GRAD.search(body)
    if m and user.education == "학사":
        reasons.append(f"{m.group(1)} 학위 요구")
    return reasons


_BAD_ROLE = re.compile(r"^[*※\-·\s]|담당\s*업무|필요\s*스킬|상세")


def display_name(doc) -> str:
    """roles.json 직무명이 표 머리 조각으로 깨진 경우 공고 제목을 쓴다."""
    role = (doc.role or "").strip()
    if not role or len(role) < 3 or _BAD_ROLE.search(role):
        return doc.post_title
    return role


class _TechIndex:
    def __init__(self, roles: list[OpenRole]):
        self.df = Counter(_norm_tech(t) for r in roles for t in {*r.doc.techs})
        self.n = max(len(roles), 1)
        self.vocab = sorted({t for r in roles for t in r.doc.techs} | set(SYNONYM), key=len, reverse=True)

    def idf(self, t: str) -> float:
        return math.log(1 + self.n / (1 + self.df.get(_norm_tech(t), 0)))

    def user_techs(self, text: str) -> set[str]:
        return {_norm_tech(t) for t in self.vocab if _has(t, text)}


def _score(role: OpenRole, user: UserProfile, utech: set[str], tidx: _TechIndex, usents: list[str]):
    rtech = {_norm_tech(t) for t in role.doc.techs}
    shared = sorted(utech & rtech)
    tech = (sum(tidx.idf(t) for t in shared) / sum(tidx.idf(t) for t in rtech)) if rtech else 0.0

    pairs = []
    for it in _heuristic_items(role.doc):
        best = max(((_sim(s, it["jd_quote"]), s) for s in usents), default=(0, ""))
        tech_hit = any(_has(t, it["jd_quote"]) and t in utech for t in rtech)
        if best[0] >= 0.12 or tech_hit:
            pairs.append({"jd_quote": it["jd_quote"], "user_quote": best[1], "sim": round(best[0], 2)})
    items = len(_heuristic_items(role.doc)) or 1
    req = len(pairs) / items

    jobs = user.jobs()
    job = 1.0 if role.doc.job in jobs else 0.0
    major = 1.0 if user.major and user.major in role.doc.text else 0.0
    score = 0.45 * tech + 0.35 * req + 0.2 * job + 0.1 * major
    return min(score, 1.0), shared, pairs


def recommend_postings(user: UserProfile, catalog: OpenCatalog | None = None, limit: int = 5,
                       review_top: int = 3, use_llm: bool = True) -> dict:
    catalog = catalog or OpenCatalog()
    tidx = _TechIndex(catalog.roles)
    utech = tidx.user_techs(user.text)
    usents = [s for e in user.experiences for s in (sentences(e) or [e])]

    ranked = []
    for role in catalog.roles:
        score, shared, pairs = _score(role, user, utech, tidx, usents)
        if score <= 0:
            continue
        ranked.append((score, role, shared, pairs))
    # 같은 공고의 직무가 목록을 도배하지 않게 공고당 1개
    ranked.sort(key=lambda x: (-x[0], x[1].days_left(catalog.today) or 999))
    seen, picked = set(), []
    for row in ranked:
        if row[1].doc.url in seen:
            continue
        seen.add(row[1].doc.url)
        picked.append(row)
        if len(picked) >= limit:
            break

    results = []
    for rank, (score, role, shared, pairs) in enumerate(picked, 1):
        d = role.doc
        reasons = _eligibility(role, user)
        row = {
            "rank": rank, "role_id": d.role_id, "corp": d.corp, "title": d.post_title, "role": display_name(d),
            "job": d.job, "tier": d.tier, "url": d.url, "emp_type": role.emp_type,
            "end": role.end.isoformat() if role.end else "", "days_left": role.days_left(catalog.today),
            "status": "지금 지원 가능" if not reasons else "준비 필요", "reasons": reasons,
            "score": round(score, 3), "shared_techs": shared, "matched": pairs[:3],
        }
        results.append(row)

    # 상위 몇 건만 서류 심사 엔진으로 정밀 대조 — 동시에 요청해 대기 시간을 줄인다
    def _review(row):
        from persona.data import get_role
        rub = load_or_build(get_role(row["role_id"]), use_llm=use_llm)
        rev = review_letter(rub, user.text, user.experiences, use_llm=use_llm)
        return {"coverage_score": rev["summary"]["coverage_score"],
                "generated_by": f"채점표 {rub['generated_by']} · 심사 {rev['generated_by']}",
                "covered": [x["label"] for x in rev["items"] if x["status"] != "missing"],
                "to_prepare": [x["label"] for x in rev["items"] if x["action"] == "prepare"]}

    top = results[:review_top]
    if top:
        with ThreadPoolExecutor(max_workers=len(top)) as pool:
            for row, rv in zip(top, pool.map(_review, top)):
                row["review"] = rv

    related_new = [p for p in catalog.no_body
                   if any(_has(t, p.title) for t in utech) or any(j.split("/")[0] in p.title for j in user.jobs())]
    return {
        "catalog": catalog.summary(), "user_techs": sorted(utech), "user_jobs": sorted(user.jobs()),
        "results": results,
        "new_without_body": [{"corp": p.corp, "title": p.title, "url": p.url,
                              "end": p.end.isoformat() if p.end else ""} for p in related_new[:5]],
        "note": "점수는 경험-공고 겹침 정도이며 합격 가능성이 아닙니다. 자격 요건은 원문에서 꼭 확인하세요.",
    }
