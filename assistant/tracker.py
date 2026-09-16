"""ApplicationTracker — 담아둔 공고 + 자소서 보관소 & 일자별 진행 추적.

이 층이 "즉석 연결"을 "담아두고 이어서 작업하는" 실제 흐름으로 바꾼다.
  - 공고를 담고(add_posting), 자소서를 한 번 붙이면(attach_draft) 보관된다 → 매번 재입력 X
  - 자소서는 '붙여넣은 텍스트' 또는 '연결된 파일'로 둘 수 있다(파일이면 매번 새로 읽음)
  - snapshot()으로 그날 상태를 계산·기록 → 여러 날 쌓이면 시간축 트래킹
  - JSON으로 저장/복원

자소서 ↔ 공고 연결은 id로 맺는다: EssayDraft.posting_id == Posting.id
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .coverage import judge_coverage
from .fit import estimate_fit
from .llm import LLMClient
from .models import (
    Competency,
    CoverageStatus,
    EssayDraft,
    Posting,
    PostingAnalysis,
)


# ---------------------------------------------------------------------------
# 자소서 출처: 붙여넣은 텍스트이거나, 연결된 파일(매번 새로 읽음)
# ---------------------------------------------------------------------------
@dataclass
class DraftRef:
    text: str = ""
    file_path: Optional[str] = None  # 지정 시 이쪽을 우선해 매번 새로 읽는다

    def resolve(self) -> str:
        """지금 시점의 자소서 본문. 파일이 연결돼 있으면 그 최신 내용."""
        if self.file_path and os.path.exists(self.file_path):
            try:
                with open(self.file_path, encoding="utf-8") as f:
                    return f.read()
            except OSError:
                pass
        return self.text


@dataclass
class SnapshotItem:
    posting_id: str
    days_left: int
    fit: Optional[float]
    coverage_rate: float
    covered: list[str]
    missing: list[str]


@dataclass
class Snapshot:
    as_of: str  # ISO date
    items: list[SnapshotItem] = field(default_factory=list)


class ApplicationTracker:
    """공고·자소서·경험을 보관하고, 일자별 진행을 기록한다."""

    def __init__(self, store_path: Optional[str] = None, client: Optional[LLMClient] = None):
        self.store_path = store_path
        self.client = client
        self.experience = DraftRef()             # fit 계산 기준(전체 경험) — 한 번만 설정
        self.postings: dict[str, Posting] = {}
        self.drafts: dict[str, DraftRef] = {}    # posting_id -> 자소서
        self.snapshots: list[Snapshot] = []

    # -- 담기/붙이기 -------------------------------------------------------
    def set_experience(self, text: str = "", file_path: Optional[str] = None) -> None:
        """fit 계산 기준이 되는 '전체 경험'을 한 번 설정(텍스트 또는 파일)."""
        self.experience = DraftRef(text=text, file_path=file_path)

    def add_posting(self, posting: Posting) -> None:
        self.postings[posting.id] = posting

    def attach_draft(
        self, posting_id: str, text: str = "", file_path: Optional[str] = None
    ) -> None:
        """공고에 자소서를 붙인다. 텍스트를 넣거나 파일을 연결(연결 시 재붙여넣기 불필요)."""
        if posting_id not in self.postings:
            raise KeyError(f"담아둔 공고에 없음: {posting_id}")
        self.drafts[posting_id] = DraftRef(text=text, file_path=file_path)

    def update_draft(self, posting_id: str, text: str) -> None:
        """앱 안에서 자소서를 편집(파일 연결이면 파일을 고치면 됨)."""
        ref = self.drafts.get(posting_id) or DraftRef()
        ref.text = text
        self.drafts[posting_id] = ref

    # -- 계산 -------------------------------------------------------------
    def analyze_all(self, as_of: Optional[date] = None) -> list[PostingAnalysis]:
        """보관된 자소서·경험으로 모든 공고를 지금 다시 계산(기록은 안 함)."""
        as_of = as_of or date.today()
        experience_text = self.experience.resolve()
        analyses: list[PostingAnalysis] = []
        for pid, posting in self.postings.items():
            # fit: 전체 경험 기준(경험이 있으면 자체 추정, 없으면 기존 fit_score 유지)
            if experience_text.strip():
                posting.fit_score = estimate_fit(posting, experience_text, self.client)
            draft_text = self.drafts.get(pid, DraftRef()).resolve()
            results = judge_coverage(
                posting, EssayDraft.from_text(pid, draft_text), self.client
            )
            analyses.append(PostingAnalysis(posting=posting, results=results, as_of=as_of))
        return analyses

    def snapshot(self, as_of: Optional[date] = None) -> list[PostingAnalysis]:
        """지금 상태를 계산하고 '그날의 기록'으로 남긴다(시간축 트래킹의 한 점)."""
        as_of = as_of or date.today()
        analyses = self.analyze_all(as_of)
        snap = Snapshot(as_of=as_of.isoformat())
        for a in analyses:
            snap.items.append(
                SnapshotItem(
                    posting_id=a.posting.id,
                    days_left=a.days_left,
                    fit=a.posting.fit_score,
                    coverage_rate=round(a.coverage_rate, 3),
                    covered=[r.competency.name for r in a.results
                             if r.status == CoverageStatus.COVERED],
                    missing=[r.competency.name for r in a.missing()],
                )
            )
        # 같은 날짜 기록이 있으면 교체(하루 한 점)
        self.snapshots = [s for s in self.snapshots if s.as_of != snap.as_of]
        self.snapshots.append(snap)
        self.snapshots.sort(key=lambda s: s.as_of)
        return analyses

    def progress(self, posting_id: str) -> list[tuple[str, float]]:
        """한 공고의 (날짜, 커버율) 추이 — '어제보다 얼마나 진행됐나'의 근거."""
        out = []
        for s in self.snapshots:
            for it in s.items:
                if it.posting_id == posting_id:
                    out.append((s.as_of, it.coverage_rate))
        return out

    # -- 저장/복원 --------------------------------------------------------
    def save(self, path: Optional[str] = None) -> str:
        path = path or self.store_path
        if not path:
            raise ValueError("store_path 가 없습니다.")
        data = {
            "experience": {"text": self.experience.text, "file_path": self.experience.file_path},
            "postings": [_posting_to_dict(p) for p in self.postings.values()],
            "drafts": {pid: {"text": d.text, "file_path": d.file_path}
                       for pid, d in self.drafts.items()},
            "snapshots": [_snapshot_to_dict(s) for s in self.snapshots],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.store_path = path
        return path

    @classmethod
    def load(cls, path: str, client: Optional[LLMClient] = None) -> "ApplicationTracker":
        t = cls(store_path=path, client=client)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        exp = data.get("experience", {})
        t.experience = DraftRef(text=exp.get("text", ""), file_path=exp.get("file_path"))
        for pd in data.get("postings", []):
            t.add_posting(_posting_from_dict(pd))
        for pid, d in data.get("drafts", {}).items():
            t.drafts[pid] = DraftRef(text=d.get("text", ""), file_path=d.get("file_path"))
        for sd in data.get("snapshots", []):
            t.snapshots.append(_snapshot_from_dict(sd))
        return t


# ---------------------------------------------------------------------------
# 직렬화 헬퍼
# ---------------------------------------------------------------------------
def _posting_to_dict(p: Posting) -> dict:
    return {
        "id": p.id,
        "company": p.company,
        "role": p.role,
        "deadline": p.deadline.isoformat(),
        "fit_score": p.fit_score,
        "required_competencies": [
            {"name": c.name, "importance": c.importance,
             "required_level": c.required_level, "source_excerpt": c.source_excerpt}
            for c in p.required_competencies
        ],
    }


def _posting_from_dict(d: dict) -> Posting:
    return Posting(
        id=d["id"],
        company=d.get("company", "?"),
        role=d.get("role", "?"),
        deadline=date.fromisoformat(d["deadline"]),
        fit_score=d.get("fit_score"),
        required_competencies=[
            Competency(
                name=c["name"],
                importance=c.get("importance", 1.0),
                required_level=c.get("required_level", ""),
                source_excerpt=c.get("source_excerpt", ""),
            )
            for c in d.get("required_competencies", [])
        ],
    )


def _snapshot_to_dict(s: Snapshot) -> dict:
    return {"as_of": s.as_of, "items": [vars(it) for it in s.items]}


def _snapshot_from_dict(d: dict) -> Snapshot:
    return Snapshot(
        as_of=d["as_of"],
        items=[SnapshotItem(**it) for it in d.get("items", [])],
    )
