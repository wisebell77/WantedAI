"""자연어 문장을 역량 노드에 붙인다. 설계 3절의 구현.

왜 문자열 매칭으로는 안 되는가
    `학회 운영진 8명 일정 조율` 에는 `일정계획준수` 라는 문자열이 없다.
    실측: 민간 공고 질의로 재면 문자열 방식 Top-1 29.5%, 임베딩 투영 51.7%.

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
        self._idx = None

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
                min_length: int = 6,
                min_best: float | None = None) -> ProjectionResult:
        """문장들을 역량 노드에 붙인다.

        min_best 가 핵심이다. 절대 임계(min_similarity)만으로는
        **"맞는 게 하나도 없는 문장"**을 못 거른다. 실측:

            [DA팀 부팀장으로 팀의 정규 세션을 조율 및 진행했다]
               0.482 부서원과의팀웍지향   0.459 역할을정의하
               0.451 티잉크라운드클럽휴대및전달   0.449 Matlab   0.449 협업을통한조정

            상위 다섯이 0.03 안에 몰려 있다. 잘 맞는 게 없다는 뜻인데
            임계 0.40 은 전부 통과시킨다. 그래서 골프장 캐디 업무와 Matlab 이
            '학회 운영진 경험'의 근거로 화면에 올라갔다.

            반대로 잘 맞는 문장은 확실히 다르다.
            [빅데이터캠퍼스 데이터 활용, 인사이트 도출]
               0.617 금융데이터수집및가공   0.609 로그및데이터분석   0.580 자료분석

        그래서 **문장별 최고 유사도**를 먼저 본다. 그게 낮으면 그 문장은
        통째로 미매칭으로 돌린다. 억지로 붙이느니 "이 문장은 못 읽었다"고
        말하는 쪽이 정직하고, CLAUDE.md 가 요구하는 것도 그쪽이다.
        """
        import numpy as np

        sents = [s.strip() for s in sentences if s and len(s.strip()) >= min_length]
        res = ProjectionResult()
        if not sents:
            return res

        R = self.node_vectors
        E = np.asarray(self.model.encode(
            sents, batch_size=256, normalize_embeddings=True), dtype="float32")
        sims = E @ R.T

        floor = SETTINGS.min_best if min_best is None else min_best
        for si, row in enumerate(sims):
            order = np.argsort(-row)[:top_k]
            best = float(row[order[0]])
            hit = ([] if best < floor else
                   [Projection(self._names_ordered[j], sents[si], float(row[j]),
                               self.dict.is_extension(self._names_ordered[j]))
                    for j in order if row[j] >= min_similarity])
            if hit:
                res.hits += hit
            else:
                res.unmatched.append((sents[si], best))
        return res

    def nodes(self, sentences, **kw) -> set[str]:
        return self.project(sentences, **kw).nodes

    def proximity(self, sentences, nodes, min_length: int = 6):
        """주어진 노드마다 **가장 가까운 사용자 문장과 그 유사도**.

        project() 와 방향이 반대다. project 는 '이 문장에 붙는 노드'를 찾고,
        여기는 '이 노드에 가장 가까운 문장'을 찾는다.

        임계를 못 넘어 탈락한 것까지 본다. 그게 요점이다 —
        0.52 로 스친 역량은 "없다"가 아니라 "거의 닿았다"이고,
        사용자에게는 그쪽이 훨씬 쓸모 있는 정보다.
        """
        import numpy as np
        sents = [s.strip() for s in sentences if s and len(s.strip()) >= min_length]
        want = [n for n in nodes if n in self._index]
        if not sents or not want:
            return {}
        E = np.asarray(self.model.encode(
            sents, batch_size=256, normalize_embeddings=True), dtype="float32")
        R = self.node_vectors[[self._index[n] for n in want]]
        sims = E @ R.T                                 # 문장 x 노드
        out = {}
        for j, node in enumerate(want):
            i = int(sims[:, j].argmax())
            out[node] = (float(sims[i, j]), sents[i])
        return out

    @property
    def _index(self) -> dict[str, int]:
        if getattr(self, "_idx", None) is None:
            self.node_vectors                          # _names_ordered 를 채운다
            self._idx = {n: i for i, n in enumerate(self._names_ordered)}
        return self._idx
