"""근거 인덱스 — "그 역량, 어느 공고가 그렇게 말했나".

행렬(JobMatrix)에는 역량이 **접힌 이름**으로만 들어 있다.
`서버보안소프트웨어설치및운영` 은 L1 정규화와 L2 군집을 거친 결과지,
공고에 그렇게 적혀 있는 게 아니다. 원문은 그 과정에서 버려진다.

버려진 그 원문이 곧 근거다. 공공 직무기술서의 `필요지식`·`필요기술` 항목이
그대로 남아 있기 때문이다.

    정보기술운영 · 서버보안소프트웨어설치및운영
      [7건] 서버 보안 및 단말 보안 소프트웨어 설치 및 운용기술
      [5건] 서버 보안 소프트웨어 설치 및 운영 기술
      [2건] 서버용 운영체제 설치 및 운용능력

    글자가 제각각인데 같은 자리의 역량으로 묶였다.
    L2 가 일하고 있다는 증거를 그대로 화면에 올릴 수 있다.

이게 없으면 CLAUDE.md 를 절반만 지킨 것이 된다.
    "모든 역량 판정은 실제 공고 문장에 근거해야 한다."
    사용자 문장만 보여 주면 "왜 이 직무가 그걸 요구한다는 건데?"에 답을 못 한다.
    정방향의 **부족한 역량**도 마찬가지다 — 그것도 "이 직무가 이걸 요구한다"는
    주장이므로 똑같이 공고 원문이 붙어야 한다.

공공과 민간을 다르게 다룬다.
    공공  ALIO 공개 문서다. 원문을 인용하고 기관·공고명·원문 링크를 같이 낸다.
    민간  확장 노드의 출처다. 본문 재배포가 조심스러우므로 **문장을 인용하지 않는다.**
          "어느 기업의 어떤 직무가 이 기술을 요구하고 있다"까지만 낸다.

크기
    (직무, 역량) 10,870쌍에 원문 상위 3개 + 출처 문서 id → 1.9MB (gzip 0.4MB).
    문서 메타는 중복 없이 따로 빼서 1,019건. 직무 하나만 떼면 gzip 49KB 라
    사용자가 펼칠 때만 그 조각을 불러오면 된다.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import PATHS, SETTINGS

# 직무명 자리에 들어온 잡음. RoleSplitter 의 앵커 휴리스틱이 표 헤더나
# 안내 문구를 직무명으로 집는 경우가 있다.
# ("어학성적결과 유효기준 : 2024. 9. 17 ~ 2026. 9. 16" 같은 것)
# 근거로 내보낼 수는 없으므로 화면에 올리기 전에 거른다.
ROLE_NOISE = re.compile(r"[:：~]|\d{4}\.\s*\d|^(학력|전공|어학|자격|우대|전형|접수)")


@dataclass(frozen=True)
class Source:
    """근거 문장이 나온 공고."""

    institution: str
    title: str = ""
    year: int | None = None
    url: str = ""

    def label(self) -> str:
        """`한국자산관리공사 2024년 2024년도 한국자산관리공사 신입직원 채용공고` 처럼
        기관명과 연도가 제목에 또 들어 있는 경우가 흔하다. 겹치는 부분을 지운다."""
        t = (self.title or "").strip()
        if self.institution and self.institution in t:
            t = t.replace(self.institution, "").strip(" -_·[]()")
        if self.year:
            t = re.sub(rf"^{self.year}\s*년도?\s*", "", t).strip(" -_·")
        y = f"{self.year}년 " if self.year else ""
        return " ".join(x for x in (self.institution, y + t) if x.strip()).strip()


@dataclass(frozen=True)
class Quote:
    """공공 직무기술서에 적힌 원문 표기 하나."""

    text: str
    postings: int                                     # 이 표기가 나온 문서 수
    sources: tuple[Source, ...] = ()

    def __repr__(self) -> str:
        return f"<Quote {self.text[:24]!r} ({self.postings}건)>"


@dataclass(frozen=True)
class RelatedPosting:
    """사용자 역량과 가장 많이 겹친 공고.

    **지난 공고다.** 2022~2025년 공공기관 채용공시에서 왔고 대부분 마감됐다.
    "지원하세요"가 아니라 "이 직무를 이렇게 정의한 공고"로 써야 한다.
    지금 지원 가능한 공고는 공채속보(민간) 쪽이고 성격이 다르다.
    """

    source: Source
    competencies: tuple[str, ...] = ()

    @property
    def overlap(self) -> int:
        return len(self.competencies)

    def sentence(self) -> str:
        return (f"{self.source.label()} — 당신과 겹치는 역량 "
                f"{self.overlap}개를 요구했습니다")

    def __repr__(self) -> str:
        return f"<RelatedPosting {self.source.institution} 겹침 {self.overlap}>"


@dataclass(frozen=True)
class MarketSignal:
    """민간 확장 노드 — 공공 축에 없는데 시장이 요구하는 것.

    문장을 인용하지 않는다. 어디서 요구하는지만 낸다.
    """

    node: str
    term: str
    parent: str                                       # "" 이면 신설 축
    roles: int                                        # 요구한 민간 직무 수
    corps: int                                        # 요구한 기업 수
    examples: tuple[tuple[str, str], ...] = ()        # (기업, 직무명)

    @property
    def is_new_axis(self) -> bool:
        return not self.parent

    def sentence(self) -> str:
        """판정이 아닌 관찰. 화면 문구의 기준형."""
        who = ", ".join(c for c, _ in self.examples[:3]) or "여러 기업"
        tail = "" if self.is_new_axis else f" (공공 축에서는 {self.parent})"
        return (f"{self.term} — 민간 공고 {self.roles}개 직무 · 기업 {self.corps}곳이 "
                f"요구하고 있습니다{tail}. 예: {who}")

    def __repr__(self) -> str:
        return f"<MarketSignal {self.term} 기업 {self.corps}곳>"


class EvidenceIndex:
    """(직무, 역량) → 공고 원문 / 확장 노드 → 시장 신호.

    >>> ev = EvidenceIndex.load()
    >>> ev.quotes("200103", "서버보안소프트웨어설치및운영")[0].text
    '서버 보안 및 단말 보안 소프트웨어 설치 및 운용기술'
    >>> ev.market("SAP").sentence()
    'SAP — 민간 공고 15개 직무 · 기업 14곳이 요구하고 있습니다. 예: 코텍, 엘에스전선, ...'
    """

    def __init__(self, items: dict, docs: dict, market: dict,
                 asof: str = ""):
        self._items = items                           # code → node → [{t,n,d}]
        self._docs = docs                             # fileNo → {i,t,y,u}
        self._market = market                         # node → {...}
        self.asof = asof

    # ── 생성

    @classmethod
    def build(cls, units, matrix, dictionary, top: int = 3,
              max_sources: int = 3, settings=SETTINGS) -> "EvidenceIndex":
        """직무 단위에서 원문 표기를 되찾는다.

        행렬을 만들 때와 **같은 접기 함수**를 써야 한다. 다르면 행렬에 있는
        역량의 근거가 비어 버린다. 그래서 dictionary 를 인자로 받는다.
        """
        from ..competency.normalize import L1Normalizer
        norm = L1Normalizer()
        fold = dictionary.fold if dictionary else (lambda x: x)

        raw: dict[tuple[str, str], Counter] = defaultdict(Counter)
        where: dict[tuple[str, str], dict[str, set]] = defaultdict(
            lambda: defaultdict(set))
        for u in units:
            code = (u.ncs_code or "")[:6]
            if code not in matrix:
                continue
            weights = matrix[code].weights
            for k in settings.sections:
                for item in u.sections.get(k, []):
                    node = fold(norm(item))
                    if node not in weights:
                        continue
                    text = " ".join((item or "").split())
                    if not text:
                        continue
                    raw[(code, node)][text] += 1
                    where[(code, node)][text].add(u.file_no)

        meta = cls.document_meta()
        items: dict[str, dict[str, list]] = defaultdict(dict)
        used: set[str] = set()
        for (code, node), cnt in raw.items():
            rows = []
            for text, n in cnt.most_common(top):
                ds = sorted(where[(code, node)][text])[:max_sources]
                used.update(ds)
                rows.append({"t": text, "n": n, "d": ds})
            items[code][node] = rows

        return cls(dict(items), {k: v for k, v in meta.items() if k in used},
                   cls.market_meta(), date.today().isoformat())

    @staticmethod
    def document_meta(path=None) -> dict[str, dict]:
        """fileNo → 기관·공고명·연도·원문 링크. 중복을 없애려고 따로 뺀다."""
        out: dict[str, dict] = {}
        for f in Path(path or PATHS.data).glob("jd_docs_*.json"):
            try:
                rows = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            for d in rows:
                out[str(d["fileNo"])] = {
                    "i": d.get("inst", ""), "t": (d.get("title") or "")[:60],
                    "y": d.get("year"), "u": d.get("srcUrl", "")}
        return out

    @staticmethod
    def market_meta(path=None) -> dict[str, dict]:
        """확장 노드 → 민간 출처. 본문은 담지 않는다 — 기업·직무명까지만."""
        p = Path(path or PATHS.ext_nodes)
        if not p.exists():
            return {}
        out = {}
        for n in json.loads(p.read_text(encoding="utf-8"))["nodes"]:
            parent = n.get("parent", "")
            new_axis = parent.startswith("NEW:")
            name = parent[4:] if new_axis else n["term"]
            seen, ex = set(), []
            for e in n.get("examples", []):
                corp, role = e.get("corp", ""), (e.get("role", "") or "").strip()
                if not corp or corp in seen:          # 같은 기업을 두 번 세지 않는다
                    continue
                seen.add(corp)
                ex.append([corp, "" if ROLE_NOISE.search(role) else role])
            out[name] = {
                "term": n["term"], "parent": "" if new_axis else parent,
                "df": n.get("df", 0), "corps": n.get("corps", 0), "ex": ex[:3]}
        return out

    # ── 조회

    def quotes(self, code: str, node: str, limit: int = 2) -> list[Quote]:
        """(직무, 역량) 의 공고 원문.

        세분류 코드(8자리)로 물으면 상위 소분류(6자리) 것을 돌려준다.
        근거 인덱스는 소분류 단위로만 만든다 — 세분류까지 만들면 (직무, 역량)
        쌍이 11,113 → 57,600 으로 늘어 파일이 다섯 배가 된다.
        세분류 단위는 소분류 단위의 부분집합이므로 같은 공고 풀에서 나온다.
        """
        rows = self._items.get(code, {}).get(node, [])
        if not rows and len(code) == 8:
            rows = self._items.get(code[:6], {}).get(node, [])
        rows = rows[:limit]
        return [Quote(r["t"], r["n"],
                      tuple(self._source(d) for d in r.get("d", [])))
                for r in rows]

    def _source(self, file_no: str) -> Source:
        m = self._docs.get(str(file_no), {})
        return Source(m.get("i", ""), m.get("t", ""), m.get("y"), m.get("u", ""))

    def postings(self, code: str, nodes, limit: int = 3) -> list[RelatedPosting]:
        """사용자 역량과 가장 많이 겹친 공고를 위에서부터.

        별도 색인을 두지 않는다. 근거를 저장할 때 이미 (직무, 역량)마다
        출처 문서 id 를 달아 뒀으므로, 그 문서들을 세기만 하면 된다.
        새 데이터도 추가 용량도 필요 없다.

        같은 문서가 여러 역량의 근거로 잡힐수록 그 직무를 잘 대표한다.
        """
        by_doc: dict[str, set] = defaultdict(set)
        rows = self._items.get(code, {})
        for n in nodes:
            for r in rows.get(n, []):
                for d in r.get("d", []):
                    by_doc[d].add(n)
        ranked = sorted(by_doc.items(), key=lambda x: (-len(x[1]), x[0]))
        out = []
        for doc, comps in ranked[:limit]:
            src = self._source(doc)
            if src.institution:                       # 출처를 못 대면 내보내지 않는다
                out.append(RelatedPosting(src, tuple(sorted(comps))))
        return out

    def market(self, node: str) -> MarketSignal | None:
        m = self._market.get(node)
        if not m:
            return None
        return MarketSignal(node, m["term"], m.get("parent", ""), m.get("df", 0),
                            m.get("corps", 0),
                            tuple((c, r) for c, r in m.get("ex", [])))

    def has(self, code: str, node: str) -> bool:
        return bool(self._items.get(code, {}).get(node))

    def for_job(self, code: str) -> dict[str, list]:
        """직무 하나만 떼어낸 조각. 화면에서 지연 로딩할 때 쓴다."""
        return self._items.get(code, {})

    # ── 저장

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path or PATHS.evidence)
        p.parent.mkdir(parents=True, exist_ok=True)
        # indent 없이 쓴다. 근거는 사람이 읽는 파일이 아니라 서비스가 읽는 파일이고,
        # 들여쓰기를 넣으면 크기가 두 배가 된다.
        p.write_text(json.dumps(
            {"asof": self.asof, "docs": self._docs, "items": self._items,
             "market": self._market}, ensure_ascii=False), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path | None = None) -> "EvidenceIndex":
        p = Path(path or PATHS.evidence)
        if not p.exists():
            return cls({}, {}, {})
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(d.get("items", {}), d.get("docs", {}), d.get("market", {}),
                   d.get("asof", ""))

    def __len__(self) -> int:
        return sum(len(v) for v in self._items.values())

    def __bool__(self) -> bool:
        return bool(self._items or self._market)

    def __repr__(self) -> str:
        return (f"<EvidenceIndex 직무 {len(self._items)}개 / "
                f"근거 {len(self):,}쌍 · 출처 문서 {len(self._docs):,}건 · "
                f"확장 {len(self._market)}개>")
