"""민간 공고 수집 — 실시간 공고와 확장 노드의 재료.

역할이 공공과 다르다. 공공은 **학습·추천 모집단**이고, 민간은
    1. 교차 평가의 질의 (evaluate.cross)
    2. 확장 노드의 재료 (competency.extensions)
    3. 화면에 띄우는 '지금 열려 있는 공고'
이다. 민간으로 프로파일을 만들지 않는다 — 건수가 모자라고 분류 라벨도 없다.

출처는 고용24 공채속보(210L21) 하나다.
    본문이 없고 외부 URL 만 준다. 그래서 목록을 받아 두고 본문은 따로 가져온다.
    total 이 340 안팎인 **스냅샷**이라 과거 조회가 안 된다.
    4일 만에 93건이 새로 올라오고 132건이 마감돼 사라졌다.
    주기적으로 받아 누적하는 수밖에 없고, 마감분도 우리 쪽에는 계속 보관한다.
    고용24 키를 쓰므로 공공데이터포털(ALIO) 일일 한도와 무관하다.

본문은 세 경로로 들어온다. 한 공고에 여러 버전이 있으면 긴 쪽을 쓴다.
    static    requests 로 바로 받은 HTML
    browser   Playwright 로 렌더링해야 나오는 것 (SPA 채용 페이지)
    ocr       공고 전체가 이미지인 경우. 사람이 읽어 텍스트로 옮긴다

    순서를 지켜야 한다. static 수집만으로 코퍼스를 덮어쓰면 browser·ocr 로
    건진 것이 조용히 사라진다. 실제로 221건이 131건으로 줄었다.
    그래서 합치는 일은 PrivateCorpus.merge() 한 곳에서만 한다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..config import PATHS, api_key
from .base import HttpClient, read_json, write_json

GONGCHAE_URL = ("https://www.work24.go.kr/cm/openApi/call/wk/"
                "callOpenApiSvcInfo210L21.do")

FIELDS = ("empSeqno", "empWantedTitle", "empBusiNm", "coClcdNm",
          "empWantedStdt", "empWantedEndt", "empWantedTypeNm",
          "empWantedHomepgDetail", "empWantedMobileUrl")

# 본문이 '채용공고답게' 생겼는지 보는 신호어
SIGNALS = ["자격요건", "주요업무", "담당업무", "수행업무", "업무내용", "우대",
           "지원자격", "모집분야", "모집부문", "직무", "경력", "전형"]


@dataclass
class GongchaeDiff:
    total: int
    new: list[dict] = field(default_factory=list)
    gone: int = 0
    stored: int = 0

    def __repr__(self) -> str:
        return (f"<GongchaeDiff 누적 {self.stored} / 신규 {len(self.new)} "
                f"/ 마감 {self.gone}>")


class GongchaeClient:
    """공채속보 목록. XML 만 준다(JSON 파라미터가 먹지 않는다).

    >>> GongchaeClient().refresh()
    <GongchaeDiff 누적 337 / 신규 12 / 마감 9>
    """

    def __init__(self, key: str | None = None, client: HttpClient | None = None,
                 store: str | Path | None = None):
        self.key = key or api_key("WORK24_KEY_RECRUIT")
        self.http = client or HttpClient()
        self.store = Path(store or PATHS.data / "gongchae_all.json")

    def fetch(self, max_pages: int = 20) -> list[dict]:
        out, page = [], 1
        total = 0
        while page <= max_pages:
            r = self.http.get(GONGCHAE_URL, authKey=self.key, callTp="L",
                              returnType="XML", startPage=page, display=100)
            blocks = re.findall(r"<dhsOpenEmpInfo>(.*?)</dhsOpenEmpInfo>",
                                r.text, re.S)
            for b in blocks:
                rec = {}
                for f in FIELDS:
                    m = re.search(rf"<{f}>(.*?)</{f}>", b, re.S)
                    rec[f] = (m.group(1).strip() if m else "")
                out.append(rec)
            m = re.search(r"<total>(\d+)</total>", r.text)
            total = int(m.group(1)) if m else total
            if not blocks or len(out) >= total:
                break
            page += 1
        self.total = total
        return out

    def refresh(self) -> GongchaeDiff:
        """받아서 누적한다. 사라진 공고도 보관분은 유지한다."""
        cur = self.fetch()
        old = read_json(self.store, []) or []
        seen = {r.get("empSeqno") for r in old}
        new = [r for r in cur if r.get("empSeqno") not in seen]
        gone = len(seen - {r.get("empSeqno") for r in cur})
        today = date.today().isoformat()
        for r in new:
            r["_firstSeen"] = today
        merged = old + new
        write_json(self.store, merged, indent=1)
        return GongchaeDiff(getattr(self, "total", len(cur)), new, gone,
                            len(merged))


class PrivateCorpus:
    """세 캐시를 합쳐 본문 코퍼스를 만든다. 합치는 곳은 여기 하나뿐이다.

    >>> c = PrivateCorpus()
    >>> good = c.merge()
    >>> len(good)
    291
    """

    def __init__(self, static=None, browser=None, ocr=None):
        self.static = Path(static or PATHS.private_static)
        self.browser = Path(browser or PATHS.private_browser)
        self.ocr = Path(ocr or PATHS.private_ocr)

    @staticmethod
    def _load(folder: Path, src: str) -> dict[str, dict]:
        out = {}
        if not folder.exists():
            return out
        for f in folder.glob("*.json"):
            r = read_json(f)
            if r:
                r["src"] = src
                out[str(r.get("seq"))] = r
        return out

    def merge(self) -> list[dict]:
        merged = dict(self._load(self.static, "static"))
        for seq, r in self._load(self.browser, "browser").items():
            cur = merged.get(seq)
            if cur is None or r.get("len", 0) > cur.get("len", 0):
                merged[seq] = r
        # 이미지 판독분은 메타(기업·제목·URL)를 기존 레코드에서 가져오고
        # 본문만 교체한다. 이미지가 곧 공고 전문이므로 무조건 채택한다.
        for seq, r in self._load(self.ocr, "ocr").items():
            base = dict(merged.get(seq, {}))
            base.update({"text": r["text"], "len": r["len"], "sig": 99,
                         "status": "ok", "src": "ocr", "seq": seq})
            for k in ("corp", "title", "dom", "url"):
                base.setdefault(k, "")
            merged[seq] = base

        rows, seen, uniq = list(merged.values()), set(), []
        for r in rows:                              # 같은 기업 + 같은 도입부 = 중복
            key = (r.get("corp", ""), (r.get("text") or "")[:300])
            if key not in seen:
                seen.add(key)
                uniq.append(r)

        good = [r for r in uniq if self.usable(r)]
        self.stats = Counter(r["src"] for r in good)
        self.all_rows = uniq
        return good

    @staticmethod
    def usable(r: dict) -> bool:
        """본문을 확보했다고 볼 수 있는가.

        판독분에 500자 기준을 그대로 적용하면 안 된다. 사람이 읽어 옮긴
        텍스트는 네비게이션이 없어 군더더기가 빠진 만큼 짧다.
        완결된 단일 직무 공고가 길이 미달로 떨어지는 일이 실제로 있었다.

        `sig` 도 같은 이유로 길이가 충분하면 묻지 않는다. SIGNALS 는 12 개뿐이라
        같은 말을 다르게 적은 공고가 걸린다 — 코레일유통 `일반직(IT개발) 경력사원`
        3,971 자가 sig 1 로, 한국학중앙연구원 2,063 자가 sig 0 으로 떨어졌다.
        **sig 가 낮은 건 "공고가 아니다"가 아니라 "표현이 다르다"이다.**
        1,500 자를 넘겨 놓고 채용공고가 아닌 문서는 수집 경로상 나오지 않는다.
        이 면제로 6 건이 돌아왔고 잡음은 하나도 들어오지 않았다(285 → 291).
        """
        if r.get("status") != "ok":
            return False
        if r.get("src") == "ocr":
            return r.get("len", 0) >= 200
        if r.get("len", 0) >= 1500:
            return True
        return r.get("len", 0) >= 500 and r.get("sig", 0) >= 4

    @staticmethod
    def signal_count(text: str) -> int:
        return sum(1 for s in SIGNALS if s in (text or ""))

    def save(self, good: list[dict], path: str | Path | None = None) -> Path:
        p = Path(path or PATHS.data / "jd_good.json")
        write_json(p, good, indent=1)
        return p
