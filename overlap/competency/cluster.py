"""L2 — 서로 다르게 쓰인 말을 같은 역량으로 묶는다.

    보안패치및업그레이드 · 서버보안소프트웨어설치및운영 · 운영체제취약점분석
    → 글자는 하나도 안 겹치지만 같은 자리의 역량이다.

LLM 을 어디에 쓰느냐가 방법론의 핵심이다.
    5만 종을 프롬프트에 넣을 수 없다. 쪼개 넣으면 묶음마다 군집 이름이 달라지고,
    매번 결과가 달라져 성능 비교가 무의미해진다. 요청마다 부르면 느리고 비싸다.

    그래서 군집 자체는 임베딩 + 거리 기준으로 만든다. 결정적이고 재현된다.
    LLM 은 오프라인에서 '군집 이름 다듬기'와 '경계 사례 검토'에만 쓴다.

거리 임계는 실측으로 정한다. 지금 값은 0.38 이다.

    느슨하게 묶어야 표현 차이를 넘는다. in-domain 평가에서는 조일수록 좋아
    보이지만, 방언이 다른 교차 평가에서는 거리를 키워야 올라간다
    (0.15 는 Top-1 24.7% 로 L1 에 수렴한다).

    **이 값은 어휘에 딸린 값이지 고정 상수가 아니다.** L1 정규화를 고쳐
    깨진 변형들이 합쳐지자 군집 대상이 8,965 → 12,644종으로 늘었고,
    같은 0.35 가 훨씬 잘게 쪼개면서(군집 2,047 → 2,597개) 교차 평가
    Top-1 이 61.1% → 56.7% 로 떨어졌다. 0.38 로 입도를 되돌리니
    (군집 2,045개) 59.8% / Top-3 79.1% 로 원래대로 돌아왔다.

    즉 떨어진 원인은 정규화가 아니라 입도였다. **어휘를 건드렸으면
    이 값을 다시 잡아야 한다.** pipelines/evaluate.py --clusters 로 잰다.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..config import SETTINGS
from .normalize import L1Normalizer


@dataclass
class ClusterResult:
    mapping: dict[str, str]                           # 항목 → 군집 대표
    groups: dict[str, list[str]]                      # 대표 → 구성원
    threshold: float
    model: str

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(
            {"model": self.model, "threshold": self.threshold,
             "map": self.mapping}, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ClusterResult":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        groups = defaultdict(list)
        for w, rep in d["map"].items():
            groups[rep].append(w)
        return cls(d["map"], dict(groups), d.get("threshold", 0.0),
                   d.get("model", ""))

    def __repr__(self) -> str:
        return (f"<ClusterResult 군집 {len(self.groups):,}개 / "
                f"항목 {len(self.mapping):,}종 · 거리 {self.threshold}>")


class L2Clusterer:
    """L1 어휘를 임베딩해 의미 군집을 만든다.

    임베딩은 무거우니 캐시한다. 임계만 바꿔 다시 군집할 때 재계산하지 않는다.

    >>> c = L2Clusterer()
    >>> res = c.fit(vocabulary_df, threshold=0.35)
    >>> res.mapping["보안패치및업그레이드"]
    '서버보안소프트웨어설치및운영'
    """

    def __init__(self, model_name: str = SETTINGS.embed_model,
                 cache: str | Path | None = None):
        self.model_name = model_name
        self.cache = Path(cache) if cache else None
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]):
        import numpy as np
        return np.asarray(self.model.encode(
            texts, batch_size=256, normalize_embeddings=True), dtype="float32")

    def fit(self, df: Counter, threshold: float = 0.35, min_df: int = 3,
            max_len: int = 40, tail_max: float = 0.30) -> ClusterResult:
        """df 는 {L1 항목: 등장 단위 수}.

        min_df 미만인 꼬리는 군집화 대상에서 빼고 최근접 대표에 붙인다.
        꼬리까지 군집화하면 계산이 제곱으로 늘고, 한 번 나온 오타가
        군집을 만들어 버린다.

        max_len 초과는 줄바꿈으로 붙은 파싱 잔해라 임베딩을 흐린다.
        """
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering

        core = [w for w, c in df.items() if c >= min_df and len(w) <= max_len]
        tail = [w for w, c in df.items() if c < min_df]

        E, TE = self._embeddings(core, tail)
        labels = AgglomerativeClustering(
            n_clusters=None, metric="cosine", linkage="average",
            distance_threshold=threshold).fit(E).labels_

        groups: dict[int, list[str]] = defaultdict(list)
        for w, g in zip(core, labels):
            groups[int(g)].append(w)
        rep = {g: max(ws, key=lambda w: (df[w], -len(w)))
               for g, ws in groups.items()}
        mapping = {w: rep[g] for g, ws in groups.items() for w in ws}

        if tail:                                      # 꼬리를 최근접 대표에 붙인다
            reps = sorted(set(rep.values()))
            idx = {w: i for i, w in enumerate(core)}
            RE = E[[idx[r] for r in reps]]
            sims = TE @ RE.T
            best, top = sims.argmax(axis=1), sims.max(axis=1)
            for w, b, s in zip(tail, best, top):
                if 1 - s <= tail_max:
                    mapping[w] = reps[b]

        out = defaultdict(list)
        for w, r in mapping.items():
            out[r].append(w)
        return ClusterResult(mapping, dict(out), threshold, self.model_name)

    # ── 임베딩 캐시

    def _embeddings(self, core: list[str], tail: list[str]):
        import numpy as np
        if self.cache and self.cache.exists():
            z = np.load(self.cache, allow_pickle=True)
            if list(z["core"]) == core and list(z["tail"]) == tail:
                # npz 는 접근할 때마다 압축을 푼다. 반복문 안에서 z["E"] 를 쓰면
                # 항목 수만큼 전체 배열을 다시 읽어 메모리가 터진다. 한 번만 꺼낸다.
                return z["E"], z["TE"]
        E = self.encode(core)
        TE = self.encode(tail) if tail else np.zeros((0, E.shape[1]), "float32")
        if self.cache:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                self.cache, E=E, TE=TE,
                core=np.array(core, dtype=object), tail=np.array(tail, dtype=object))
        return E, TE

    # ── 어휘 만들기

    @staticmethod
    def vocabulary(units, sections=SETTINGS.sections,
                   normalizer: L1Normalizer | None = None) -> Counter:
        """JobUnit 목록 → {L1 항목: 등장 단위 수}"""
        norm = normalizer or L1Normalizer()
        df: Counter = Counter()
        for u in units:
            if not u.ncs_code:
                continue
            seen = {norm(x) for k in sections for x in u.sections.get(k, [])}
            for w in seen:
                if len(w) >= 2:
                    df[w] += 1
        return df
