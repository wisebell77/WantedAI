"""첨부 파일 하나를 받아 텍스트로 만든다.

공공기관은 NCS 기반 직무기술서를 **별도 첨부**로 낸다.
공고 본문(aplyQlfcCn)에는 행정 요건만 있고, 실제 역량(능력단위·필요지식·
필요기술·직무수행태도)은 이 파일 안에 있다. 이 모듈이 없으면 프로젝트가 성립하지 않는다.

받는 곳이 API 와 다르다.
    API      apis.data.go.kr        — 공공데이터포털. 한도는 넉넉하다
    파일     www.alio.go.kr         — 속도 제한이 있다. 쉬지 않고 받으면
                                      몇백 건 만에 IP 가 막히고 수십 분간 TCP 연결조차 안 된다
    (opendata.alio.go.kr 경로는 죽어 있다. download.json?fileNo= 만 살아 있다)

그래서 기본 1.5초씩 쉬면서 받는다. 막히면 복구 대기가 훨씬 길다 —
천천히 받는 편이 결국 빠르다.

캐시는 두 겹이다.
    jdfiles/{fileNo}.{ext}   원본 바이트. 파싱 규칙을 고쳐도 다시 안 받는다
    jdtext/{fileNo}.json     파싱 결과. 같은 파일을 다시 열지 않는다
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..config import PATHS
from ..parse.hwp import HwpTextExtractor
from .base import Budget, SourceDown, read_json, write_json

FILE_URL = "https://www.alio.go.kr/download/download.json?fileNo={}"
PARSEABLE = (".pdf", ".hwp", ".hwpx", ".zip")


@dataclass
class Attachment:
    file_no: str
    name: str
    bytes: int
    text: str
    error: str = ""

    @property
    def usable(self) -> bool:
        """300자 미만은 표지만 있는 스캔본이거나 파싱 실패다."""
        return len(self.text) >= 300

    def to_dict(self) -> dict:
        return {"fileNo": self.file_no, "name": self.name, "bytes": self.bytes,
                "text": self.text, "len": len(self.text), "err": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> "Attachment":
        return cls(d["fileNo"], d["name"], d.get("bytes", 0),
                   d.get("text", ""), d.get("err", ""))


class AttachmentFetcher:
    """첨부 다운로드 + 텍스트 추출 + 캐시.

    >>> f = AttachmentFetcher()
    >>> a = f.fetch("123456", "2025년 직무기술서.hwp", Budget(100))
    >>> a.usable
    True
    """

    def __init__(self, client=None, delay: float = 1.5,
                 max_connect_fails: int = 5, hwp=None):
        from .base import HttpClient
        self.client = client or HttpClient()
        self.delay = delay
        self.max_connect_fails = max_connect_fails
        self.fails = 0
        self.hwp = hwp or HwpTextExtractor()
        PATHS.jd_files.mkdir(parents=True, exist_ok=True)
        PATHS.jd_text.mkdir(parents=True, exist_ok=True)

    # ── 파싱

    def parse(self, data: bytes, name: str) -> str:
        """PDF / HWP / HWPX / ZIP → 텍스트. ZIP 은 안을 재귀로 훑는다."""
        low = name.lower()
        try:
            if low.endswith(".pdf") or data[:4] == b"%PDF":
                import fitz
                doc = fitz.open(stream=data, filetype="pdf")
                return chr(10).join(p.get_text() for p in doc)
            if low.endswith(".zip") or data[:4] == b"PK" + bytes([3, 4]):
                if low.endswith(".hwpx"):         # hwpx 도 zip 이라 먼저 시도
                    t = self.hwp.extract(data)
                    if len(t) > 200:
                        return t
                return self.parse_zip(data)
            if low.endswith((".hwp", ".hwpx")) or data[:4] == bytes(
                    [0xD0, 0xCF, 0x11, 0xE0]):
                return self.hwp.extract(data)
        except Exception:
            return ""
        return ""

    def parse_zip(self, data: bytes) -> str:
        out = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for inner in z.namelist():
                if inner.endswith("/") or not inner.lower().endswith(PARSEABLE[:3]):
                    continue
                try:
                    sub = z.read(inner)
                except Exception:
                    continue
                try:                               # 압축 안 이름은 cp949 로 깨져 있다
                    shown = inner.encode("cp437").decode("cp949")
                except Exception:
                    shown = inner
                t = self.parse(sub, shown)
                if t.strip():
                    out.append(f"[{shown}]" + chr(10) + t)
        return (chr(10) * 2).join(out)

    # ── 수집

    def fetch(self, file_no, name: str, budget: Budget) -> Attachment | None:
        cached = read_json(PATHS.jd_text / f"{file_no}.json")
        if cached:
            return Attachment.from_dict(cached)

        data = self.bytes_of(file_no, name, budget)
        if data is None:
            return None
        if isinstance(data, Attachment):           # 다운로드 실패 기록
            return data

        text = self.parse(data, name)
        # 어떤 경로로 들어오든 UTF-8 로 못 쓰는 문자가 섞이면 수집 전체가 죽는다.
        # 파일 하나 때문에 그날 받은 것을 다 잃지 않도록 여기서 한 번 더 막는다.
        text = text.encode("utf-8", "replace").decode("utf-8")
        text = re.sub(chr(10) + "{3,}", chr(10) * 2, text).strip()

        a = Attachment(str(file_no), name, len(data), text,
                       "" if text else "파싱 실패")
        write_json(PATHS.jd_text / f"{file_no}.json", a.to_dict())
        return a

    def bytes_of(self, file_no, name: str, budget: Budget):
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        cache = PATHS.jd_files / f"{file_no}{ext}"
        if cache.exists():
            return cache.read_bytes()
        if not budget:
            return None
        try:
            # (연결, 읽기) 분리. 연결이 안 되는 상황을 90초씩 기다릴 이유가 없다.
            r = self.client.get(FILE_URL.format(file_no), timeout=(5, 90))
            budget.spend()
            data = r.content
            self.fails = 0
            time.sleep(self.delay)
        except Exception as e:
            budget.spend()
            conn = type(e).__name__ in ("ConnectTimeout", "ConnectionError")
            self.fails = self.fails + 1 if conn else 0
            if self.fails >= self.max_connect_fails:
                raise SourceDown(f"{type(e).__name__} 연속 {self.fails}회")
            return None

        if len(data) < 200 or data[:15] == b"<!DOCTYPE html>":
            a = Attachment(str(file_no), name, len(data), "",
                           "다운로드 실패(HTML 응답)")
            write_json(PATHS.jd_text / f"{file_no}.json", a.to_dict())
            return a
        cache.write_bytes(data)
        return data

    @staticmethod
    def downloaded_count() -> int:
        return sum(1 for _ in PATHS.jd_files.iterdir())
