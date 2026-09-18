"""역량 사전 — 공공 축 + 확장 노드.

축을 이원화하는 이유는 실측이다. 민간 공고 요건을 공공 축에 투영했더니
60% 만 붙었고, 안 붙는 40% 는 AI·클라우드·CAD/CAE·ERP 처럼 덩어리로 빠졌다.
NCS 표준 개정 주기가 시장 속도를 못 따라가서 생기는 공백이다.

    공공 축     NCS 직무기술서에서 만든 역량 군집. 안정적이고 분류 체계가 붙어 있다.
    확장 노드   민간 공고에서 자동 추출. 공공에 없는 개념을 채운다.
                하위 연결 — 공공에 상위 개념이 있어 매달리는 것 (Spring → 소프트웨어개발프레임워크)
                신설 축   — 대응 개념이 아예 없어 새로 세우는 것 (LLM, 클라우드 인프라)

엔진을 두 개 만드는 게 아니다. 두 출처가 한 공간에 들어간다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS
from .cluster import ClusterResult
from .normalize import is_noise


@dataclass
class CompetencyNode:
    name: str
    source: str                                       # "public" | "extension"
    parent: str = ""                                  # 확장 노드의 상위 공공 노드
    members: list[str] = field(default_factory=list)  # 이 노드로 접히는 L1 항목


class CompetencyDictionary:
    """역량 노드의 집합. 문자열 → 노드 접기와 노드 목록 제공을 맡는다.

    >>> d = CompetencyDictionary.load()
    >>> d.fold("보안패치및업그레이드")
    '서버보안소프트웨어설치및운영'
    >>> len(d)
    2051
    """

    def __init__(self, clusters: ClusterResult,
                 extensions: dict[str, str] | None = None):
        self._map = dict(clusters.mapping)
        self._groups = dict(clusters.groups)
        self.extension_nodes = dict(extensions or {})  # 노드명 → 상위(빈 문자열이면 신설)
        # 잔해 노드는 투영 후보에서 뺀다. 두면 top_k 자리를 잡아먹는다 —
        # 실제로 `티잉크라운드클럽휴대및전달` 이 유사도 0.451 로 통과해
        # 맞는 역량 하나를 밀어냈다.
        self._names = sorted({n for n in (set(self._groups)
                                          | set(self.extension_nodes))
                              if not is_noise(n)})

    # ── 생성

    @classmethod
    def load(cls, clusters: str | Path | None = None,
             ext: str | Path | None = None,
             use_extensions: bool = True) -> "CompetencyDictionary":
        cr = ClusterResult.load(clusters or PATHS.l2_clusters)
        e: dict[str, str] = {}
        p = Path(ext or PATHS.ext_nodes)
        if use_extensions and p.exists():
            for n in json.loads(p.read_text(encoding="utf-8"))["nodes"]:
                parent = n.get("parent", "")
                # 신설 축은 축 이름을, 하위 연결은 용어 자체를 노드로 쓴다
                name = parent[4:] if parent.startswith("NEW:") else n["term"]
                e[name] = "" if parent.startswith("NEW:") else parent
        return cls(cr, e)

    # ── 조회

    @property
    def names(self) -> list[str]:
        return self._names

    def fold(self, term: str) -> str:
        """L1 항목을 군집 대표로 접는다. 사전에 없으면 그대로 돌려준다."""
        return self._map.get(term, term)

    def members(self, node: str) -> list[str]:
        return self._groups.get(node, [])

    def is_extension(self, node: str) -> bool:
        return node in self.extension_nodes

    def parent(self, node: str) -> str:
        return self.extension_nodes.get(node, "")

    def node(self, name: str) -> CompetencyNode:
        if name in self.extension_nodes:
            return CompetencyNode(name, "extension", self.extension_nodes[name])
        return CompetencyNode(name, "public", members=self._groups.get(name, []))

    def __len__(self) -> int:
        return len(self._names)

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def __repr__(self) -> str:
        pub = len(self._names) - len(self.extension_nodes)
        return (f"<CompetencyDictionary {len(self._names):,}개 "
                f"(공공 {pub:,} + 확장 {len(self.extension_nodes)})>")
