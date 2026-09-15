"""자연어 문장을 역량 노드에 붙인다. 설계 3절의 구현.

왜 문자열 매칭으로는 안 되는가
    `학회 운영진 8명 일정 조율` 에는 `일정계획준수` 라는 문자열이 없다.
    실측: 민간 공고 질의로 재면 문자열 방식 Top-1 32.0%, 임베딩 투영 60.3%.

왜 런타임에 LLM 을 안 부르는가
    느리고 비싸며, 같은 입력에 매번 다른 결과가 나오면 어제와 오늘 점수가 달라진다.
    사전이 고정이면 임베딩만으로 결정적이고 빠르다.

미매칭을 비워 두는 이유
    맞는 노드가 없어도 억지로 붙이면 근거 문장은 나오지만 말이 안 되는 근거가 된다.
    CLAUDE.md 는 근거를 못 대는 항목의 출력을 금지한다.
    미매칭은 버리지 않고 모은다 — 사전에 없는 개념을 찾는 단서이자,
    반복해서 쌓이는 표현이 다음 확장 노드 후보다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS, SETTINGS
from .dictionary import CompetencyDictionary


@dataclass(frozen=True)
class Projection:
    """역량 노드 하나와 그 근거."""

    node: str
    evidence: str                                     # 근거가 된 원문 문장
    similarity: float
    is_extension: bool = False


@dataclass
class ProjectionResult:
    hits: list[Projection] = field(default_factory=list)
    unmatched: list[tuple[str, float]] = field(default_factory=list)

    @property
    def nodes(self) -> set[str]:
        return {h.node for h in self.hits}

    def evidence_for(self, node: str) -> list[str]:
        return [h.evidence for h in self.hits if h.node == node]

    def __repr__(self) -> str:
        return (f"<ProjectionResult 노드 {len(self.nodes)}개 / "
                f"미매칭 {len(self.unmatched)}문장>")


class TextProjector:
    """문장 목록 → 역량 노드 + 근거.

    >>> p = TextProjector()
    >>> r = p.project(["사내 서버 취약점 점검해서 보안 패치 적용"])
    >>> r.hits[0].node, round(r.hits[0].similarity, 2)
    ('서버보안소프트웨어설치및운영', 0.73)
    """

    def __init__(self, dictionary: CompetencyDictionary | None = None,
                 model_name: str = SETTINGS.embed_model,
                 embedding_cache: str | Path | None = None):
        self.dict = dictionary or CompetencyDictionary.load()
        self.model_name = model_name
        self._cache = Path(embedding_cache or PATHS.l2_embeddings)
        self._model = None
        self._node_vectors = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def node_vectors(self):
        """노드 벡터. 군집 대표는 임베딩 캐시에서 꺼내고, 확장 노드만 새로 만든다."""
        if self._node_vectors is None:
            import numpy as np
            names = self.dict.names
            vec, missing, order = [], [], []
            if self._cache.exists():
                z = np.load(self._cache, allow_pickle=True)
                core = list(z["core"])
                EMB = z["E"]                           # npz 는 접근마다 압축을 푼다
                idx = {w: i for i, w in enumerate(core)}
                for n in names:
                    if n in idx:
                        vec.append(EMB[idx[n]])
                        order.append(n)
                    else:
                        missing.append(n)
            else:
                missing = list(names)
            if missing:
                vec += list(self.model.encode(
                    missing, batch_size=256, normalize_embeddings=True))
                order += missing
            self._names_ordered = order
            self._node_vectors = np.asarray(vec, dtype="float32")
        return self._node_vectors

    def project(self, sentences, min_similarity: float = SETTINGS.min_similarity,
                top_k: int = SETTINGS.project_top_k,
                min_length: int = 6) -> ProjectionResult:
        import numpy as np

        sents = [s.strip() for s in sentences if s and len(s.strip()) >= min_length]
        res = ProjectionResult()
        if not sents:
            return res

        R = self.node_vectors
        E = np.asarray(self.model.encode(
            sents, batch_size=256, normalize_embeddings=True), dtype="float32")
        sims = E @ R.T

        for si, row in enumerate(sims):
            order = np.argsort(-row)[:top_k]
            hit = [Projection(self._names_ordered[j], sents[si], float(row[j]),
                              self.dict.is_extension(self._names_ordered[j]))
                   for j in order if row[j] >= min_similarity]
            if hit:
                res.hits += hit
            else:
                res.unmatched.append((sents[si], float(row[order[0]])))
        return res

    def nodes(self, sentences, **kw) -> set[str]:
        return self.project(sentences, **kw).nodes
