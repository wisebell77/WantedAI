"""분류별 표본이 쓸 만한지 본다. 수집을 어디에 더 써야 하는지도 여기서 나온다.

단위 수만 보면 속는다. `재료` 는 143단위로 상위권인데 그중 124개(87%)가
한국세라믹기술원 하나였다. 그 분류의 '요구 역량'은 통계가 아니라
한 기관의 채용 관행이다.

그래서 네 가지를 같이 본다.

    단위      전체 직무 단위 수
    기관      서로 다른 기관 수
    HHI       허핀달 지수 — 기관 점유율의 제곱합. 1 이면 한 곳 독점
    유효단위  기관당 cap 개까지만 세었을 때의 수 — 실질 표본 크기

유효단위와 HHI 를 함께 보는 이유는 서로 못 잡는 구멍이 달라서다.
    유효단위는 '기관이 몇이나 되나'를 본다. 소수 기관 독점을 잘 잡는다.
    HHI 는 '고르게 퍼져 있나'를 본다. 기관 수는 많은데 상위 두세 곳이
    절반을 넘는 경우를 잡는다. 유효단위만으로는 이게 통과해 버린다.

미달 분류에는 '새 기관 몇 곳이 더 필요한가'를 같이 낸다.
수집은 공고 수를 늘리는 일이 아니라 기관을 늘리는 일이기 때문이다.
collect 쪽 --max-per-inst 가 이 계산과 짝을 이룬다.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from ..config import SETTINGS
from ..recommend.matrix import JobMatrix


@dataclass
class CoverageRow:
    code: str
    name: str
    units: int
    institutions: int
    hhi: float
    effective: int
    top_share: float
    top_institutions: list[tuple[str, int]]

    def passes(self, goal: int, max_hhi: float) -> bool:
        return self.effective >= goal and self.hhi < max_hhi

    def reason(self, goal: int, max_hhi: float) -> str:
        if self.effective < goal:
            return f"유효단위 -{goal - self.effective}"
        if self.hhi >= max_hhi:
            return f"HHI {self.hhi:.2f} 초과"
        return "달성"

    def __repr__(self) -> str:
        return (f"<CoverageRow {self.name} {self.units}단위 · "
                f"기관 {self.institutions} · HHI {self.hhi:.2f} · "
                f"유효 {self.effective}>")

    def needed_institutions(self, goal: int, cap: int) -> int:
        """부족분을 메우려면 새 기관이 몇 곳 필요한가 (기관당 cap 단위 가정)."""
        gap = max(goal - self.effective, 0)
        return -(-gap // cap)


class CoverageReport:
    """분류별 표본 현황.

    >>> rep = CoverageReport(units)
    >>> rep.short()[0]
    <CoverageRow 재료 143단위 · 기관 5 · HHI 0.77 · 유효 28>
    """

    def __init__(self, units, taxonomy=None, level: int = 6,
                 settings=SETTINGS):
        self.settings = settings
        by: dict[str, Counter] = defaultdict(Counter)
        for u in units:
            c = (u.ncs_code or "")[:level]
            if len(c) == level:
                by[c][u.institution or "?"] += 1

        self.rows = []
        for c, ins in by.items():
            n = sum(ins.values())
            self.rows.append(CoverageRow(
                code=c, name=(taxonomy.name(c) if taxonomy else c),
                units=n, institutions=len(ins),
                hhi=JobMatrix.hhi(ins),
                effective=JobMatrix.effective_units(ins, settings.institution_cap),
                top_share=max(ins.values()) / n,
                top_institutions=ins.most_common(3)))
        self.rows.sort(key=lambda r: -r.units)

    def passing(self, goal: int | None = None) -> list[CoverageRow]:
        g = goal or self.settings.min_effective_units
        return [r for r in self.rows if r.passes(g, self.settings.max_hhi)]

    def short(self, goal: int | None = None) -> list[CoverageRow]:
        g = goal or self.settings.min_effective_units
        return [r for r in self.rows if not r.passes(g, self.settings.max_hhi)]

    def concentrated(self, threshold: float = 0.4) -> list[CoverageRow]:
        return [r for r in self.rows if r.top_share >= threshold]

    def table(self, goal: int | None = None, limit: int | None = None) -> str:
        g = goal or self.settings.min_effective_units
        cap = self.settings.institution_cap
        out = [f"기관당 상한 {cap}단위 · 목표 유효단위 {g} · HHI 상한 {self.settings.max_hhi}",
               "",
               f"  {'분류':<22}{'단위':>6}{'기관':>5}{'HHI':>7}{'유효':>6}   상태"]
        out.append("-" * 70)
        rows = self.rows[:limit] if limit else self.rows
        for r in rows:
            flag = "  <-편중" if r.top_share >= 0.4 else ""
            out.append(f"  {r.name[:20]:<22}{r.units:>6}{r.institutions:>5}"
                       f"{r.hhi:>7.2f}{r.effective:>6}   "
                       f"{r.reason(g, self.settings.max_hhi)}{flag}")
        out.append("-" * 70)
        out.append(f"  통과 {len(self.passing(g))}개 / 전체 {len(self.rows)}개")
        return chr(10).join(out)

    def collection_plan(self, goal: int | None = None) -> str:
        """수집 우선순위 — 어느 분류에 새 기관이 몇 곳 더 필요한가."""
        g = goal or self.settings.min_effective_units
        cap = self.settings.institution_cap
        rows = sorted(self.short(g), key=lambda r: -r.needed_institutions(g, cap))
        out = [f"미달 {len(rows)}개 - 필요한 새 기관 수 (기관당 {cap}단위 가정)"]
        for r in rows:
            out.append(f"  {r.name[:20]:<22} 유효 {r.effective:>4} "
                       f"→ 새 기관 {r.needed_institutions(g, cap):>2}곳")
        return chr(10).join(out)

    def __len__(self) -> int:
        return len(self.rows)

    def __repr__(self) -> str:
        return (f"<CoverageReport 분류 {len(self.rows)}개 / "
                f"통과 {len(self.passing())}개>")
