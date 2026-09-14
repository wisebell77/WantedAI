"""수집 공통 — 호출 예산, 중단 조건, HTTP 세션.

이 파일은 전부 '한 번 크게 데어서 생긴 장치'다. 수집은 몇 시간짜리 작업이라
중간에 죽으면 그때까지 받은 것을 잃는다. 실제로 두 번 잃었다.

    QuotaExceeded  공공데이터포털 일일 한도 초과. 조용히 넘기면 '데이터 없음'으로
                   오해한다. 한도 초과는 HTTP 429 + JSON 본문으로 오기 때문에
                   json() 파싱이 성공해 버린다. 반드시 본문을 뜯어 구분한다.

    SourceDown     첨부 파일 서버에 연결 자체가 안 되는 상태.
                   API(apis.data.go.kr)와 파일 서버(www.alio.go.kr)는 별개다.
                   API 는 멀쩡한데 파일 서버만 죽은 적이 있었고, 그때 요청마다
                   TCP 연결 타임아웃 21초를 다 기다리며 분당 3건씩 처리했다.
                   연속 실패가 쌓이면 즉시 멈추고 지금까지 받은 것을 저장한다.

    Budget         이번 실행에서 쓸 최대 호출 수. 한도를 다 태우면 다음 작업을
                   못 하므로 스스로 끊는다.

캐시 읽기에 try/except 가 붙은 것도 사고 대응이다.
중간에 죽으면 0바이트 캐시가 남고, 그걸 읽다 JSONDecodeError 로 수집 전체가
죽으면서 그때까지 받은 500건이 저장되지 않고 사라졌다. 깨진 캐시는 지우고 다시 받는다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


class QuotaExceeded(Exception):
    """일일 호출 한도 초과. 자정에 풀린다."""


class SourceDown(Exception):
    """원본 서버 접속 불가. 복구를 기다렸다 같은 명령을 다시 돌리면 된다."""


class Budget:
    """남은 호출 수. 0 이 되면 수집을 접는다."""

    def __init__(self, total: int):
        self.total = total
        self.left = total

    def spend(self, n: int = 1) -> bool:
        self.left -= n
        return self.left > 0

    @property
    def used(self) -> int:
        return self.total - self.left

    def __bool__(self) -> bool:
        return self.left > 0

    def __repr__(self) -> str:
        return f"<Budget {self.left}/{self.total}>"


def read_json(path: str | Path, default=None):
    """깨진 캐시는 지우고 default 를 돌려준다."""
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        p.unlink(missing_ok=True)
        return default


def write_json(path: str | Path, obj, indent=None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent),
                 encoding="utf-8")


class HttpClient:
    """재시도 붙은 requests 세션. 수집 모듈은 전부 이걸 쓴다."""

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

    def __init__(self, retries: int = 3, timeout: int = 40,
                 delay: float = 0.0):
        import requests
        self.requests = requests
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.UA})
        self.retries, self.timeout, self.delay = retries, timeout, delay

    def get(self, url: str, timeout=None, **params):
        r = self.session.get(url, params=params or None,
                             timeout=timeout or self.timeout)
        if self.delay:
            time.sleep(self.delay)
        return r

    def json(self, url: str, budget: Budget | None = None, **params):
        """JSON 응답. 실패하면 None. 한도 초과면 QuotaExceeded."""
        if budget is not None and not budget:
            return None
        for attempt in range(self.retries):
            try:
                r = self.get(url, **params)
                if budget is not None:
                    budget.spend()
                d = r.json()
                # 에러 봉투면 한도 초과인지 보고, 아니면 '결과 없음'으로 넘긴다
                return None if self.is_error(d) else d
            except QuotaExceeded:
                raise
            except Exception:
                if attempt == self.retries - 1:
                    if budget is not None:
                        budget.spend()
                    return None
                time.sleep(2)

    @staticmethod
    def is_error(d) -> bool:
        """에러 봉투인가. 한도 초과면 여기서 QuotaExceeded 로 올린다."""
        if not (isinstance(d, dict) and "OpenAPI_ServiceResponse" in d):
            return False
        msg = (d["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
               .get("errMsg", ""))
        if "LIMITED_NUMBER_OF_SERVICE" in msg:
            raise QuotaExceeded(msg)
        return True
