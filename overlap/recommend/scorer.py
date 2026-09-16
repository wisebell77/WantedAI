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
       역량 하나에 **양쪽 근거**가 붙는다.
           사용자 쪽  그 역량으로 읽힌 경험 원문 문장
           공고 쪽    그 직무 공고에 실제로 적혀 있던 표기 + 기관·공고명·원문 링크
       사용자 문장만 보여 주면 "왜 이 직무가 그걸 요구한다는 건데?"에 답을 못 한다.
       **부족한 역량도 마찬가지다** — 그것도 "이 직무가 이걸 요구한다"는 주장이므로
       똑같이 공고 원문이 붙는다.
    3. 퍼센트를 쓰지 않는다.
       겹침 비율은 무작위 병합 대조군(61.1%)이 실제 군집(53.8%)보다 높게 나온 지표다.
       숫자가 커 보일 뿐 아무 것도 증명하지 못한다. 건수와 문장만 쓴다.
       내부 점수(IDF 합)는 순위 정렬 용도로만 쓰고 화면에 띄우지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..competency.projector import ProjectionResult, TextProjector
from .evidence import EvidenceIndex, MarketSignal, Quote, RelatedPosting
from .matrix import JobMatrix, JobProfile


@dataclass(frozen=True)
class Evidence:
    """역량 하나에 붙는 근거. 사용자 쪽과 공고 쪽이 함께 있어야 완성이다."""

    competency: str
    sentence: str = ""                # 사용자 경험 원문 (갖춘 역량일 때만)
    similarity: float = 0.0
    postings: int = 0                 # 이 직무 공고 중 해당 역량을 요구한 건수
    quotes: tuple[Quote, ...] = ()    # 공고에 실제로 적혀 있던 표기 + 출처
    is_extension: bool = False        # 확장 노드(민간에서만 나온 개념)인가

    @property
    def grounded(self) -> bool:
        """공고 쪽 근거가 있는가. 없으면 화면에 올리지 않는다."""
        return bool(self.quotes)

    def source_label(self) -> str:
        for q in self.quotes:
            for s in q.sources:
                if s.institution:
                    return s.label()
        return ""


@dataclass(frozen=True)
class Subdivision:
    """소분류 **안에서** 어느 세분류에 더 가까운가.

    단독 추천이 아니다. `정보기술전략·계획` 을 권한 다음
    "그 안에서는 빅데이터분석 쪽입니다" 라고 한 단계 좁혀 주는 것이다.
    NCS 이름만으로는 안 와닿는데, 세분류까지 내려가면 훨씬 구체적이 된다.

    표본이 작아 순위를 단독 근거로 쓰면 안 된다. 그래서 단위 수를 같이 낸다.
    """

    code: str
    name: str
    units: int
    overlap: int
    description: str = ""

    def sentence(self) -> str:
        return (f"{self.name} — 겹치는 역량 {self.overlap}개 "
                f"(이 세분류 공고 {self.units}건)")


