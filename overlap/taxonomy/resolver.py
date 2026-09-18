"""직무기술서의 분류체계 표를 읽어 NCS 코드를 확정한다.

두 번 갈아엎은 부분이라 왜 이 방식인지 남겨 둔다.

    1차 — 공고의 ncsCdNmLst 를 그대로 썼다.
          공고 하나가 전산·건축·법무를 함께 뽑으면 코드가 7개 붙는데,
          분야마다 직무기술서 파일이 따로 있다. 파일마다 공고 코드 7개를 붙이면
          '전산 직무기술서'가 건설·영업판매 문서로도 집계된다. 240건이 틀렸다.

    2차 — 표에서 '몇 번째 칸'인지로 읽었다.
          레이아웃이 기관마다 달라 칸이 밀리면 `01.해외관리` 자리에 `양식조리`가
          들어갔다. 공식표와 대조하니 16% 불일치.

    3차 (현재) — 표 구간의 각 칸을 공식 이름 사전에 조회해 코드로 확정한다.
          위치를 안 보므로 레이아웃에 흔들리지 않는다.
          코드가 공식표에 있어야만 통과하므로 오독이 구조적으로 사라진다.

대분류는 반드시 '분류체계 표 구간'에서만 읽는다. 본문 능력단위에도
"01.IT시스템 운영 기획" 같은 두 자리 코드가 나오므로 구간을 제한하지 않으면
다시 오염된다.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .ncs import NcsTaxonomy, normalize

LEAD_CODE = re.compile(r"^\s*(\d{2})\s*[.．·:]?\s*")
HEAD_MAJOR = re.compile(r"^\s*대\s*분\s*류\s*$")
HEAD_OTHER = re.compile(r"^\s*[중소세]\s*분\s*류\s*$")
# 코드와 이름이 붙어 있는 경우. 가장 확실하다.
PAIRED = re.compile(r"(\d{2})\s*[.．·]\s*([가-힣][가-힣A-Za-z·.ㆍ,／/\s]{1,24})")


@dataclass(frozen=True)
class Resolution:
    code: str | None
    level: str | None
    how: str                                          # 어떤 규칙으로 찾았는지


class NcsResolver:
    """분류체계 표 구간 → NCS 코드.

    >>> r = NcsResolver(NcsTaxonomy.load())
    >>> r.resolve(region).code
    '200106'
    """

    def __init__(self, taxonomy: NcsTaxonomy):
        self.tax = taxonomy

    def resolve(self, region: str, major_hint: str = "",
                max_cells: int = 80) -> Resolution:
        if not region:
            return Resolution(None, None, "구간 없음")
        cells = [c.strip() for c in region.splitlines() if c.strip()][:max_cells]

        major = self.tax.major_code(major_hint) if major_hint else ""
        if not major:
            major = self._major_from_cells(cells)

        # 깊은 단계부터. 세분류가 잡히면 코드에서 대/중/소가 자동으로 따라온다.
        for level in ("세분류", "소분류", "중분류"):
            hits: list[str] = []
            for c in cells:
                key = normalize(LEAD_CODE.sub("", c))
                hits += self.tax.lookup(key, level, under=major)
            if hits:
                return Resolution(Counter(hits).most_common(1)[0][0], level, "이름 조회")

        if major:
            return Resolution(major, "대분류", "대분류만")
        return Resolution(None, None, "공식표에서 못 찾음")

    # ── 대분류 찾기

    def _major_from_cells(self, cells: list[str]) -> str:
        # (가) 코드+이름이 붙어 있는 칸
        for c in cells:
            for code, name in PAIRED.findall(c):
                if self.tax.name(code) and normalize(self.tax.name(code)) == \
                        normalize(name):
                    return code
        # (나) 칸 전체가 대분류 이름
        for c in cells:
            code = self.tax.major_code(LEAD_CODE.sub("", c))
            if code:
                return code
        # (다) '대분류' 헤더 뒤 첫 코드 칸
        for i, c in enumerate(cells):
            if not HEAD_MAJOR.match(c):
                continue
            for nxt in cells[i + 1:i + 8]:
                if HEAD_OTHER.match(nxt):
                    break                              # 값 없이 다음 헤더면 헤더행 레이아웃
                m = LEAD_CODE.match(nxt)
                if m and self.tax.name(m.group(1)):
                    return m.group(1)
                break
        # (라) 헤더행이 끝난 뒤 첫 코드 칸
        heads = [i for i, c in enumerate(cells)
                 if HEAD_MAJOR.match(c) or HEAD_OTHER.match(c)]
        if heads:
            for nxt in cells[max(heads) + 1:max(heads) + 4]:
                m = LEAD_CODE.match(nxt)
                if m and self.tax.name(m.group(1)):
                    return m.group(1)
                break
        return ""

    @staticmethod
    def is_self_developed(region: str) -> bool:
        """기관이 NCS 를 안 쓰고 자체 개발한 경우. 분류체계 표의 17% 가 이렇다."""
        return bool(re.search(r"자체\s?개발|NCS\s?미개발|미개발|해당\s?없", region))
