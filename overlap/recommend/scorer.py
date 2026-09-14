"""정방향 격차 · 역방향 매칭.

CLAUDE.md 의 설계 원칙 그대로다.
    정방향과 역방향은 같은 지표(겹침)의 양 끝이다.
    정방향 — 목표 직무와 겹침이 부족한 곳   → 준비할 것
    역방향 — 안 본 직무와 겹침이 뜻밖에 많은 곳 → 새 선택지

출력 규칙 세 가지. 어기면 서비스가 아니라 점집이 된다.

    1. 판정하지 않는다.
       "당신은 HR 이 맞습니다" 가 아니라
       "당신의 경험은 HR 공고가 요구하는 역량 7개와 겹칩니다 (마케팅은 3개)".
    2. 근거 없는 항목은 내보내지 않는다.
       모든 역량에는 사용자 문장과 공고 건수가 붙는다. 못 붙이면 뺀다.
    3. 퍼센트를 쓰지 않는다.
       겹침 비율은 무작위 병합 대조군(61.1%)이 실제 군집(53.8%)보다 높게 나온 지표다.
       숫자가 커 보일 뿐 아무 것도 증명하지 못한다. 건수와 문장만 쓴다.
       내부 점수(IDF 합)는 순위 정렬 용도로만 쓰고 화면에 띄우지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..competency.projector import ProjectionResult, TextProjector
from .matrix import JobMatrix, JobProfile


@dataclass(frozen=True)
class Evidence:
    """역량 하나에 붙는 근거."""

    competency: str
    sentence: str = ""                # 사용자 경험 원문 (갖춘 역량)
    similarity: float = 0.0
    postings: int = 0                 # 이 직무 공고 중 해당 역량을 요구한 건수
    is_extension: bool = False        # 확장 노드(민간에서만 나온 개념)인가


@dataclass
class JobMatch:
    """직무 하나와의 대조 결과."""

    code: str
    name: str
    units: int
    institutions: int
    have: list[Evidence] = field(default_factory=list)   # 겹치는 역량
    lack: list[Evidence] = field(default_factory=list)   # 요구되는데 없는 역량
    score: float = 0.0                                   # 정렬용. 화면에 쓰지 않는다

    @property
    def overlap(self) -> int:
        return len(self.have)

    def sentence(self) -> str:
        """판정이 아닌 대조 문장. 화면 문구의 기준형."""
        return (f"{self.name} 공고가 요구하는 역량 중 {len(self.have)}개가 "
                f"당신의 경험과 겹칩니다 (공고 {self.units}건 · 기관 {self.institutions}곳)")

    def __repr__(self) -> str:
        return f"<JobMatch {self.name} 겹침 {len(self.have)} / 부족 {len(self.lack)}>"


@dataclass
class GapReport:
    """정방향 — 목표 직무 하나에 대한 격차."""

    target: JobMatch
    compare: list[JobMatch] = field(default_factory=list)  # 비교용 이웃 직무
    unmatched: list[str] = field(default_factory=list)     # 사전에 못 붙인 문장

    def __repr__(self) -> str:
        return f"<GapReport {self.target.name} 부족 {len(self.target.lack)}개>"


class Recommender:
    """경험 원문 → 정방향 격차 / 역방향 후보.

    >>> r = Recommender()
    >>> r.reverse(["학회 운영진으로 8명 일정 조율", "설문 300건 정리해 보고서 작성"])[0]
    <JobMatch 경영기획 겹침 11 / 부족 289>
    """

    def __init__(self, matrix: JobMatrix | None = None,
                 projector: TextProjector | None = None,
                 taxonomy=None):
        self.matrix = matrix or JobMatrix.load()
        self.projector = projector or TextProjector()
        self.taxonomy = taxonomy

    # ── 입력 해석

    def profile(self, texts) -> ProjectionResult:
        """경험 원문 문장들을 역량 노드로 투영한다.

        문장 단위로 쪼개는 건 호출자 몫이 아니다. 여기서 한다 —
        문단째 넣으면 임베딩이 뭉개져 유사도가 전부 0.3 대로 눌린다.
        """
        return self.projector.project(self.sentences(texts))

    @staticmethod
    def sentences(texts) -> list[str]:
        import re
        if isinstance(texts, str):
            texts = [texts]
        out = []
        for t in texts:
            for s in re.split(r"[.!?\n·•]+|(?<=다)\s+(?=[가-힣])", t or ""):
                s = s.strip(" -·,")
                if len(s) >= 6:
                    out.append(s)
        return out

    # ── 대조

    def compare(self, result: ProjectionResult, profile: JobProfile,
                lack_limit: int = 10) -> JobMatch:
        """투영 결과 하나를 직무 하나와 맞춰 본다."""
        nodes = result.nodes
        have = []
        for c in profile.matched(nodes):
            ev = result.evidence_for(c)
            if not ev:                                # 근거 없는 항목은 버린다
                continue
            best = max((h for h in result.hits if h.node == c),
                       key=lambda h: h.similarity)
            have.append(Evidence(c, best.evidence, best.similarity,
                                 profile.df.get(c, 0), best.is_extension))
        lack = [Evidence(c, postings=profile.df.get(c, 0))
                for c in profile.missing(nodes)[:lack_limit]]
        return JobMatch(profile.code, profile.name, profile.units,
                        profile.institutions, have, lack,
                        profile.score(nodes))

    # ── 정방향

    def forward(self, texts, target: str, neighbors: int = 3,
                lack_limit: int = 10) -> GapReport:
        """목표 직무를 정하고, 그 직무와의 격차를 낸다.

        target 은 소분류 코드 또는 이름.
        비교 직무를 함께 붙이는 이유는 CLAUDE.md 의 대조 원칙이다.
        "부족 12개"만 보여 주면 많은 건지 적은 건지 알 수 없다.
        """
        code = self.resolve(target)
        res = self.profile(texts)
        tgt = self.compare(res, self.matrix[code], lack_limit)
        near = [m for m in self.reverse_from(res, limit=neighbors + 1)
                if m.code != code][:neighbors]
        return GapReport(tgt, near, [s for s, _ in res.unmatched])

    # ── 역방향

    def reverse(self, texts, limit: int = 5, exclude=(),
                min_overlap: int = 3, lack_limit: int = 10) -> list[JobMatch]:
        return self.reverse_from(self.profile(texts), limit, exclude,
                                 min_overlap, lack_limit)

    def reverse_from(self, result: ProjectionResult, limit: int = 5,
                     exclude=(), min_overlap: int = 3,
                     lack_limit: int = 10) -> list[JobMatch]:
        """겹침이 많은 직무를 위에서부터.

        min_overlap 은 근거 하한이다. 역량 1~2개 겹친 걸 "추천"으로 내보내면
        근거 없는 출력이 된다.
        """
        skip = {self.resolve(x) for x in exclude}
        out = []
        for code, _ in self.matrix.rank(result.nodes, limit=limit * 4):
            if code in skip:
                continue
            m = self.compare(result, self.matrix[code], lack_limit)
            if m.overlap >= min_overlap:
                out.append(m)
            if len(out) >= limit:
                break
        return out

    def unexpected(self, texts, seen=(), limit: int = 3,
                   **kw) -> list[JobMatch]:
        """데모 하이라이트 — 사용자가 안 본 대분류에서 올라온 직무만.

        seen 에 넣은 직무와 같은 대분류는 전부 뺀다. 정보통신을 보고 있던
        사람에게 정보통신 옆칸을 권하는 건 '뜻밖'이 아니다.
        """
        blocked = {self.resolve(s)[:2] for s in seen}
        res = self.profile(texts)
        out = []
        for m in self.reverse_from(res, limit=limit * 8, **kw):
            if m.code[:2] in blocked:
                continue
            out.append(m)
            if len(out) >= limit:
                break
        return out

    # ── 보조

    def resolve(self, target: str) -> str:
        """코드/이름 → 소분류 코드."""
        t = (target or "").strip()
        if t in self.matrix:
            return t
        for p in self.matrix:
            if p.name == t:
                return p.code
        if self.taxonomy:
            n = self.taxonomy.lookup(t, level=3)
            if n:
                return n
        raise KeyError(f"직무를 찾을 수 없습니다: {target}")
