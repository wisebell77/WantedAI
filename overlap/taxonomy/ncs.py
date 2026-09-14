"""NCS 공식 분류체계.

NCS(국가직무능력표준)는 자격기본법 근거로 고용노동부·한국산업인력공단이 관리하는
국가 표준이다. 대/중/소/세분류 4단계이고 2023년 기준 24 / 83 / 279 / 1,114 종이다.

정본은 NCS-KECO 연계표(hwp)에서 뽑는다. 우리가 직무기술서 본문에서 긁은 분류는
기관이 옮겨 적은 값이라 가운뎃점 표기가 다섯 가지로 갈리고 오기입도 섞인다
(소분류 코드의 45%). 정본이 있어야 정규화와 오류 검출이 된다.

덤으로 KECO(한국고용직업분류) 연계가 같이 들어온다. KECO 는 워크넷·고용24 의
직종코드 체계라, 민간 공고 직종을 NCS 축에 얹을 때 쓸 수 있다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

LEVEL = re.compile(r"^(\d{2})\.\s*(.+)$")
KECO_CODE = re.compile(r"^(\d{4})$")


def normalize(s: str) -> str:
    """가운뎃점·공백은 기관마다 제각각이라 지우고 비교한다."""
    return re.sub(r"\s+", "", re.sub(r"[·․‧∙・･ㆍ⋅ž,]", "", s))


@dataclass(frozen=True)
class NcsNode:
    code: str
    name: str

    @property
    def level(self) -> str:
        return {2: "대분류", 4: "중분류", 6: "소분류", 8: "세분류"}[len(self.code)]


class NcsTaxonomy:
    """공식 분류표를 들고 코드 ↔ 이름을 변환한다.

    >>> tax = NcsTaxonomy.load()
    >>> tax.name("200102")
    '정보기술개발'
    >>> tax.path("20010206")
    {'대분류': '정보통신', '중분류': '정보기술', '소분류': '정보기술개발', ...}
    """

    def __init__(self, levels: dict[str, dict[str, str]], keco: list[dict]):
        self._levels = levels                          # 단계명 → {코드: 이름}
        self.keco = keco
        self._by_code = {c: n for d in levels.values() for c, n in d.items()}
        self._major_by_name = {normalize(n): c
                               for c, n in levels["대분류"].items()}
        self._name_index = {
            lv: self._build_index(d) for lv, d in levels.items()
        }

    # ── 생성

    @classmethod
    def load(cls, path: str | Path | None = None) -> "NcsTaxonomy":
        from ..config import PATHS
        d = json.loads(Path(path or PATHS.taxonomy).read_text(encoding="utf-8"))
        levels = {lv: {x["코드"]: x["이름"] for x in d[lv]}
                  for lv in ("대분류", "중분류", "소분류", "세분류")}
        return cls(levels, d.get("keco", []))

    @classmethod
    def from_hwp(cls, hwp_path: str | Path) -> "NcsTaxonomy":
        """NCS-KECO 연계표(hwp)에서 직접 뽑는다.

        표 한 줄이 6칸이다.
            NCS 대분류 / 중분류 / 소분류 / 세분류 / KECO 코드 / KECO 세분류명
        """
        from ..parse.hwp import HwpTextExtractor

        lines = [l.strip() for l in
                 HwpTextExtractor().extract(hwp_path).splitlines() if l.strip()]
        rows, buf = [], []
        for l in lines:
            m = LEVEL.match(l)
            if m:
                if len(buf) >= 4:
                    buf = []
                buf.append((m.group(1), m.group(2).strip()))
                continue
            if KECO_CODE.match(l) and len(buf) == 4:
                buf.append(l)
                continue
            if len(buf) == 5:
                rows.append({"path": buf[:4], "keco": (buf[4], l)})
                buf = []

        levels = {"대분류": {}, "중분류": {}, "소분류": {}, "세분류": {}}
        keco = []
        for r in rows:
            codes = [c for c, _ in r["path"]]
            for i, lv in enumerate(("대분류", "중분류", "소분류", "세분류")):
                levels[lv]["".join(codes[:i + 1])] = r["path"][i][1]
            keco.append({"ncs세분류": "".join(codes),
                         "keco코드": r["keco"][0], "keco명": r["keco"][1]})
        return cls(levels, keco)

    def save(self, path: str | Path | None = None) -> None:
        from ..config import PATHS
        out = {lv: [{"코드": c, "이름": n} for c, n in sorted(d.items())]
               for lv, d in self._levels.items()}
        out["keco"] = self.keco
        Path(path or PATHS.taxonomy).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 조회

    def name(self, code: str) -> str:
        return self._by_code.get(code, "")

    def path(self, code: str) -> dict[str, str]:
        out = {}
        for lv, n in (("대분류", 2), ("중분류", 4), ("소분류", 6), ("세분류", 8)):
            if len(code) >= n:
                out[lv] = self._levels[lv].get(code[:n], "")
        return out

    def codes(self, level: str) -> list[str]:
        return sorted(self._levels[level])

    def major_code(self, name: str) -> str:
        return self._major_by_name.get(normalize(name), "")

    def lookup(self, name: str, level: str, under: str = "") -> list[str]:
        """이름으로 코드를 찾는다. under 로 상위 코드를 제한할 수 있다.

        이름 중복이 거의 없어 안전하다 — 중분류·세분류 0종, 소분류 1종('법무').
        긴 이름은 한 글자 차이를 허용한다. 기관이 `인쇄·목재·가공·공예` 처럼
        오타를 내는 경우가 있다(표준은 `가구`).
        """
        key = normalize(name)
        if len(key) < 2:
            return []
        idx = self._name_index[level]
        hits = idx.get(key, [])
        if not hits and len(key) >= 5:
            for k, v in idx.items():
                if len(k) == len(key) and sum(a != b for a, b in zip(k, key)) <= 1:
                    hits = v
                    break
        return [c for c in hits if c.startswith(under)] if under else list(hits)

    @staticmethod
    def _build_index(d: dict[str, str]) -> dict[str, list[str]]:
        idx: dict[str, list[str]] = {}
        for c, n in d.items():
            idx.setdefault(normalize(n), []).append(c)
        return idx

    def __repr__(self) -> str:
        n = {lv: len(d) for lv, d in self._levels.items()}
        return (f"<NcsTaxonomy 대{n['대분류']} 중{n['중분류']} "
                f"소{n['소분류']} 세{n['세분류']} · KECO 연계 {len(self.keco)}행>")
