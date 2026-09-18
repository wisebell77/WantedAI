"""민간 공고 본문에서 요건·역량 문장만 골라낸다.

공공 직무기술서는 `■ 필요지식` 밑에 항목이 줄줄이 붙는 정형 문서라
SectionParser 로 자른다. 민간 공고는 그런 구조가 없다.
HTML 을 텍스트로 만들면 접수 안내·약관·저작권·푸터 메뉴가 본문과 섞인다.

그래서 문장 단위로 걸러 낸다. 두 조건을 동시에 본다.

    신호어가 있어야 한다   경험·능력·역량·이해·지식·개발·설계·분석·운영 …
    잡음어가 없어야 한다   접수·전형·마감·약관·개인정보·COPYRIGHT·TOEIC …

이 필터를 넣기 전에는 확장 노드 후보 상위권에 `Rights` `Reserved` `OPIc` 이
올라왔다. 푸터 저작권 문구와 어학 성적 표기를 기술 용어로 읽은 것이다.

길이 상한 90자는 문단 통짜가 한 문장으로 들어오는 것을 막는다.
길이 하한 8자는 `우대` `기타` 같은 조각을 막는다.
"""

from __future__ import annotations

import re

# 줄바꿈·불릿·슬래시로 끊는다. 슬래시는 한글 뒤에서만 — URL 을 쪼개지 않기 위해서다.
SPLIT = re.compile(r"[\n·•○●▪□■]\s*|(?<=[가-힣])\s*/\s*")

SIGNAL = re.compile(r"경험|능력|역량|이해|지식|보유|개발|설계|구현|분석|운영|활용"
                    r"|가능자|숙련|검증|구축|기획|관리")

NOISE = re.compile(
    r"접수|지원서|전형|면접|홈페이지|문의|마감|입사지원|합격|공고|근무지|급여"
    r"|근무형태|근무일시|약관|개인정보 처리|용어사전|EP\.|뉴스|책임연구원|졸업"
    r"|취소|명예|비방|COPYRIGHT|Rights|Reserved|TOEIC|OPIc|Speaking")


class RequirementExtractor:
    """공고 본문 → 요건 문장 목록.

    >>> rx = RequirementExtractor()
    >>> rx.sentences("· Python 기반 파이프라인 개발 경험 · 접수기간 9/1~9/20")
    ['Python 기반 데이터 파이프라인 개발 경험']
    """

    def __init__(self, min_length: int = 8, max_length: int = 90):
        self.min_length = min_length
        self.max_length = max_length

    def __call__(self, text: str):
        return self.extract(text)

    def extract(self, text: str):
        for raw in SPLIT.split(text or ""):
            s = re.sub(r"\s+", " ", raw).strip(" .,·•-–—()[]")
            if not (self.min_length <= len(s) <= self.max_length):
                continue
            if not re.search(r"[가-힣]", s):    # 영문 전용 줄은 대개 메뉴·URL
                continue
            if NOISE.search(s) or not SIGNAL.search(s):
                continue
            yield s

    def sentences(self, text: str) -> list[str]:
        return list(self.extract(text))
