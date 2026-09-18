"""확장 노드 자동 추출 — 민간 공고에서 '공공 축에 없는 역량'을 찾는다.

왜 자동이어야 하나
    NCS 축은 표준 개정 주기만큼 뒤처진다. 실측하니 정보통신 685개 노드에
    클라우드·LLM·CI/CD·프론트엔드가 하나도 없었다.
    민간 코퍼스는 계속 늘어난다(공채속보 4일간 93건). 손으로 만든 표는
    한 달이면 낡으므로 갱신할 때마다 다시 뽑는다.

선정 기준 여섯 — 모두 통과해야 노드가 된다.

    C1 출처   요건·역량 문장에서만 뽑는다 (parse.RequirementExtractor).
              → 저작권 문구와 어학 성적이 기술어로 잡히던 것을 막는다.
    C2 빈도   서로 다른 민간 직무 min_df(기본 3)개 이상.
              한 번 나온 말은 그 공고의 사정이지 역량이 아니다.
    C3 분산   서로 다른 기업 min_corp(기본 2)곳 이상.
              C2 만으로는 한 회사가 직무를 여럿 올리면 통과해 버린다.
              사내 약어(BwG, PCC)를 걸러 내는 건 이 기준이다.
    C4 미충족 공공 축 전체에 없어야 한다. 공백을 지운 형태로 비교한다.
              정보통신 축만 보면 `안전관리` 같은 다른 소분류 개념이
              빈 것처럼 보이므로 전 분류의 노드를 합쳐서 본다.
    C5 형태   사람이 관리하는 차단 목록(ext_nodes_manual.json)에 없어야 한다.
              자동 판정이 못 거르는 것만 손으로 막는다. 목록은 짧게 유지한다.
    C6 드리프트 직전 결과와 비교해 신규·소멸을 남긴다.
              용어가 언제 들어오고 사라지는지가 곧 시장 변화 신호다.

상위 연결은 수동이다. 자동으로 부모를 정하면 틀렸을 때 조용히 틀린다.
    parent 있음        공공 노드 하위로 매단다 (Spring → 소프트웨어개발프레임워크)
    parent "NEW:이름"  대응 개념이 없어 새 축을 세운다
    parent 없음        연결 미정. 사전에는 올라가되 사람 확인 대기.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..config import PATHS
from ..parse.requirements import RequirementExtractor

# 후보 표면형 — 영문 토큰과, 기술어 어미로 끝나는 한글 복합어
EN = re.compile(r"\b[A-Za-z][A-Za-z0-9+#./_-]{1,22}\b")
KO = re.compile(r"([가-힣A-Za-z0-9]{2,14}?(?:개발|설계|분석|운영|관리|구축|처리|학습"
                r"|모델링|모델|서비스|플랫폼|아키텍처|자동화|최적화|검증|튜닝"
                r"|엔지니어링|마이닝|시각화|파이프라인|배포|보안|인프라))")


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


@dataclass
class ExtensionNode:
    term: str
    df: int                                   # 등장한 민간 직무 수
    corps: int                                # 등장한 기업 수
    parent: str = ""
    examples: list[dict] = field(default_factory=list)

    @property
    def is_new_axis(self) -> bool:
        return self.parent.startswith("NEW:")

    @property
    def node_name(self) -> str:
        return self.parent[4:] if self.is_new_axis else self.term


@dataclass
class ExtensionResult:
    nodes: list[ExtensionNode]
    candidates: int
    dropped: Counter
    roles: int
    new: list[str] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)

    def save(self, path=None, drift_path=None) -> None:
        p = Path(path or PATHS.ext_nodes)
        p.write_text(json.dumps({
            "asof": date.today().isoformat(), "roles": self.roles,
            "nodes": [{"term": n.term, "df": n.df, "corps": n.corps,
                       "parent": n.parent, "examples": n.examples}
                      for n in self.nodes]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        if self.new or self.gone:
            d = Path(drift_path or p.with_name("ext_nodes_drift.json"))
            hist = json.loads(d.read_text(encoding="utf-8")) if d.exists() else []
            hist.append({"asof": date.today().isoformat(),
                         "new": self.new, "gone": self.gone})
            d.write_text(json.dumps(hist, ensure_ascii=False, indent=1),
                         encoding="utf-8")

    def __repr__(self) -> str:
        return (f"<ExtensionResult 노드 {len(self.nodes)}개 "
                f"/ 후보 {self.candidates:,}종 · 신규 {len(self.new)}>")


class ExtensionBuilder:
    """민간 직무 목록 → 확장 노드.

    >>> b = ExtensionBuilder()
    >>> r = b.build(roles, public_nodes)
    >>> r.nodes[0].term
    'Kubernetes'
    """

    def __init__(self, min_df: int = 3, min_corp: int = 2,
                 manual: str | Path | None = None,
                 extractor: RequirementExtractor | None = None):
        self.min_df = min_df
        self.min_corp = min_corp
        self.extractor = extractor or RequirementExtractor()
        p = Path(manual or PATHS.data / "ext_nodes_manual.json")
        m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        self.block = {b.lower() for b in m.get("block", [])}
        self.alias = {k.lower(): v for k, v in m.get("alias", {}).items()}
        self.parent = m.get("parent", {})

    def terms(self, sentence: str) -> set[str]:
        out = {w for w in EN.findall(sentence) if len(w) > 1 and not w.isdigit()}
        return out | set(KO.findall(sentence))

    def build(self, roles, public_nodes, previous=None) -> ExtensionResult:
        """roles 는 {'text','corp','role','job'} 목록, public_nodes 는 공공 노드 이름들."""
        pub = squash("".join(public_nodes))

        df: Counter = Counter()
        corps: dict[str, set] = defaultdict(set)
        where: dict[str, list] = defaultdict(list)
        for r in roles:
            seen: set[str] = set()
            for s in self.extractor.extract(r.get("text")):   # C1
                seen |= self.terms(s)
            for w in seen:
                key = self.alias.get(w.lower(), w)
                df[key] += 1
                corps[key].add(r.get("corp", "?"))
                if len(where[key]) < 3:
                    where[key].append({"corp": r.get("corp", ""),
                                       "role": r.get("role", "")})

        kept, drop = [], Counter()
        for w, c in df.most_common():
            if c < self.min_df:
                drop["C2 빈도 미달"] += 1
            elif len(corps[w]) < self.min_corp:
                drop["C3 기업 분산 미달"] += 1
            elif squash(w) in pub:
                drop["C4 공공 축에 이미 있음"] += 1
            elif w.lower() in self.block:
                drop["C5 차단 목록"] += 1
            else:
                kept.append(ExtensionNode(
                    w, c, len(corps[w]),
                    self.parent.get(w, self.parent.get(w.lower(), "")),
                    where[w]))

        prev = set(previous or self.previous_terms())          # C6
        cur = {n.term for n in kept}
        return ExtensionResult(kept, len(df), drop, len(roles),
                               sorted(cur - prev) if prev else [],
                               sorted(prev - cur) if prev else [])

    @staticmethod
    def previous_terms(path=None) -> set[str]:
        p = Path(path or PATHS.ext_nodes)
        if not p.exists():
            return set()
        return {n["term"] for n in
                json.loads(p.read_text(encoding="utf-8"))["nodes"]}
