"""지금 모집 중인 공고 목록.

목록·마감일 = 고용24 공채속보 API(210L21) 원본
본문        = 기업 채용페이지에서 수집한 jd_tiered.json (robots 허용분)
직무 단위   = roles.json (persona.data 로더 재사용)

오늘 날짜 기준 마감일(empWantedEndt)이 지나지 않은 것만 '모집 중'으로 본다.
목록은 매일 바뀌므로(4일 만에 신규 93 · 마감 132) scripts/refresh_open_postings.py 로 갱신한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime

from persona.data import DATA_DIR, RoleDoc, load_roles

# 팀 파이프라인(refresh_private.py) 누적본이 있으면 우선, 없으면 번들 원본
LIST_FILES = ("gongchae_all.json", "gongchae_open.json", "공채속보_원본350.json")


@dataclass
class OpenRole:
    doc: RoleDoc
    seq: str
    start: date | None
    end: date | None
    emp_type: str
    corp_type: str

    def days_left(self, today: date) -> int | None:
        return (self.end - today).days if self.end else None


@dataclass
class NewPosting:
    """목록에는 있지만 본문을 아직 수집하지 못한 공고."""
    seq: str
    corp: str
    title: str
    url: str
    end: date | None


def _d(s: str) -> date | None:
    try:
        return datetime.strptime((s or "")[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _load_list() -> list[dict]:
    for name in LIST_FILES:
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"{DATA_DIR} 에 공채속보 목록 파일({', '.join(LIST_FILES)})이 없습니다.")


class OpenCatalog:
    def __init__(self, today: date | None = None, tiers=("A", "B")):
        self.today = today or date.today()
        listing = _load_list()
        by_url = {}
        for g in listing:
            end = _d(g.get("empWantedEndt", ""))
            if end and end < self.today:
                continue  # 마감
            by_url[g.get("empWantedHomepgDetail", "")] = g
        self.listing_total = len(listing)

        self.roles: list[OpenRole] = []
        with_body = set()
        for doc in load_roles(tier=None):
            g = by_url.get(doc.url)
            if not g:
                continue
            with_body.add(doc.url)
            if doc.tier not in tiers:
                continue  # C등급은 직무 정보가 없어 대조 불가
            self.roles.append(OpenRole(doc, g.get("empSeqno", ""), _d(g.get("empWantedStdt")),
                                       _d(g.get("empWantedEndt")), g.get("empWantedTypeNm", ""),
                                       g.get("coClcdNm", "")))
        self.no_body = [NewPosting(g.get("empSeqno", ""), g.get("empBusiNm", ""),
                                   g.get("empWantedTitle", ""), u, _d(g.get("empWantedEndt")))
                        for u, g in by_url.items() if u not in with_body]
        self.open_total = len(by_url)

    def summary(self) -> str:
        return (f"{self.today} 기준 모집 중 {self.open_total}건 (목록 {self.listing_total}건 중) · "
                f"대조 가능한 직무 {len(self.roles)}개 · 본문 미수집 {len(self.no_body)}건")
