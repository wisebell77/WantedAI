"""교차 평가 — 방언이 다른 질의로 잰다. 이 프로젝트에서 가장 중요한 지표다.

내부 평가(evaluate.indomain)는 L1 에게 유리하게 기울어 있다.
질의도 직무기술서, 프로파일도 직무기술서라 같은 방언끼리 맞춘 것이다.
`일정계획준수` 라는 질의가 `일정계획준수` 라는 항목에 문자열로 그대로 걸린다.

실제 사용자는 `학회 운영진 8명 일정 조율` 이라고 쓴다. 그 문장에는
`일정계획준수` 라는 문자열이 없다. L1 은 못 걸리고, 그 간극을 메우라고 L2 가 있다.

그래서 질의를 **민간 공고의 요건 문장**으로 바꾼다. 출처가 다르니 표현이 다르다.
이 평가를 도입하자 결론이 뒤집혔다.

    내부 평가만 봤을 때   L2 는 이득이 없거나 해로워 보였다
    교차 평가로 재니      L1 23.3%  →  +L2 35.2%  →  +문장투영 55.3%

정답은 거칠게 잡는다. 민간 직무의 자체 분류를 NCS 대분류 묶음에 대응시키고,
예측한 소분류가 그 묶음에 속하면 맞힌 것으로 본다.
소분류 단위 정답은 없으므로 대분류 수준의 적중만 본다.

    한계 — 대분류까지만 보므로 '정보통신 안에서 백엔드냐 보안이냐'는 못 잰다.
    확장 노드의 기여가 이 지표에 안 잡히는 이유도 같다. 확장 노드는
    대부분 정보통신 안에서 갈리는 개념이라 대분류 정답을 바꾸지 못한다.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..competency.normalize import L1Normalizer
from ..config import SETTINGS
from ..parse.requirements import RequirementExtractor
from ..recommend.matrix import JobMatrix

# 민간 자체 분류 → 허용 NCS 대분류 코드
GOLD: dict[str, set[str]] = {
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


@dataclass(frozen=True)
class CrossScore:
    label: str
    top1: float
    top3: float
    queries: int
    answered: float = 1.0                     # 점수가 0 이 아닌 질의 비율

    def row(self) -> str:
        return (f"  {self.label:<22}{self.top1*100:>7.1f}%{self.top3*100:>8.1f}%"
                f"{self.answered*100:>10.1f}%{self.queries:>7}")

    @staticmethod
    def header() -> str:
        return f"  {'설정':<22}{'Top-1':>7}{'Top-3':>8}{'매칭질의':>11}{'질의':>7}"

    def __repr__(self) -> str:
        return f"<{self.label} Top-1 {self.top1*100:.1f}% Top-3 {self.top3*100:.1f}%>"


class CrossDomainEvaluator:
    """공공 프로파일 × 민간 질의.

    >>> ev = CrossDomainEvaluator(units, roles)
    >>> ev.string_match()                     # L1 만
    <L1만 Top-1 23.3% Top-3 51.9%>
    >>> ev.projection(TextProjector())        # 3절 문장 투영
    <투영 sim>=0.4 k=5 Top-1 55.3% Top-3 78.0%>
    """

    def __init__(self, units, roles, settings=SETTINGS, gold=None):
        self.units = list(units)
        self.roles = [r for r in roles if r.get("job") in (gold or GOLD)]
        self.gold = gold or GOLD
        self.settings = settings
        self.extractor = RequirementExtractor()
        self.norm = L1Normalizer()

    # ── 공공 쪽 프로파일

    def profiles(self, fold=None):
        fold = fold or (lambda x: x)
        by: dict[str, list[set[str]]] = defaultdict(list)
        inst: dict[str, Counter] = defaultdict(Counter)
        for u in self.units:
            c = (u.ncs_code or "")[:6]
            if len(c) != 6:
                continue
            s = {fold(self.norm(x)) for k in self.settings.sections
                 for x in u.sections.get(k, [])}
            s = {x for x in s if len(x) >= 2}
            if len(s) >= 5:
                by[c].append(s)
                inst[c][u.institution or "?"] += 1
        keep = [c for c in by
                if JobMatrix.effective_units(inst[c], self.settings.institution_cap)
                >= self.settings.min_effective_units
                and JobMatrix.hhi(inst[c]) < self.settings.max_hhi]
        DF = {c: Counter(i for s in by[c] for i in s) for c in keep}
        ap: Counter = Counter()
        for c in keep:
            for i in DF[c]:
                ap[i] += 1
        idf = {i: math.log(len(keep) / a) for i, a in ap.items()}
        prof = {}
        for c in keep:
            items = sorted(DF[c].items(), key=lambda x: -x[1] * idf[x[0]])
            prof[c] = {i: idf[i] for i, _ in items[:self.settings.top_k]}
        return sorted(keep), prof

    # ── 질의 만들기

    def string_queries(self, fold=None):
        """문자열 방식 — 요건 문장을 L1 정규화해 토큰 집합으로."""
        fold = fold or (lambda x: x)
        out = []
        for r in self.roles:
            toks = set()
            for s in self.extractor.extract(r.get("text")):
                w = self.norm(s)
                if 2 <= len(w) <= 40:
                    toks.add(fold(w))
                # 문장 통째로는 절대 안 걸리므로 어절 조각도 같이 넣는다.
                # 문자열 방식에 최대한 유리하게 맞춰 준 뒤 비교하는 것이다.
                for piece in s.replace(",", " ").split():
                    p = self.norm(piece)
                    if len(p) >= 2:
                        toks.add(fold(p))
            if len(toks) >= 5:
                out.append((r["job"], toks))
        return out

    def projection_queries(self, projector, **kw):
        """3절 방식 — 문장을 임베딩해 역량 노드에 붙인다. 문자열 매칭 없음."""
        out = []
        for r in self.roles:
            nodes = projector.nodes(self.extractor.sentences(r.get("text")), **kw)
            if len(nodes) >= 3:
                out.append((r["job"], nodes))
        return out

    # ── 채점

    def score(self, queries, prof, codes, label) -> CrossScore:
        hit1 = hit3 = answered = 0
        for job, q in queries:
            sc = {c: sum(prof[c][i] for i in q if i in prof[c]) for c in codes}
            order = sorted(codes, key=lambda c: -sc[c])
            answered += sc[order[0]] > 0
            g = self.gold[job]
            hit1 += order[0][:2] in g
            hit3 += any(c[:2] in g for c in order[:3])
        n = max(len(queries), 1)
        return CrossScore(label, hit1 / n, hit3 / n, len(queries), answered / n)

    # ── 실행

    def string_match(self, dictionary=None, label=None) -> CrossScore:
        fold = dictionary.fold if dictionary else None
        codes, prof = self.profiles(fold)
        return self.score(self.string_queries(fold), prof, codes,
                          label or ("L1+L2" if dictionary else "L1만"))

    def projection(self, projector, dictionary=None, label=None,
                   **kw) -> CrossScore:
        fold = (dictionary or projector.dict).fold
        codes, prof = self.profiles(fold)
        sim = kw.get("min_similarity", self.settings.min_similarity)
        k = kw.get("top_k", self.settings.project_top_k)
        return self.score(self.projection_queries(projector, **kw), prof, codes,
                          label or f"투영 sim>={sim} k={k}")

    def __repr__(self) -> str:
        return f"<CrossDomainEvaluator 민간 질의 {len(self.roles)}개>"