@dataclass
class JobMatch:
    """직무 하나와의 대조 결과."""

    code: str
    name: str
    units: int
    institutions: int
    have: list[Evidence] = field(default_factory=list)   # 겹치는 역량
    lack: list[Evidence] = field(default_factory=list)   # 요구되는데 없는 역량
    postings: list[RelatedPosting] = field(default_factory=list)  # 대표 공고
    subdivisions: list[Subdivision] = field(default_factory=list)  # 세분류 순위
    description: str = ""                                # 이 분류가 무슨 일인가
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
    market: list[MarketSignal] = field(default_factory=list)

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
                 taxonomy=None, evidence: EvidenceIndex | None = None,
                 sub_matrix: JobMatrix | None = None, descriptions=None):
        from ..config import PATHS
        self.matrix = matrix or JobMatrix.load()
        # 세분류 행렬과 설명은 **있으면 쓰고 없으면 조용히 건너뛴다.**
        # 둘 다 화면을 풍부하게 하는 것이지 추천 순위에는 영향을 주지 않는다.
        if sub_matrix is None and PATHS.sub_matrix.exists():
            sub_matrix = JobMatrix.load(PATHS.sub_matrix)
        self.sub_matrix = sub_matrix
        if descriptions is None:
            from ..collect.jobinfo import DescriptionStore
            descriptions = DescriptionStore.load()
        self.descriptions = descriptions
        self.projector = projector or TextProjector()
        self.taxonomy = taxonomy
        self.evidence = evidence if evidence is not None else EvidenceIndex.load()
        # 인덱스가 있으면 **공고 근거가 없는 역량은 버린다.** 서비스가 지켜야 할 규칙이다.
        # 인덱스를 아직 안 만들었으면(평가·개발 중) 그 규칙을 끄고 돌아간다.
        # 인덱스가 없다고 조용히 근거 없는 추천을 내보내는 게 아니라,
        # '근거를 댈 수 없는 모드'임을 flag 로 드러내 둔다.
        self.require_quotes = bool(self.evidence)

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
                lack_limit: int = 10, quotes: int = 2,
                postings: int = 3) -> JobMatch:
        """투영 결과 하나를 직무 하나와 맞춰 본다.

        갖춘 역량은 사용자 문장 + 공고 원문 양쪽이 있어야 통과한다.
        부족한 역량은 사용자 문장이 없는 게 당연하므로 공고 원문만 본다.
        """
        nodes = result.nodes
        have = []
        for c in profile.matched(nodes):
            if not result.evidence_for(c):            # 사용자 쪽 근거
                continue
            q = tuple(self.evidence.quotes(profile.code, c, quotes))
            if self.require_quotes and not q:         # 공고 쪽 근거
                continue
            best = max((h for h in result.hits if h.node == c),
                       key=lambda h: h.similarity)
            have.append(Evidence(c, best.evidence, best.similarity,
                                 profile.df.get(c, 0), q, best.is_extension))

        lack = []
        for c in profile.missing(nodes):
            q = tuple(self.evidence.quotes(profile.code, c, quotes))
            if self.require_quotes and not q:
                continue
            lack.append(Evidence(c, postings=profile.df.get(c, 0), quotes=q))
            if len(lack) >= lack_limit:
                break

        # 위치 인자로 넘기지 않는다. 필드를 하나 끼워 넣었을 때 score 가
        # subdivisions 자리로 들어가는 사고가 났다.
        return JobMatch(
            code=profile.code, name=profile.name, units=profile.units,
            institutions=profile.institutions, have=have, lack=lack,
            postings=self.evidence.postings(
                profile.code, [e.competency for e in have], postings),
            subdivisions=self.subdivisions(nodes, profile.code),
            description=self.describe(profile.code),
            score=profile.score(nodes))

    # ── 한 단계 더 좁히기

    def subdivisions(self, nodes, code: str, limit: int = 3,
                     min_overlap: int = 2) -> list[Subdivision]:
        """소분류 안에서 어느 세분류에 더 가까운가.

        `정보기술전략·계획` 을 권한 다음 "그 안에서는 빅데이터분석 쪽입니다"
        까지 내려가야 이름이 와닿는다. 실제로 그 소분류 안에 빅데이터분석이
        34단위 들어 있는데, 소분류까지만 보면 그게 안 보인다.

        **단독 추천이 아니다.** 이미 고른 소분류 안의 줄 세우기다.
        표본이 작아 단독 근거로 쓰면 안 되므로 단위 수를 같이 낸다.
        """
        if self.sub_matrix is None:
            return []
        out = []
        for p in self.sub_matrix:
            if not p.code.startswith(code):
                continue
            hit = p.matched(nodes)
            if len(hit) >= min_overlap:
                out.append(Subdivision(p.code, p.name, p.units, len(hit),
                                       self.describe(p.code)))
        out.sort(key=lambda s: (-s.overlap, -s.units))
        return out[:limit]

    def describe(self, code: str) -> str:
        """이 분류가 무슨 일인지. 공식 능력단위 정의에서 온 문장뿐이다."""
        return self.descriptions.summary(code) if self.descriptions else ""

    def market_signals(self, result: ProjectionResult,
                       limit: int = 5) -> list[MarketSignal]:
        """확장 노드에 붙은 문장이 있으면 '시장이 요구하는 것'으로 따로 낸다.

        공공 축에 대응 개념이 없어 직무 행렬에는 못 들어가는 것들이다.
        그렇다고 버리면 사용자가 가진 가장 최신 역량(클라우드·LLM·ERP)이
        통째로 사라진다. 대신 **판정과 섞지 않고 별도 블록**으로 낸다.

        민간 공고 본문은 인용하지 않는다. 어느 기업의 어떤 직무가 요구하는지까지만.
        """
        out = []
        for node in sorted(result.nodes):
            m = self.evidence.market(node)
            if m:
                out.append(m)
        out.sort(key=lambda m: -m.corps)
        return out[:limit]

    # ── 정방향

    def forward(self, texts, target: str, neighbors: int = 3,
                lack_limit: int = 10) -> GapReport:
        """목표 직무를 정하고, 그 직무와의 격차를 낸다.

        target 은 소분류 코드 또는 이름.
        비교 직무를 함께 붙이는 이유는 CLAUDE.md 의 대조 원칙이다.
        "부족 12개"만 보여 주면 많은 건지 적은 건지 알 수 없다.
        """
        code, matrix = self.resolve(target)
        res = self.profile(texts)
        tgt = self.compare(res, matrix[code], lack_limit)
        near = [m for m in self.reverse_from(res, limit=neighbors + 1)
                if m.code != code[:6]][:neighbors]
        return GapReport(tgt, near, [s for s, _ in res.unmatched],
                         self.market_signals(res))

    # ── 역방향

    def reverse(self, texts, limit: int = 5, exclude=(),
                min_overlap: int = 2, lack_limit: int = 10) -> list[JobMatch]:
        return self.reverse_from(self.profile(texts), limit, exclude,
                                 min_overlap, lack_limit)

    def reverse_from(self, result: ProjectionResult, limit: int = 5,
                     exclude=(), min_overlap: int = 2,
                     lack_limit: int = 10) -> list[JobMatch]:
        """겹침이 많은 직무를 위에서부터.

        min_overlap 은 근거 하한이다. 역량 하나 겹친 걸 "추천"으로 내보내면
        근거 없는 출력이 된다.

        **순위는 점수로 매기고 여기서는 개수로 거른다.** 기준이 둘이라
        점수 1위가 잘려 나갈 수 있다 — 실제로 `min_overlap=3` 일 때
        점수 1위(정보기술개발, 1.10)가 겹침 2개라 빠지고 3위가 화면에 올라갔다.
        사용자 방언 세트로 재니 질의의 **35%가 아예 답을 못 받고 있었다.**

            min_overlap   사용자 Top-1   Top-3   답 못한 질의
                 3           36.4%      39.8%      35%
                 2           47.7%      61.4%      12%   <- 이걸 쓴다
                 1           45.5%      64.2%       8%

        1 까지 내리면 Top-3 는 더 오르지만 Top-1 이 떨어진다.
        역량 하나만 겹친 직무가 1위로 올라오는 건 근거가 너무 얇다.
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
        blocked = {self.resolve(s)[0][:2] for s in seen}
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

    def resolve(self, target: str):
        """코드/이름 → (코드, 그 코드가 든 행렬).

        소분류(6자리)와 세분류(8자리) 둘 다 목표가 될 수 있다.
        잘 모르겠으면 소분류를, 희망 직무가 구체적이면 세분류를 고른다.
        """
        t = (target or "").strip()
        for m in (self.matrix, self.sub_matrix):
            if m is None:
                continue
            if t in m:
                return t, m
            for p in m:
                if p.name == t:
                    return p.code, m
        if self.taxonomy:
            n = self.taxonomy.lookup(t, level=3)
            if n and n[0] in self.matrix:
                return n[0], self.matrix
        raise KeyError(f"직무를 찾을 수 없습니다: {target}")

    def targets(self) -> list[dict]:
        """정방향에서 고를 수 있는 목표 목록. 소분류 + 그 아래 세분류.

        화면에서 검색으로 찾을 수 있게 `label` 에 상위 이름을 붙여 둔다 —
        `정보기술전략· 계획 › 빅데이터분석` 처럼.
        """
        out = [{"code": p.code, "name": p.name, "label": p.name,
                "units": p.units, "level": "소분류", "parent": ""}
               for p in self.matrix]
        for p in (self.sub_matrix or []):
            parent = self.matrix.profiles.get(p.code[:6])
            if parent is None:
                continue
            out.append({"code": p.code, "name": p.name,
                        "label": f"{parent.name} › {p.name}",
                        "units": p.units, "level": "세분류",
                        "parent": parent.name})
        out.sort(key=lambda x: (x["parent"] or x["name"], x["level"] != "소분류",
                                -x["units"]))
        return out
