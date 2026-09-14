"""ALIO 공공기관 채용공시 수집 — 학습·추천 모집단을 만드는 곳.

왜 공공기관인가
    민간 공고는 본문을 주는 공개 API 가 사실상 없다. 고용24 채용정보 API 는
    개인회원에게 막혀 있고(직업정보제공사업 신고확인증이 필요하다),
    플랫폼 크롤링은 CLAUDE.md 가 금지한다(원티드는 이 대회 주최사다).
    ALIO 는 NCS 기반 직무기술서를 첨부로 공개한다. 분류 라벨이 붙은
    한국어 직무 문서를 수천 건 모을 수 있는 유일한 합법 경로다.

호출 구조는 3단이다
    목록 1회 / 100건  →  상세 1회 / 공고  →  파일 1회 / 첨부
    연도당 공고가 1.2만 건이라 전수 조회는 일일 한도(1만)를 넘는다.
    그래서 NCS 대분류별로 표본을 잘라 받는다(per_ncs). 통계용으로는 충분하다.

수집 순서가 데이터 품질을 좌우한다 — 여기가 이 파일의 핵심이다.
    1. 분류 순서대로 처리하면 예산이 떨어졌을 때 뒤쪽 분류(정보통신 등)가 통째로 빈다.
       → 분류별로 번갈아 간다.
    2. 한 기관 공고를 연달아 받으면 그 기관이 분류를 대표해 버린다.
       재료 143단위 중 기관이 5곳(한 곳이 87%)이었던 게 그 결과다.
       → 분류 안에서도 기관별로 번갈아 가고, 이미 max_per_inst 단위를
         확보한 기관은 건너뛴다.
    이 상한은 evaluate.coverage 의 유효단위 계산과 같은 숫자를 쓴다.
    '무엇을 더 받아야 하나'와 '무엇을 신뢰할 수 있나'가 같은 기준이어야 한다.

라벨은 조회한 분류가 아니라 공고 자신의 분류를 쓴다.
    공고의 67% 가 복수 분류를 갖는다. 질의 분류로 라벨을 박으면
    뒤 순서 분류가 통째로 사라진다.
    (더 정확한 라벨은 문서 안 분류체계 표에서 읽는다 → taxonomy.NcsResolver)
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS, SETTINGS, api_key
from .attachments import PARSEABLE, AttachmentFetcher
from .base import Budget, HttpClient, QuotaExceeded, SourceDown, read_json, write_json

LIST_URL = "https://apis.data.go.kr/1051000/recruitment/list"
DETAIL_URL = "https://apis.data.go.kr/1051000/recruitment/detail"

NCS_MAJOR = {
    "R600001": "사업관리", "R600002": "경영.회계.사무", "R600003": "금융.보험",
    "R600004": "교육.자연.사회과학", "R600005": "법률.경찰.소방", "R600006": "보건.의료",
    "R600007": "사회복지.종교", "R600008": "문화.예술.디자인.방송", "R600009": "운전.운송",
    "R600010": "영업판매", "R600011": "경비.청소", "R600012": "이용.숙박.여행.오락",
    "R600013": "음식서비스", "R600014": "건설", "R600015": "기계", "R600016": "재료",
    "R600017": "화학", "R600018": "섬유.의복", "R600019": "전기.전자", "R600020": "정보통신",
    "R600021": "식품가공", "R600022": "인쇄.목재.가구", "R600023": "환경.에너지.안전",
    "R600024": "농림어업", "R600025": "연구",
}

JD_PATTERN = re.compile(
    r"직무기술서|직무\s?설명|직무\s?소개|직무설명자료|job\s?description", re.I)


class AlioClient:
    """공시 목록·상세 조회. 상세는 캐시한다(같은 공고를 두 번 사지 않는다)."""

    def __init__(self, key: str | None = None, client: HttpClient | None = None):
        self.key = key or api_key("DATA_GO_KR_KEY")
        if not self.key:
            raise SystemExit("DATA_GO_KR_KEY 가 비어 있다. .env 를 확인할 것.")
        self.http = client or HttpClient()
        PATHS.alio_detail.mkdir(parents=True, exist_ok=True)

    def _call(self, url: str, budget: Budget, **params):
        return self.http.json(url, budget, serviceKey=self.key,
                              resultType="json", **params)

    def list_year(self, ncs_code: str, year: int, count: int,
                  budget: Budget) -> list[dict]:
        out, page = [], 1
        while len(out) < count and budget:
            d = self._call(LIST_URL, budget, numOfRows=min(100, count - len(out)),
                           pageNo=page, ncsCdLst=ncs_code,
                           pbancBgngYmd=f"{year}-01-01", pbancEndYmd=f"{year}-12-31")
            got = (d or {}).get("result") or []
            out += got
            if len(got) < min(100, count):
                break
            page += 1
            time.sleep(0.1)
        return out

    def detail(self, sn, budget: Budget) -> dict | None:
        cache = PATHS.alio_detail / f"detail_{sn}.json"
        d = read_json(cache)
        if d is None:
            if not budget:
                return None
            d = self._call(DETAIL_URL, budget, sn=sn)
            if d is None:
                return None
            write_json(cache, d)
            time.sleep(0.05)
        return d


@dataclass
class JobDoc:
    """확보한 직무기술서 한 건의 메타."""

    year: int
    ncs: str
    ncs_all: list[str]
    institution: str
    title: str
    sn: str
    file_no: str
    file: str
    length: int
    url: str = ""

    def to_dict(self) -> dict:
        return {"year": self.year, "ncs": self.ncs, "ncs_all": self.ncs_all,
                "inst": self.institution, "title": self.title, "sn": self.sn,
                "fileNo": self.file_no, "file": self.file, "len": self.length,
                "srcUrl": self.url}


@dataclass
class CollectResult:
    docs: list[JobDoc] = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)
    skipped: int = 0
    down: str = ""
    budget_left: int = 0

    def merge_into(self, path: str | Path) -> int:
        """기존 목록에 없는 것만 덧붙인다. 재실행해도 중복되지 않는다."""
        prev = read_json(path, []) or []
        known = {(d["sn"], d["fileNo"]) for d in prev}
        merged = prev + [d.to_dict() for d in self.docs
                         if (d.sn, d.file_no) not in known]
        write_json(path, merged, indent=1)
        return len(merged)

    def __repr__(self) -> str:
        return (f"<CollectResult 확보 {len(self.docs)}건 "
                f"/ 건너뜀 {self.skipped} / 예산 {self.budget_left}>")


class PublicCollector:
    """연도 하나를 수집한다.

    >>> c = PublicCollector()
    >>> res = c.collect(2025, per_ncs=200, budget=Budget(2500))
    >>> res.merge_into(PATHS.data / "jd_docs_2025.json")
    2294
    """

    def __init__(self, client: AlioClient | None = None,
                 fetcher: AttachmentFetcher | None = None,
                 max_per_inst: int = SETTINGS.institution_cap,
                 max_files: int = 250):
        self.api = client or AlioClient()
        self.files = fetcher or AttachmentFetcher()
        self.max_per_inst = max_per_inst
        self.max_files = max_files

    # ── 이미 가진 것

    def existing(self) -> Counter:
        """(분류, 기관) 별로 이미 확보한 직무 단위 수.

        분류 이름이 질의용(NCS 딕셔너리)과 문서에서 읽은 것이 조금 다르다.
        '법률.경찰.소방' vs '법률.경찰.소방.교도.국방' — 짧은 쪽 기준으로 맞춘다.
        """
        units = read_json(PATHS.units, []) or []
        if not units:
            return Counter()
        inst_of = {}
        for f in PATHS.data.glob("jd_docs_*.json"):
            for d in read_json(f, []) or []:
                inst_of[d["fileNo"]] = d.get("inst", "")
        cnt: Counter = Counter()
        for u in units:
            names = u.get("ncs") or []
            if len(names) != 1:
                continue
            inst = inst_of.get(u["fileNo"], "")
            if not inst:
                continue
            for q in NCS_MAJOR.values():
                if names[0].startswith(q) or q.startswith(names[0]):
                    cnt[(q, inst)] += 1
                    break
        return cnt

    # ── 순서 잡기

    def interleave(self, posts: list[dict], have: Counter) -> tuple[list[dict], int]:
        grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        skipped = 0
        for p in posts:
            nm = p.get("_ncs", "")
            inst = p.get("instNm", "") or "?"
            if have.get((nm, inst), 0) >= self.max_per_inst:
                skipped += 1
                continue
            grouped[nm][inst].append(p)

        order = []
        while any(any(v.values()) for v in grouped.values()):
            for nm in list(grouped):
                insts = grouped[nm]
                for inst in sorted(insts, key=lambda i: (have.get((nm, i), 0), i)):
                    if insts[inst]:
                        order.append(insts[inst].pop(0))
                        break
        return order, skipped

    # ── 수집

    def collect(self, year: int, per_ncs: int = 40,
                budget: Budget | None = None,
                only: list[str] | None = None,
                on_progress=None) -> CollectResult:
        budget = budget or Budget(4000)
        targets = {c: n for c, n in NCS_MAJOR.items()
                   if not only or any(w in n for w in only)}

        posts = []
        for code, nm in targets.items():
            for r in self.api.list_year(code, year, per_ncs, budget):
                r["_ncs"] = nm
                posts.append(r)
        seen = set()
        posts = [p for p in posts
                 if not (p["recrutPblntSn"] in seen or seen.add(p["recrutPblntSn"]))]
        posts, skipped = self.interleave(posts, self.existing())

        res = CollectResult(skipped=skipped)
        before = self.files.downloaded_count()
        for i, p in enumerate(posts, 1):
            d = self.api.detail(p["recrutPblntSn"], budget)
            if d is None:
                if not budget:
                    break
                # 일시 실패로 전체를 멈추면 뒤쪽 분류가 통째로 빈다. 이 건만 거른다.
                res.stats["상세 조회 실패"] += 1
                continue
            if self._one(year, p, d, budget, res) is False:
                break
            if self.files.downloaded_count() - before >= self.max_files:
                res.stats["첨부 상한 도달"] += 1
                break
            if on_progress and i % 50 == 0:
                on_progress(i, len(posts), len(res.docs), budget.left)

        res.budget_left = budget.left
        return res

    def _one(self, year: int, post: dict, detail: dict, budget: Budget,
             res: CollectResult) -> bool | None:
        """공고 한 건의 첨부를 처리한다. False 를 돌려주면 전체 중단."""
        r = (detail or {}).get("result") or {}
        files = [f for f in (r.get("files") or [])
                 if JD_PATTERN.search(f.get("atchFileNm", ""))
                 and f.get("atchFileNm", "").lower().endswith(PARSEABLE)]
        if not files:
            res.stats["직무기술서 없음"] += 1
            return None

        for f in files:
            if not budget:
                return False
            try:
                a = self.files.fetch(f["recrutAtchFileNo"], f["atchFileNm"], budget)
            except SourceDown as e:
                res.down = str(e)
                return False
            except QuotaExceeded:
                raise
            except Exception as e:
                # 첨부 하나가 이상해도 그날 받은 것을 다 잃으면 안 된다.
                # (깨진 인코딩·파싱 폭탄으로 실제로 500건을 날렸다)
                res.stats[f"첨부 처리 실패({type(e).__name__})"] += 1
                continue
            if a is None:
                return False
            res.stats["성공" if a.usable else (a.error or "본문 짧음")] += 1
            if a.usable:
                own = [x.strip() for x in (r.get("ncsCdNmLst") or "").split(",")
                       if x.strip()] or [post.get("_ncs", "")]
                res.docs.append(JobDoc(
                    year=year, ncs=own[0], ncs_all=own,
                    institution=r.get("instNm", ""),
                    title=r.get("recrutPbancTtl", ""),
                    sn=str(post["recrutPblntSn"]), file_no=a.file_no,
                    file=a.name, length=len(a.text),
                    url=r.get("srcUrl", "")))
        return None
