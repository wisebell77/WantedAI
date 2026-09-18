"""민간 공고에서 **주요업무 서술문**을 뽑는다.

요건 문장(`RequirementExtractor`)과 무엇이 다른가.

    요건   "빅데이터 플랫폼 설치 및 운용 능력"      명사구. 자격을 나열한다
    업무   "앨범 마케팅 플래닝 및 운영"             서술. 무슨 일을 하는지 적는다

둘 다 같은 공고 안에 있는데 지금까지 요건 문장만 썼다. 그게 문제였다.

우리 역량 축은 공공 직무기술서의 역량 항목(`빅데이터 분석 결과 시각화`)으로
만들었다. 요건 문장과 **같은 꼴**이라 유사도가 높게 나온다. 그 문장으로
임계를 고르면 실제 사용자 문장에는 너무 빡빡해진다.

실측한 최고 유사도 분포

    요건 문장        평균 0.665   0.55 초과 94%
    주요업무 서술문   평균 0.583   0.55 초과 68%     <- 여기
    실제 사용자 문장  평균 0.540   0.55 초과 50%

주요업무 서술문이 딱 중간이다. **진짜 사람이 쓴 문장**이고, 정답 라벨(그 공고의
직무 분류)이 그대로 붙어 있으며, 추가 수집이 필요 없다. 평가 질의로 쓰기 좋다.

거르기가 관건이다. 공고 본문에는 급여·복지·접수 안내가 섞여 있고,
`신입 : 기본 연봉 3,500만원` 같은 줄이 유사도 0.671 로 잡히기도 했다.
"""

from __future__ import annotations

import re

# 일하는 모습을 적은 문장의 종결. 명사구로 끝나는 요건 문장과 이걸로 갈린다.
DUTY_TAIL = re.compile(
    r"(?:합니다|습니다|해요|한다|됩니다"
    r"|수행|담당|진행|운영|관리|구축|개발|설계|분석|기획|지원|대응|개선"
    r"|작성|검토|점검|제작|실시|추진)\s*$")

# 업무가 아닌 줄. 요건 문장 쪽 잡음어와 겹치지만 여기서 걸러야 할 것이 더 많다 —
# 급여·복지·근무조건은 서술체로 적히는 경우가 잦아 종결어미만으로는 안 걸러진다.
NOT_DUTY = re.compile(
    r"연봉|급여|월급|상여|인센티브|복리|복지|퇴직|보험|수당|휴가|연차"
    r"|접수|지원서|제출|전형|면접|합격|마감|채용\s?절차|우대\s?사항"
    r"|근무\s?시간|근무\s?지|근무\s?형태|주\s?\d일|출퇴근"
    r"|만원|억원|\d{4}\s?년\s?\d{1,2}\s?월\s?\d{1,2}|문의|담당자|이메일"
    r"|학력|전공|자격증|어학|토익|경력\s?\d+\s?년\s?이상"
    # 안내 문구는 서술체로 끝나서 종결어미만으로는 안 걸린다.
    # `적격자가 없을 경우, 채용하지 않을 수 있습니다` 가 유사도 0.483 으로 잡혔다.
    r"|적격자|해당자|대상자|다음과\s?같|아래와\s?같|바랍니다|유의|안내"
    r"|불이익|취소|허위|결격|제한될|경우에는|할\s?수\s?있습니다"
    r"|모집\s?분야|모집\s?인원|채용\s?인원|입사|입문|수습")

SPLIT = re.compile(r"[\n·•○●▪□■]\s*|(?<=[가-힣])\s*/\s*")


class DutyExtractor:
    """공고 본문 → 주요업무 서술문.

    >>> dx = DutyExtractor()
    >>> dx.sentences("· 앨범 마케팅 플래닝 및 운영 · 신입 : 기본 연봉 3,500만원")
    ['앨범 마케팅 플래닝 및 운영']
    """

    def __init__(self, min_length: int = 12, max_length: int = 60):
        self.min_length, self.max_length = min_length, max_length

    def __call__(self, text: str):
        return self.extract(text)

    def extract(self, text: str):
        seen = set()
        for raw in SPLIT.split(text or ""):
            s = re.sub(r"\s+", " ", raw).strip(" .,·•-–—()[]")
            if not (self.min_length <= len(s) <= self.max_length):
                continue
            if not re.search(r"[가-힣]", s):
                continue
            if NOT_DUTY.search(s) or not DUTY_TAIL.search(s):
                continue
            key = re.sub(r"\s+", "", s)
            if key in seen:                           # 같은 공고 안 중복이 잦다
                continue
            seen.add(key)
            yield s

    def sentences(self, text: str) -> list[str]:
        return list(self.extract(text))
