"""Overlap — 채용공고 역파싱 기반 역량 격차 · 인접 직무 매칭 엔진.

흐름은 한 방향이다.

    collect    →  parse   →  taxonomy  →  competency  →  recommend
    공고 수집     문서 해석    분류 확정     역량 사전       대조

    evaluate 는 어느 단계에서든 불려 '이 설정이 나은가'를 숫자로 답한다.

가장 짧은 사용법:

    from overlap import Recommender
    r = Recommender()
    for m in r.reverse(["학회 운영진으로 8명 일정 조율", "설문 300건 정리해 보고서 작성"]):
        print(m.sentence())
"""

from .config import PATHS, SETTINGS, Paths, Settings, api_key
from .competency.dictionary import CompetencyDictionary
from .llm import UpstageClient
from .competency.projector import TextProjector
from .recommend.evidence import EvidenceIndex
from .recommend.matrix import JobMatrix
from .recommend.scorer import Recommender

__all__ = ["PATHS", "SETTINGS", "Paths", "Settings", "api_key",
           "CompetencyDictionary", "TextProjector", "UpstageClient", "JobMatrix", "EvidenceIndex",
           "Recommender"]
