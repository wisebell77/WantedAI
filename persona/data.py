"""수집 공고 데이터 로더.

data/overlap/ 의 roles.json(직무 단위 365개) + jd_tiered.json(공고 본문 221건)을
직무 단위 문서(RoleDoc)로 합친다. roles.json 에는 직무별 본문이 없어서
공고 본문(clean)에서 직무명 줄을 찾아 해당 구간을 잘라낸다.
"""
from __future__ import annotations

import ast
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("OVERLAP_DATA_DIR", os.path.join(ROOT, "data", "overlap"))
MAX_TEXT = 6000  # LLM 입력 상한


@dataclass
class RoleDoc:
    role_id: str
    corp: str
    post_title: str
    role: str
    job: str
    tier: str
    url: str
    techs: list[str] = field(default_factory=list)
    text: str = ""
    sliced: bool = False  # 공고 본문에서 이 직무 구간만 잘라냈는지

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("role_id", "corp", "post_title", "role", "job", "tier", "url", "techs")}


def _load(name: str):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} 가 없습니다. Overlap_데이터 zip의 data/ 파일을 data/overlap/ 에 두세요.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _techs(value) -> list[str]:
    if isinstance(value, list):
        return value
    try:
        out = ast.literal_eval(value or "[]")
        return [str(x) for x in out] if isinstance(out, list) else []
    except (ValueError, SyntaxError):
        return []


def _slice(clean: str, name: str, others: list[str]) -> tuple[str, bool]:
    """본문에서 name 으로 시작하는 줄부터 다음 직무명 줄 전까지 잘라낸다."""
    lines = clean.splitlines()
    key = name.strip()
    start = next((i for i, l in enumerate(lines) if key and l.strip().startswith(key)), None)
    if start is None:
        return clean[:MAX_TEXT], False
    stops = [o.strip() for o in others if o.strip() and o.strip() != key]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if any(lines[j].strip().startswith(s) for s in stops):
            end = j
            break
    return "\n".join(lines[start:end])[:MAX_TEXT], True


@lru_cache(maxsize=4)
def load_roles(tier: str | None = "A", min_len: int = 150) -> tuple[RoleDoc, ...]:
    """직무 단위 문서 목록. tier=None 이면 전 등급. 본문이 너무 짧은 조각(표 머리 등)은 제외."""
    roles = _load("roles.json")
    posts = {p["url"]: p for p in _load("jd_tiered.json")}
    by_url: dict[str, list[dict]] = defaultdict(list)
    for r in roles:
        by_url[r["url"]].append(r)

    out: list[RoleDoc] = []
    for url, rows in by_url.items():
        post = posts.get(url, {})
        clean = post.get("clean") or post.get("text") or ""
        names = [r["role"] for r in rows]
        for idx, r in enumerate(rows):
            if tier and r.get("post_tier") != tier:
                continue
            if int(r.get("len") or 0) < min_len:
                continue
            single = len(rows) == 1 or r["role"] == r.get("post_title")
            text, sliced = (clean[:MAX_TEXT], False) if single else _slice(clean, r["role"], names)
            out.append(RoleDoc(
                role_id=f"{post.get('seq') or abs(hash(url)) % 10**6}-{idx}",
                corp=r.get("corp", ""), post_title=r.get("post_title", ""),
                role=r.get("role", ""), job=r.get("job", "분류불가"),
                tier=r.get("post_tier", ""), url=url,
                techs=_techs(r.get("techs")), text=text, sliced=sliced))
    return tuple(out)


def get_role(role_id: str) -> RoleDoc:
    for r in load_roles(tier=None):
        if r.role_id == role_id:
            return r
    raise KeyError(role_id)


@lru_cache(maxsize=32)
def job_market(job: str, tier: str | None = "A") -> dict:
    """같은 직무군 공고에서 기술별 요구 빈도. {"n": 직무수, "tech": {기술: 건수}}

    표본이 작다(직무군당 수~수십 건). 화면에는 반드시 'N건 중 k건'으로 보여 준다.
    """
    docs = [r for r in load_roles(tier=tier) if r.job == job]
    cnt = Counter(t.lower() for r in docs for t in set(r.techs))
    return {"job": job, "n": len(docs), "tech": dict(cnt)}
