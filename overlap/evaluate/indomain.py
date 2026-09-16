"""내부 평가 — 정답이 이미 붙어 있는 데이터로 점수 방식을 고른다.

평가셋을 따로 만들 필요가 없다. 공공 직무기술서는 자기 NCS 소분류를 밝히고 있다.
한 단위의 역량 집합을 '사용자 프로필'처럼 넣고 원래 소분류를 맞히는지 보면 된다.

    leave-one-out 이 필수다. 프로파일을 만들 때 질의로 쓴 그 단위를 빼지 않으면
    자기 자신을 맞히는 셈이라 점수가 통째로 부풀려진다.

지표 셋
    Top-1   1위로 맞힌 비율
    MRR     정답 순위의 역수 평균. 1위=1.0, 2위=0.5, 5위=0.2
            Top-1 은 '맞다/아니다' 뿐이라 2위와 50위를 구분하지 못한다.
            화면에 5개를 보여 줄 거라면 MRR 이 더 실감에 가깝다.
    표본편향 '예측 1위 직무의 평균 단위 수' ÷ '질의 가중 평균 단위 수'.
            1.0 근처가 공정하다. 1 보다 크면 표본이 큰 직무로 쏠린 것이다.

            분모를 단순 평균으로 잡으면 안 된다. 질의는 직무마다
            단위 수만큼 나오므로, 아무 편향이 없어도 예측 1위의 평균 단위 수는
            질의 가중 평균(지금 데이터에서 229)에 수렴한다. 여기서 한 번 잘못 읽고
            상위 150 을 300 보다 낫다고 판단한 적이 있다.

이 평가의 한계는 분명하다. 질의도 직무기술서, 프로파일도 직무기술서라
같은 방언끼리 맞춘 것이다. `일정계획준수` 라는 질의가 `일정계획준수` 라는
프로파일 항목에 문자열로 그대로 걸린다. 실제 사용자는 그렇게 쓰지 않는다.
→ 이 점수만 믿으면 안 된다. evaluate.cross 를 함께 본다.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..competency.normalize import L1Normalizer
from ..config import SETTINGS
from ..recommend.matrix import JobMatrix


@dataclass(frozen=True)
class Score:
    label: str
    top1: float
    top3: float
    mrr: float
    bias: float
    queries: int

    def __repr__(self) -> str:
        return (f"<{self.label} Top-1 {self.top1*100:.1f}% "
                f"MRR {self.mrr:.3f} 편향 {self.bias:.2f} (질의 {self.queries:,})>")

    def row(self) -> str:
        return (f"  {self.label:<22}{self.top1*100:>7.1f}%{self.top3*100:>8.1f}%"
                f"{self.mrr:>8.3f}{self.bias:>9.2f}{self.queries:>8,}")

    @staticmethod
    def header() -> str:
        return (f"  {'설정':<22}{'Top-1':>7}{'Top-3':>8}{'MRR':>8}"
                f"{'표본편향':>9}{'질의':>8}")


class InDomainEvaluator:
    """공공 단위로 설정값을 비교한다.

    >>> ev = InDomainEvaluator(units)
    >>> ev.run(top_k=300, min_df=1)
    <top_k=300 min_df=1 Top-1 70.2% MRR 0.797 편향 0.89 (질의 4,323)>
    """

    def __init__(self, units, dictionary=None, settings=SETTINGS,
                 sections=None):
        norm = L1Normalizer()
        fold = dictionary.fold if dictionary else (lambda x: x)
        keys = sections or settings.sections
        self.settings = settings

        by: dict[str, list[set[str]]] = defaultdict(list)
        inst: dict[str, Counter] = defaultdict(Counter)
        for u in units:
            c = (u.ncs_code or "")[:6]
            if len(c) != 6:
                continue
            s = {fold(norm(x)) for k in keys for x in u.sections.get(k, [])}
            s = {x for x in s if len(x) >= 2}
            if len(s) < 5:                    # 역량이 너무 적은 단위는 질의가 못 된다
                continue
            by[c].append(s)
            inst[c][u.institution or "?"] += 1

        self.jobs = {c: v for c, v in by.items()
                     if JobMatrix.effective_units(inst[c], settings.institution_cap)
                     >= settings.min_effective_units
                     and JobMatrix.hhi(inst[c]) < settings.max_hhi}
        self.codes = sorted(self.jobs)
        self.N = {c: len(self.jobs[c]) for c in self.codes}

    @property
    def baseline(self) -> float:
        """질의 가중 평균 단위 수. 편향 계산의 분모."""
        tot = sum(self.N.values())
        return sum(n * n for n in self.N.values()) / tot if tot else 0.0

    def run(self, top_k: int | None = None, min_df: int | None = None,
            label: str = "") -> Score:
        top_k = top_k if top_k is not None else self.settings.top_k
        min_df = min_df if min_df is not None else self.settings.min_df
        codes = self.codes

        DF = {c: Counter(i for s in self.jobs[c] for i in s) for c in codes}
        appear: Counter = Counter()
        for c in codes:
            for i in DF[c]:
                appear[i] += 1
        idf = {i: math.log(len(codes) / a) for i, a in appear.items()}

        def profile(df: Counter) -> dict[str, float]:
            items = [(i, v) for i, v in df.items() if v >= min_df]
            items.sort(key=lambda x: -x[1] * idf.get(x[0], 0))
            return {i: idf.get(i, 0.0) for i, _ in items[:top_k]}

        base = {c: profile(DF[c]) for c in codes}

        hit1 = hit3 = total = 0
        rr, pred_n = [], []
        for true_c in codes:
            for q in self.jobs[true_c]:
                total += 1
                loo = DF[true_c].copy()       # leave-one-out
                for i in q:
                    loo[i] -= 1
                p_loo = profile(Counter({i: v for i, v in loo.items() if v > 0}))
                sc = {c: (sum(p_loo[i] for i in q if i in p_loo) if c == true_c
                          else sum(base[c][i] for i in q if i in base[c]))
                      for c in codes}
                order = sorted(codes, key=lambda c: -sc[c])
                rank = order.index(true_c) + 1
                hit1 += rank == 1
                hit3 += rank <= 3
                rr.append(1 / rank)
                pred_n.append(self.N[order[0]])

        b = self.baseline
        return Score(label or f"top_k={top_k} min_df={min_df}",
                     hit1 / total, hit3 / total, statistics.mean(rr),
                     (statistics.mean(pred_n) / b) if b else 0.0, total)

    def sweep(self, top_ks=(150, 300, 500), min_dfs=(1, 2)) -> list[Score]:
        return [self.run(k, d) for k in top_ks for d in min_dfs]

    def __repr__(self) -> str:
        return (f"<InDomainEvaluator 직무 {len(self.codes)}개 / "
                f"단위 {sum(self.N.values()):,}개>")
