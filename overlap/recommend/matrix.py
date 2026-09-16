"""직무 × 역량 행렬.

입도는 NCS 소분류다.
    대분류 24종은 너무 거칠다 — 정보통신 하나에 백엔드·보안·AI 가 다 들어간다.
    세분류 1,114종은 표본이 3~9개라 통계가 안 된다.
    소분류 279종에서 개발·기획·운영이 갈린다.

프로파일은 직무당 60단위까지만 쓴다(settings.profile_unit_cap).
큰 직무가 어휘 폭만으로 이기는 것을 막는다 — 실측 편향배율 2.07 → 1.31.
근거로 내보내는 공고 수(units)는 줄이지 않는다. 그건 실제 표본 크기다.

포함 기준은 두 가지를 함께 본다.
    유효단위 >= 30   기관당 8단위 상한을 건 뒤의 수
    HHI < 0.25       허핀달 지수. 한 기관 쏠림

단위 수만 보면 속는다. `재료 > 소성·소결세라믹제조` 는 100단위로 5위권인데
기관이 2곳(한국세라믹기술원 96%)이라 유효단위 12 로 떨어진다. 통계가 아니라 사례다.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS, SETTINGS


@dataclass
class JobProfile:
    """직무 하나의 역량 프로파일."""

    code: str                                         # NCS 소분류 코드
    name: str
    units: int
    institutions: int
    weights: dict[str, float] = field(default_factory=dict)   # 역량 → IDF
    df: dict[str, int] = field(default_factory=dict)          # 역량 → 등장 단위 수
    sampled: int = 0
    """프로파일을 만들 때 실제로 쓴 단위 수(표본 크기를 맞춘 뒤).
    units 는 근거가 되는 전체 공고 수라 화면에 그대로 쓴다 — 줄이지 않는다."""

    def score(self, competencies) -> float:
        return sum(self.weights[c] for c in competencies if c in self.weights)

    def matched(self, competencies) -> list[str]:
        """겹치는 역량. IDF 높은 순 — 변별력 있는 것부터 보여준다."""
        return sorted((c for c in competencies if c in self.weights),
                      key=lambda c: -self.weights[c])

    def missing(self, competencies) -> list[str]:
        """이 직무가 요구하는데 사용자에게 없는 것."""
        have = set(competencies)
        return sorted((c for c in self.weights if c not in have),
                      key=lambda c: -self.df.get(c, 0))


class JobMatrix:
    """소분류별 역량 프로파일 모음.

    >>> m = JobMatrix.build(units, dictionary)
    >>> m["200102"].name
    '정보기술개발'
    >>> m.rank({"소프트웨어아키텍처", "프로그램디버깅"})[:2]
    [('200102', 7.4), ('200101', 3.1)]
    """

    def __init__(self, profiles: dict[str, JobProfile]):
        self.profiles = profiles

    # ── 생성

    @classmethod
    def build(cls, units, dictionary=None, taxonomy=None,
              settings=SETTINGS, level: int = 6,
              min_units: int | None = None) -> "JobMatrix":
        """JobUnit 목록 → 행렬.

        dictionary 를 주면 역량을 L2 군집 대표로 접는다.

        level 6 이 기본(소분류)이고 8 이면 세분류다. 세분류 행렬은 추천 후보가
        아니라 **소분류 안에서 어느 쪽에 더 가까운지 줄 세우는 용도**다.
        표본이 적어 단독 추천에는 못 쓴다 — 그래서 min_units 로 문턱을 따로 준다.
        """
        from ..competency.normalize import L1Normalizer, is_noise
        norm = L1Normalizer()
        fold = dictionary.fold if dictionary else (lambda x: x)

        by: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
        inst: dict[str, Counter] = defaultdict(Counter)
        for u in units:
            code = (u.ncs_code or "")[:level]
            if len(code) != level:
                continue
            s = {fold(norm(x)) for k in settings.sections
                 for x in u.sections.get(k, [])}
            s = {x for x in s if not is_noise(x)}
            if len(s) < 5:
                continue
            by[code].append((u.institution or "?", s))
            inst[code][u.institution or "?"] += 1

        if min_units is None:
            keep = {c for c in by
                    if cls.effective_units(inst[c], settings.institution_cap)
                    >= settings.min_effective_units
                    and cls.hhi(inst[c]) < settings.max_hhi}
        else:
            # 세분류는 소분류 안의 줄 세우기용이라 문턱을 단위 수로만 본다.
            # 여기에 유효단위·HHI 를 걸면 정보기술개발 안의 `빅데이터분석` 처럼
            # 정작 보여 주고 싶은 것이 통째로 사라진다.
            keep = {c for c in by if len(by[c]) >= min_units}

        # 표본 크기를 맞춘다. 큰 직무가 어휘 폭만으로 이기는 것을 막는다.
        used = {c: cls.level_units(by[c], settings.profile_unit_cap) for c in keep}
        DF = {c: Counter(i for _, s in used[c] for i in s) for c in keep}
        # 화면에 쓰는 건수는 전체 코퍼스 기준이어야 한다. 표본을 60 으로 맞춘 건
        # 선별과 가중치를 공정하게 하려는 것이지, 근거를 줄이려는 게 아니다.
        # 여기서 안 되돌리면 "공고 37건에서 요구"가 "공고 8건"으로 표기된다.
        FULL = {c: Counter(i for _, s in by[c] for i in s) for c in keep}
        appear = Counter()
        for c in keep:
            for i in DF[c]:
                appear[i] += 1
        n = max(len(keep), 1)
        idf = {i: math.log(n / a) for i, a in appear.items()}

        profiles = {}
        for c in keep:
            items = [(i, v) for i, v in DF[c].items() if v >= settings.min_df]
            # 선별은 df x IDF. df 만 쓰면 `문서작성`·`의사소통` 같은 범용어가
            # 상위를 차지하고, IDF 만 쓰면 한 번 나온 파싱 오류가 1등이 된다
            # (가장 희귀하므로). 곱해야 '이 직무가 실제로 요구하면서 고유한 것'이 남는다.
            items.sort(key=lambda x: -x[1] * idf.get(x[0], 0))
            items = items[:settings.top_k]
            profiles[c] = JobProfile(
                code=c,
                name=(taxonomy.name(c) if taxonomy else c),
                units=len(by[c]), institutions=len(inst[c]),
                weights={i: idf[i] for i, _ in items},
                df={i: FULL[c][i] for i, _ in items},
                sampled=len(used[c]))
        return cls(profiles)

    @staticmethod
    def level_units(rows, cap: int):
        """직무당 cap 단위만 고른다. 기관을 번갈아 가며.

        무작위로 뽑으면 빌드할 때마다 행렬이 달라져 어제와 오늘 결과를
        비교할 수 없다. 기관 이름과 등장 순서로 정렬해 **결정적**으로 고른다.

        기관을 번갈아 가는 건 덤이 아니라 핵심이다. 앞에서부터 60개를 자르면
        공고를 많이 낸 기관이 표본을 통째로 차지한다 — 유효단위·HHI 로
        막으려던 바로 그 문제가 프로파일 안에서 되살아난다.
        """
        if cap <= 0 or len(rows) <= cap:
            return list(rows)
        groups: dict[str, list] = defaultdict(list)
        for institution, s in rows:
            groups[institution].append(s)
        order = sorted(groups)                        # 기관 수가 적은 쪽부터가 아니라
        out, i = [], 0                                # 이름순 — 재현을 위해서다
        while len(out) < cap:
            picked = False
            for institution in order:
                bucket = groups[institution]
                if i < len(bucket):
                    out.append((institution, bucket[i]))
                    picked = True
                    if len(out) >= cap:
                        break
            if not picked:
                break
            i += 1
        return out

    # ── 지표

    @staticmethod
    def effective_units(institution_counts: Counter, cap: int) -> int:
        """기관당 cap 개까지만 센 실질 표본 크기."""
        return sum(min(v, cap) for v in institution_counts.values())

    @staticmethod
    def hhi(institution_counts: Counter) -> float:
        """허핀달 지수. 1 에 가까울수록 한 기관 독점."""
        n = sum(institution_counts.values())
        return sum((v / n) ** 2 for v in institution_counts.values()) if n else 1.0

    # ── 조회

    def rank(self, competencies, limit: int | None = None):
        s = [(c, p.score(competencies)) for c, p in self.profiles.items()]
        s.sort(key=lambda x: -x[1])
        return s[:limit] if limit else s

    def __getitem__(self, code: str) -> JobProfile:
        return self.profiles[code]

    def __contains__(self, code: str) -> bool:
        return code in self.profiles

    def __len__(self) -> int:
        return len(self.profiles)

    def __iter__(self):
        return iter(self.profiles.values())

    # ── 저장

    def save(self, path: str | Path | None = None) -> None:
        p = Path(path or PATHS.job_matrix)
        p.write_text(json.dumps({
            c: {"name": pr.name, "units": pr.units, "institutions": pr.institutions,
                "sampled": pr.sampled, "weights": pr.weights, "df": pr.df}
            for c, pr in self.profiles.items()}, ensure_ascii=False, indent=1),
            encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path | None = None) -> "JobMatrix":
        d = json.loads(Path(path or PATHS.job_matrix).read_text(encoding="utf-8"))
        return cls({c: JobProfile(c, v["name"], v["units"], v["institutions"],
                                  v["weights"], v["df"], v.get("sampled", 0))
                    for c, v in d.items()})

    def __repr__(self) -> str:
        return f"<JobMatrix 직무 {len(self.profiles)}개>"
