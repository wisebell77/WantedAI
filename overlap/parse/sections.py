"""직무기술서 본문에서 역량 섹션을 잘라낸다.

직무기술서는 공공기관 공통 양식이라 섹션 이름이 거의 고정되어 있다.
    NCS 분류체계 · 직무수행내용 · 능력단위
    필요지식 · 필요기술 · 직무수행태도 · 직업기초능력 · 관련자격

여기서는 그 섹션만 옮긴다. 문장을 지어내지 않는다.

다루기 까다로운 지점 세 가지 — 모두 실제로 데이터를 망가뜨렸던 것들이다.

    표제가 표 셀 단위로 줄바꿈된다
        '기술원 / 주요 / 사업' → 최대 3줄까지 이어 붙여서 표제를 찾는다.

    짧은 표제가 과하게 일치한다
        '기술원' 이 '기술' 표제로 잡혀 그 아래 기관 소개가 통째로 필요기술이 됐다.
        길이 2자 표제(지식/기술/태도)는 완전히 일치할 때만 인정한다.

    경계 전용 표제가 길다
        '■ 교육요건(학력, 전공)/관련자격/경력 등 우대사항' 이 25자여서
        예전 상한 24자에 걸려 표제로 인식되지 않았고, 조건 문구가 역량에 섞였다.
"""

from __future__ import annotations

import re
from collections import defaultdict

# 수집할 섹션과 그 표제들
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("필요지식", ("필요지식", "직무필요지식", "지식")),
    ("필요기술", ("필요기술", "직무필요기술", "기술")),
    ("직무수행태도", ("직무수행태도", "필요태도", "태도")),
    ("능력단위", ("능력단위", "주요능력단위")),
    ("직무수행내용", ("직무수행내용", "주요업무", "담당업무", "직무내용",
                 "채용분야주요업무")),
    ("직업기초능력", ("직업기초능력",)),
    ("관련자격", ("관련자격", "우대자격", "필요자격", "자격증")),
)

# 역량이 아니지만 표제인 것들. 수집하지 않고 경계로만 쓴다.
# 이걸 경계로 잡지 않으면 기관 소개·우대사항 문장이 앞 역량 섹션에 흡수된다.
STOP_HEADS: tuple[str, ...] = (
    "기관주요사업", "주요사업", "기관소개", "사업개요", "공단사업",
    "우대사항", "우대조건", "교육요건", "일반요건", "필요자격", "관련자격",
    "전형방법", "근무지", "근무부서", "채용분야", "모집분야", "직급", "직군",
    "참고사이트", "참고", "비고", "기타", "직업기초능력", "직무수행요건",
    "요구수준", "요구역량", "분류체계", "NCS분류체계", "대분류", "중분류",
    "지원요건", "응시자격", "지원자격", "자격요건", "연령", "성별", "학력",
    "전공", "경력", "채용인원", "소속", "직위", "직렬", "고용형태",
)

BULLET = "·•◦○●ㅇ□■▪▫◇◆⚬∘⦁‣▶▷►★☆❍¡-"
ITEM_SPLIT = re.compile(
    r"[\n" + re.escape(BULLET) + r"]\s*|(?<=[다음])\s*,\s*|,\s+(?=[가-힣A-Za-z(])")

# 표 칸 안에서 구(句) 중간에 줄바꿈이 들어간다.
#   "정보시스템에\n대한 지식" → "정보시스템에" 와 "대한 지식" 으로 쪼개진다.
# 실제로 `대한 지식`(87회), `분석 능력`(94회) 같은 조각이 독립 역량처럼 집계됐다.
WRAP_TAIL = re.compile(r"(?:[에의을를과와및]|[,·])\s*$")
WRAP_HEAD = re.compile(r"^\s*(?:대한|관한|대해|관해|및|등|있는|없는|위한|통한)\b")
BULLET_HEAD = re.compile(r"^\s*[" + re.escape(BULLET) + r"]")
LEAD_MARK = re.compile(r"^[\s■□○●▪▫◆◇※◎ㅇ·•\-–—]+")

TABLE_HEAD = frozenset({
    "대분류", "중분류", "소분류", "세분류", "분류체계", "채용분야", "직무", "직급",
    "근무지", "근무부서", "전형방법", "일반요건", "교육요건", "연령", "성별", "학력",
    "전공", "경력", "주요사업", "기관", "참고사이트", "우대사항", "관련자격",
    "직무수행", "직무수행내용", "능력단위", "직업기초능력", "필요지식", "필요기술",
    "직무수행태도", "필요태도", "기관주요사업", "채용인원", "비고",
})
# 직업기초능력 10종은 별도 섹션이다. 필요지식/기술에 섞이면 모든 직무에서
# 똑같이 상위를 차지해 변별력을 없앤다.
BASIC_ABILITY = frozenset({
    "의사소통능력", "수리능력", "문제해결능력", "자기개발능력", "자원관리능력",
    "대인관계능력", "정보능력", "기술능력", "조직이해능력", "직업윤리",
})
FRAGMENT = frozenset({"직업기초", "기초능력", "수행태도", "필요지식", "필요기술",
                      "직무수행", "분류", "체계", "요건", "사항", "내용", "단위", "능력"})
