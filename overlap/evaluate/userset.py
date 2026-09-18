"""사용자 방언 평가 — 취준생이 쓰는 문장으로 잰다.

교차 평가(evaluate.cross)도 "방언이 다른 질의"라고 했지만 정확히는
**공공 공고 vs 민간 공고**였다. 둘 다 공고다. 그래서 문제가 생겼다.

    요건 문장     "빅데이터 플랫폼 설치 및 운용 능력"      명사구
    사용자 문장   "교내 학술동아리에서 공공데이터 30만 행을
                  파이썬으로 정리하고 시각화했다"          서사

우리 역량 축은 공공 직무기술서의 역량 항목으로 만들었다. 요건 문장과 같은 꼴이라
유사도가 높게 나온다(평균 0.665, 94%가 0.55 초과). 사용자 문장은 다르다
(평균 0.540, 50%). **공고 문장으로 고른 임계는 사용자에게 너무 빡빡하다.**

실제로 그 일이 났다. `min_best` 를 공고 질의로 0.55 로 골랐더니
랜딩 프리셋 `데이터분석` 세 문장이 0.518 / 0.489 / 0.431 로 전부 잘려
빈 화면이 나왔다.

민간 공고의 **주요업무란**이 중간 방언일까 싶어 재 봤지만 아니었다.
잡음(연봉·안내 문구)을 걸러 내니 평균이 0.583 → 0.651 로 올라갔다.
채용공고는 주요업무도 명사구로 적는다. 서사가 아니다.

그래서 문장을 따로 만들었다(data/user_queries_written.json).
11개 분류 × 16문장. 분포를 확인한 결과 실제 사용자 문장과 거의 같다.

    작성 문장     평균 0.543 · 중앙값 0.549 · 0.55 초과 49%
    실제 사용자   평균 0.540 · 중앙값 0.549 · 0.55 초과 50%

**한계는 분명하다.** 이 문장들은 모델이 "취준생은 이렇게 쓸 것 같다"고 상상해
쓴 것이다. 분포가 맞는다고 문체까지 맞는다는 보장은 없다.
진짜 사람이 쓴 문장 20~40개를 받아 이 세트가 맞았는지 확인해야 한다.
그때까지 여기서 나온 값은 **잠정**이다.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from ..config import PATHS, SETTINGS
from .cross import GOLD, CrossScore
from ..recommend.matrix import JobMatrix


@dataclass(frozen=True)
class UserQuery:
    text: str
    job: str                                          # GOLD 의 키


class UserSetEvaluator:
    """사용자 방언 문장으로 직무를 맞히는지 본다.

    한 문장이 한 질의다. 공고 질의는 요건 문장을 여러 개 묶어 한 직무를
    맞혔지만, 사용자는 문장 하나만 던지기도 한다. 더 어려운 조건이고
    그게 실제 상황에 가깝다.

    >>> ev = UserSetEvaluator(units, dictionary)
    >>> ev.run(projector, min_best=0.50)
    <min_best 0.50 Top-1 41.5% Top-3 63.1%>
    """

    def __init__(self, units, dictionary=None, path: str | Path | None = None,
                 settings=SETTINGS, gold=None):
        self.gold = gold or GOLD
        self.settings = settings
        p = Path(path or PATHS.data / "user_queries_written.json")
        rows = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        self.queries = [UserQuery(r["text"], r["job"]) for r in rows
                        if r.get("job") in self.gold]
        m = JobMatrix.build(units, dictionary, settings=settings)
        self.codes = sorted(m.profiles)
        self.prof = {c: p_.weights for c, p_ in m.profiles.items()}

    def run(self, projector, label: str = "", **kw) -> CrossScore:
        hit1 = hit3 = answered = 0
        for q in self.queries:
            nodes = projector.nodes([q.text], **kw)
            if not nodes:
                continue                              # 못 읽은 문장은 세지 않는다
            answered += 1
            sc = {c: sum(self.prof[c][i] for i in nodes if i in self.prof[c])
                  for c in self.codes}
            order = sorted(self.codes, key=lambda c: -sc[c])
            g = self.gold[q.job]
            hit1 += order[0][:2] in g
            hit3 += any(c[:2] in g for c in order[:3])
        n = max(len(self.queries), 1)
        mb = kw.get("min_best", self.settings.min_best)
        return CrossScore(label or f"min_best {mb:.2f}", hit1 / n, hit3 / n,
                          len(self.queries), answered / n)

    def similarity_profile(self, projector) -> dict:
        """이 세트가 정말 사용자 방언인지 확인용."""
        best = []
        for q in self.queries:
            r = projector.project([q.text], min_best=0.0, top_k=1)
            best.append(r.hits[0].similarity if r.hits else 0.0)
        return {"n": len(best), "mean": statistics.mean(best),
                "median": statistics.median(best),
                "over_55": sum(1 for x in best if x >= 0.55) / len(best)}

    def __len__(self) -> int:
        return len(self.queries)

    def __repr__(self) -> str:
        return f"<UserSetEvaluator 사용자 질의 {len(self.queries)}개>"
