"""Overlap 수집 데이터 → 엔진 모델(Posting/Competency) 변환 로더.

Overlap 팀이 수집한 실제 공고 데이터를 내 비서 엔진이 먹을 수 있는 형태로 바꾼다.
데이터는 data/overlap/ 아래에 두며, 절대 Git에 커밋하지 않는다(내부 검토용).

⚠ 이 번들에 '없는' 값들 — 로더가 채우는 방식:
  - 요구 수준(required_level): 데이터에 없음(Overlap '요구 수준 추출' 미완). 빈 문자열.
  - 적합도(fit_score): Overlap 진단 산출물. 이 번들엔 없어 None(중립).
  - 마감일(deadline): 데이터에 없음(트래킹 시 사용자가 입력할 값).
      → 데모 편의를 위해 assign_deadline 콜백으로 임시 부여한다. 실제 값 아님.

중요도(importance)는 analysis.json 의 코퍼스 전체 기술 '빈도'로 근사한다.
(요구 빈도 = 그 역량을 요구하는 공고가 많다 = 더 중요) — Overlap이 정식 가중치를
주면 그때 교체하면 된다.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Callable, Optional

from .models import Competency, Posting

DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "overlap"
)


def _load_json(data_dir: str, name: str):
    with open(os.path.join(data_dir, name), encoding="utf-8") as f:
        return json.load(f)


def importance_table(analysis: dict) -> dict[str, float]:
    """analysis.json 의 기술 빈도를 0~1 중요도로 정규화한 표.

    키는 소문자로 통일해 대소문자/표기 차이를 흡수한다.
    """
    tech = analysis.get("tech", {})
    if not tech:
        return {}
    peak = max(tech.values())
    table: dict[str, float] = {}
    for name, cnt in tech.items():
        table[name.lower()] = round(cnt / peak, 3)
    return table


def _staggered_deadline(index: int, _posting: dict) -> date:
    """데모용 임시 마감일: 오늘부터 2,5,8,11... 일 뒤로 흩뿌린다. (실제 값 아님)"""
    return date.today() + timedelta(days=2 + (index % 5) * 3)


def _excerpt_for(tech: str, clean: str) -> str:
    """공고 본문에서 해당 기술이 언급된 첫 줄을 근거로 뽑는다(근거 제시용)."""
    if not clean:
        return ""
    for line in clean.splitlines():
        if tech.lower() in line.lower():
            return line.strip()[:120]
    return ""


def load_postings(
    data_dir: str = DEFAULT_DATA_DIR,
    *,
    tier: Optional[str] = "A",
    job: Optional[str] = None,
    limit: Optional[int] = None,
    require_techs: bool = True,
    assign_deadline: Optional[Callable[[int, dict], date]] = None,
) -> list[Posting]:
    """실제 공고를 Posting 리스트로 로드.

    tier: 'A'/'B'/'C' 로 등급 필터 (None이면 전체). 기본 A(역량 구체적).
    job:  직무 카테고리 필터 (예: '데이터/AI', '경영지원'). None이면 전체.
    limit: 최대 개수.
    require_techs: 기술 키워드가 있는 공고만 (역량 대조가 의미 있으려면 필요).
    assign_deadline: 마감일 부여 콜백. 기본은 데모용 staggered.
    """
    analysis = _load_json(data_dir, "analysis.json")
    imp = importance_table(analysis)
    rows = _load_json(data_dir, "jd_tiered.json")
    assign = assign_deadline or _staggered_deadline

    postings: list[Posting] = []
    for row in rows:
        if tier and row.get("tier") != tier:
            continue
        if job and row.get("job") != job:
            continue
        techs = row.get("techs") or []
        if require_techs and not techs:
            continue

        clean = row.get("clean") or row.get("text") or ""
        comps = [
            Competency(
                name=t,
                importance=imp.get(t.lower(), 0.5),  # 빈도 표에 없으면 중립 0.5
                required_level="",                    # Overlap '요구 수준 추출' 미완
                source_excerpt=_excerpt_for(t, clean),
            )
            for t in techs
        ]
        idx = len(postings)
        postings.append(
            Posting(
                id=str(row.get("seq") or row.get("url") or idx),
                company=row.get("corp", "?"),
                role=row.get("title", row.get("job", "?")),
                deadline=assign(idx, row),
                required_competencies=comps,
                fit_score=None,  # Overlap 진단 연동 전까지 중립
            )
        )
        if limit and len(postings) >= limit:
            break
    return postings


def job_categories(data_dir: str = DEFAULT_DATA_DIR) -> dict[str, int]:
    """직무 카테고리별 공고 수 (analysis.json)."""
    return _load_json(data_dir, "analysis.json").get("jobs", {})
