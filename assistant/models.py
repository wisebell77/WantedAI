"""핵심 데이터 모델.

이 모듈의 자료구조가 AI 비서 파트의 '계약(contract)'이다.
특히 `Competency`/`Posting`은 Overlap 파트가 넘겨주는 역량 데이터의 형태를
그대로 받는 자리이므로, Overlap 산출 스키마가 확정되면 여기만 맞추면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class CoverageStatus(str, Enum):
    """자소서가 특정 요구 역량을 얼마나 드러내고 있는지."""

    COVERED = "covered"      # 충분히 드러남
    PARTIAL = "partial"      # 언급은 되나 근거/수준이 부족
    MISSING = "missing"      # 전혀 드러나지 않음


@dataclass
class Competency:
    """공고가 요구하는 역량 하나. (Overlap 파트 산출물의 최소 단위)

    Overlap이 '공고 → 역량 정규화 + 요구 수준 추출'을 마친 결과를 받는다고 가정한다.
    """

    name: str                      # 정규화된 역량명 (예: "SQL", "데이터 전처리")
    importance: float = 1.0        # 요구 빈도/중요도 가중치 (0~1 권장, Overlap이 산정)
    required_level: str = ""       # 요구 수준 (예: "쿼리 작성", "프로젝트 활용 경험")
    source_excerpt: str = ""       # 근거가 된 공고 원문 일부 (근거 제시용)


@dataclass
class Posting:
    """사용자가 트래킹 중인 채용 공고 하나."""

    id: str
    company: str
    role: str
    deadline: date
    required_competencies: list[Competency] = field(default_factory=list)
    # 적합도: 사용자의 '전체 경험'이 이 직무 요구와 얼마나 겹치는지 (0~1).
    # Overlap 진단 파트가 산출해 넘겨주는 값. 자소서 진행도(커버율)와는 다른 축이다.
    # None이면 우선순위에서 중립(1.0)으로 취급한다.
    fit_score: Optional[float] = None


@dataclass
class EssayDraft:
    """사용자가 작성 중인 자소서/지원서 초안."""

    posting_id: str
    text: str


@dataclass
class CoverageResult:
    """역량 하나에 대한 커버 판정 결과."""

    competency: Competency
    status: CoverageStatus
    evidence: Optional[str] = None   # 자소서에서 근거가 된 문장 (없으면 None)
    comment: str = ""                # 수준/보완점에 대한 짧은 설명

    @property
    def credit(self) -> float:
        """커버율 계산 시 이 역량이 받는 점수 비율 (partial은 절반)."""
        return {
            CoverageStatus.COVERED: 1.0,
            CoverageStatus.PARTIAL: 0.5,
            CoverageStatus.MISSING: 0.0,
        }[self.status]


@dataclass
class PostingAnalysis:
    """공고 하나에 대한 종합 분석 (커버율 + 격차 + 마감)."""

    posting: Posting
    results: list[CoverageResult]
    as_of: date

    @property
    def days_left(self) -> int:
        return (self.posting.deadline - self.as_of).days

    @property
    def coverage_rate(self) -> float:
        """중요도 가중 커버율 (0~1)."""
        total_w = sum(r.competency.importance for r in self.results)
        if total_w == 0:
            return 0.0
        got = sum(r.competency.importance * r.credit for r in self.results)
        return got / total_w

    @property
    def gap(self) -> float:
        """격차 = 1 - 커버율."""
        return 1.0 - self.coverage_rate

    def missing(self) -> list[CoverageResult]:
        return [r for r in self.results if r.status == CoverageStatus.MISSING]

    def partial(self) -> list[CoverageResult]:
        return [r for r in self.results if r.status == CoverageStatus.PARTIAL]