DROP = re.compile(
    r"^(www\.|http|참고|사이트|ncs|\d+\.?$|\d{2}\.\s|기타|해당없음|없음|미개발|자체개발)",
    re.I)
NCS_CODE = re.compile(r"^\s*\d{2}[.\s]")
BOILER = re.compile(
    r"국가직무능력표준|홈페이지|www\.|http|별첨|자체 ?개발|붙임|세부 ?사항입니다"
    r"|본 ?내용은|상기 ?직무|직무 ?설명자료|직무기술서|채용 ?공고|별도로")
GUIDE = re.compile(r"바랍니다|하시기|될 수 있|참고하|해당 없|제한 ?없|양지")


def compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


class SectionParser:
    """직무기술서 텍스트 → {섹션명: [역량 항목, ...]}

    >>> SectionParser().parse(text)["필요기술"][:2]
    ['서버 보안 소프트웨어 설치 및 운영 기술', '프로그램 코드 검토 능력']
    """

    def parse(self, text: str) -> dict[str, list[str]]:
        return {k: self.items(v) for k, v in self.split(text).items()}

    # ── 섹션 분할

    def split(self, text: str) -> dict[str, str]:
        flat = re.sub(r"[ \t]+", " ", text or "")
        lines = [l.strip() for l in flat.splitlines()]
        idx: list[tuple[int, str | None, int]] = []
        i = 0
        while i < len(lines):
            hit = None
            for span in (3, 2, 1):
                part = lines[i:i + span]
                if len(part) < span:
                    continue
                if span > 1 and any((not x) or len(x) > 8 for x in part):
                    continue
                c = LEAD_MARK.sub("", compact("".join(part)))
                if not c or len(c) > 60:
                    continue
                m = self._match_head(c)
                # 긴 줄은 경계 전용 표제만 인정한다. 역량 섹션 표제가 길 리 없고,
                # 길게 허용하면 본문 문장이 표제로 오인된다.
                if m and len(c) > 24 and m[0] is not None:
                    m = None
                if m:
                    hit = (m[0], span)
                    break
            if hit:
                idx.append((i, hit[0], hit[1]))
                i += hit[1]
            else:
                i += 1

        out: dict[str, list[str]] = defaultdict(list)
        for k, (i, canon, span) in enumerate(idx):
            if canon is None:
                continue                              # 경계 전용 표제. 내용은 버린다.
            end = idx[k + 1][0] if k + 1 < len(idx) else min(len(lines), i + 40)
            body = "\n".join(lines[i + span:end]).strip()
            if body:
                out[canon].append(body)
        return {k: "\n".join(v) for k, v in out.items()}

    @staticmethod
    def _match_head(c: str) -> tuple[str | None, int] | None:
        """표제면 (섹션명 또는 None, 일치길이). 아니면 None.

        짧은 표제(지식/기술/태도)는 반드시 완전히 일치해야 한다.
        startswith 로 허용하면 '기술원'이 '기술' 표제로 잡혀서
        그 아래 기관 소개가 통째로 필요기술 항목이 된다.
        """
        best = None
        for canon, heads in [(None, STOP_HEADS)] + [(k, hs) for k, hs in SECTIONS]:
            for h in heads:
                hc = compact(h)
                if c == hc or (len(hc) >= 3 and c.startswith(hc)):
                    if best is None or len(hc) > best[1]:
                        best = (canon, len(hc))
        return best

    # ── 항목 분리

    def items(self, block: str) -> list[str]:
        out = []
        for raw in ITEM_SPLIT.split(self.join_wrapped(block)):
            s = re.sub(r"\s+", " ", (raw or "")).strip(" .–—()[]" + BULLET)
            if not s or len(s) < 3 or len(s) > 80:
                continue
            if DROP.match(s) or self.is_noise(s):
                continue
            out.append(s)
        return out

    @staticmethod
    def join_wrapped(block: str) -> str:
        lines = (block or "").split("\n")
        out: list[str] = []
        for l in lines:
            if out and not BULLET_HEAD.match(l) and (
                    WRAP_TAIL.search(out[-1]) or WRAP_HEAD.match(l)):
                out[-1] = out[-1].rstrip() + " " + l.strip()
            else:
                out.append(l)
        return "\n".join(out)

    @staticmethod
    def is_noise(s: str) -> bool:
        # 표에서 빈 칸이 쉼표만 남기고 떨어져 나온다(",,"). 역량이 아니다.
        if not re.search(r"[가-힣A-Za-z]", s):
            return True
        if len(re.sub(r"[^가-힣A-Za-z]", "", s)) < 2:
            return True
        c = re.sub(r"[\s.·0-9]", "", s)
        if (not c) or c in TABLE_HEAD or c in BASIC_ABILITY or c in FRAGMENT:
            return True
        if NCS_CODE.match(s) or GUIDE.search(s) or BOILER.search(s):
            return True
        # 한 단어짜리 명사는 역량 서술로 보기 어렵다("바이오", "재무제표")
        if len(c) <= 4 and " " not in s.strip():
            return True
        return False
