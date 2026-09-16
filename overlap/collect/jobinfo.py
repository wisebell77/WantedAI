"""고용24 직무정보 — NCS 분류에 공식 설명을 붙인다.

문제: 분류 이름만으로는 무슨 일인지 안 와닿는다.
`정보기술전략·계획`, `건축설비설계·시공`, `산업안전관리공통직무` — NCS 를 모르면
이름만 보고는 알 수 없다. 추천 결과로 내밀면서 설명을 못 하면 곤란하다.

우리 분류표(NCS-KECO 연계표)에는 코드와 이름뿐이고 설명이 없다.
고용24 표준직무기술서 API(215L01)가 **능력단위 정의**를 준다.

    "빅데이터 분석 결과 시각화란 정보를 명확하고 효과적으로 전달하기 위해서
     분석 결과의 시각화 방식을 기획하여 설계하고 …"

주의할 점이 둘 있다.

    1. returnType=JSON 필수. XML 을 주면 서버가 예외를 던지고 HTML 을 돌려준다.
    2. **매처로 쓰면 안 된다.** `데이터 분석` 을 넣으면 금융 신용등급 사후관리가
       나온다. 능력단위명에 대한 소박한 문자열 매칭이다.
       그래서 여기서는 **사전으로만** 쓴다 — 이름으로 조회한 뒤
       코드가 우리가 찾던 분류와 일치하는 것만 남긴다.

코드는 URI 로 온다. `http://lod.work.go.kr/task/직무/_20010105` → `20010105`.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS, api_key
from .base import HttpClient, write_json

JOBINFO_URL = ("https://www.work24.go.kr/cm/openApi/call/wk/"
               "callOpenApiSvcInfo215L01.do")
CODE = re.compile(r"_(\d{2,8})\s*$")


def code_of(uri: str) -> str:
    """`http://lod.work.go.kr/task/직무/_20010105` → `20010105`"""
    m = CODE.search((uri or "").strip())
    return m.group(1) if m else ""


@dataclass
class Description:
    """분류 하나의 설명. 전부 공식 문서에서 온 문장이다."""

    code: str
    name: str
    units: list[str] = field(default_factory=list)      # 능력단위명
    definitions: list[str] = field(default_factory=list)  # 능력단위 정의

    @property
    def ok(self) -> bool:
        return bool(self.definitions)

    def summary(self, limit: int = 5) -> str:
        """한 줄 설명 — **능력단위 이름을 나열한다.**

        정의 하나를 골라 쓰면 안 된다. 능력단위 정의는 그 단위 하나를 설명하는
        문장이지 분류 전체를 설명하는 문장이 아니다. 첫 정의를 쓰면
        `정보기술전략·계획` 이 "핀테크 기술 분석이란…" 으로 소개된다 —
        여덟 능력단위 중 하나일 뿐인데 분류 전체인 양 나간다.

        이름을 나열하는 쪽이 정확하고 더 잘 읽힌다.
            빅데이터분석 → 빅데이터 분석 결과 시각화 · 분석 데이터 전처리 ·
                          빅데이터 분석 모델링 · …
        """
        if not self.units:
            return ""
        head = " · ".join(self.units[:limit])
        rest = len(self.units) - limit
        return head + (f" 외 {rest}개" if rest > 0 else "")

    def define(self, unit: str) -> str:
        """능력단위 하나의 공식 정의. 펼쳐 볼 때 쓴다."""
        for u, d in zip(self.units, self.definitions):
            if u == unit:
                return re.sub(r"\s+", " ", d).strip()
        return ""

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name,
                "units": self.units, "definitions": self.definitions}


class JobInfoClient:
    """표준직무기술서 조회. 이름으로 찾고 **코드로 거른다**.

    >>> c = JobInfoClient()
    >>> d = c.describe("20010105", "빅데이터분석")
    >>> d.summary()[:34]
    '빅데이터 분석 결과 평가 · 분석 데이터 피처(Feature) 엔지니어링'
    """

    def __init__(self, key: str | None = None, client: HttpClient | None = None,
                 delay: float = 0.4):
        self.key = key or api_key("WORK24_KEY_JOBDUTY") or api_key("WORK24_AUTH_KEY")
        self.http = client or HttpClient()
        self.delay = delay

    def query(self, word: str, limit: int = 30) -> list[dict]:
        try:
            r = self.http.get(JOBINFO_URL, authKey=self.key, returnType="JSON",
                              jobCont=word, limit=limit)
            res = (r.json() or {}).get("result") or {}
        except Exception:
            return []
        time.sleep(self.delay)
        out = []
        for unit_name, v in res.items():
            if isinstance(v, dict):
                out.append({"unit": unit_name,
                            "sdvn": code_of(v.get("job_sdvn_cd", "")),
                            "scla": code_of(v.get("job_scla_cd", "")),
                            "def": (v.get("ablt_def") or "").strip()})
        return out

    def describe(self, code: str, name: str, limit: int = 30) -> Description:
        """이름으로 조회하고 코드가 맞는 것만 남긴다.

        이름 조회가 빈손이면 이름을 쪼개서 한 번 더 본다.
        `건축설비설계·시공` 처럼 가운뎃점이 든 이름은 통째로는 안 걸린다.
        """
        rows = self.query(name, limit)
        hits = self._match(rows, code)
        if not hits:
            for part in re.split(r"[·\s/]+", name):
                if len(part) >= 2:
                    hits = self._match(self.query(part, limit), code)
                    if hits:
                        break
        return Description(code, name,
                           [h["unit"] for h in hits][:8],
                           [h["def"] for h in hits if h["def"]][:4])

    @staticmethod
    def _match(rows: list[dict], code: str) -> list[dict]:
        """세분류(8자리)면 sdvn 으로, 소분류(6자리)면 scla 로 거른다."""
        key = "sdvn" if len(code) == 8 else "scla"
        return [r for r in rows if r.get(key) == code]


class DescriptionStore:
    """받아 둔 설명을 파일 하나로 관리한다. 서비스는 이것만 읽는다."""

    def __init__(self, data: dict[str, dict] | None = None):
        self._d = data or {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "DescriptionStore":
        p = Path(path or PATHS.descriptions)
        if not p.exists():
            return cls({})
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path or PATHS.descriptions)
        write_json(p, self._d, indent=1)
        return p

    def put(self, d: Description) -> None:
        if d.ok:
            self._d[d.code] = d.to_dict()

    def get(self, code: str) -> Description | None:
        v = self._d.get(code)
        if not v:
            return None
        return Description(v["code"], v["name"], v.get("units", []),
                           v.get("definitions", []))

    def summary(self, code: str, limit: int = 5) -> str:
        d = self.get(code)
        return d.summary(limit) if d else ""

    def __contains__(self, code: str) -> bool:
        return code in self._d

    def __len__(self) -> int:
        return len(self._d)

    def __repr__(self) -> str:
        return f"<DescriptionStore 설명 {len(self._d)}개>"
