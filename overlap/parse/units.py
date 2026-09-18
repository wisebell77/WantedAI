"""직무기술서 파일 하나를 '직무 단위'로 쪼갠다.

공공기관은 한 번 공고에 여러 분야를 뽑으면서 직무설명자료를 한 파일에 이어 붙인다.
파일을 통째로 한 덩어리로 보면 '전산' 역량과 '환경미화' 역량이 섞인다.
실제로 정보통신 상위 역량에 회계프로그램·재무제표가 올라왔었다.

직무기술서는 분야마다 NCS 분류체계 표를 하나씩 갖는다. 그 표를 앵커로 잡으면
분야 경계가 그대로 나온다.

    [제목/채용분야] ■ NCS 분류체계 → 대분류/중분류/소분류/세분류
    ■ 직무수행 내용 / 능력단위 / 필요지식 / 필요기술 / 태도 ...
    [다음 분야 제목] ■ NCS 분류체계 ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .sections import SectionParser

# 분류체계 표의 시작. '분류체계' 표제 또는 대분류→중분류가 잇달아 나오는 자리.
ANCHOR = re.compile(r"(?:NCS\s*)?분\s?류\s?체\s?계"
                    r"|대\s?분\s?류(?=[\s\S]{0,40}?중\s?분\s?류)")
# 분류체계 표가 끝나는 자리 = 다음 섹션 표제
TABLE_END = re.compile(
    r"직\s?무\s?수\s?행|능\s?력\s?단\s?위|필\s?요\s?지\s?식|주\s?요\s?업\s?무"
    r"|직\s?무\s?필\s?요|담\s?당\s?업\s?무|직\s?무\s?내\s?용")
TITLE_NOISE = re.compile(r"^[\s■□○●▪◆※\-=_.]*$|^\d{4}-\d+호$|^(대|중|소|세)분류$")

# 조건 구간의 표제. 값은 표제 뒤 몇 줄 안에 있다.
QUAL_FIELDS = {
    "학력": r"학\s?력|교육\s?요건|학위",
    "전공": r"전\s?공",
    "경력": r"경\s?력",
    "자격": r"관련\s?자격|자격\s?증|필수\s?자격|우대\s?자격|자격\s?요건",
    "우대": r"우대\s?사항|우대\s?조건|우대\s?요건",
}
QUAL_STOP = re.compile(r"직무\s?수행|능력\s?단위|필요\s?지식|필요\s?기술|직무\s?필요"
                       r"|직업\s?기초|참고\s?사이트|분류\s?체계")


@dataclass
class JobUnit:
    """직무기술서 한 건 = 직무 하나.

    quals 는 이 직무만의 조건이다. 공고 단위 API 필드(recrutSeNm 등)를 쓰면
    안 되는 이유가 여기 있다 — 단위의 86% 가 여러 직무를 묶은 공고에서 나오고,
    그 공고의 학력 조건은 하나뿐이라 전산(대졸)과 청소원(학력무관)을 구분 못 한다.
    """

    file_no: str
    unit: int
    title: str
    text: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    quals: dict[str, str] = field(default_factory=dict)
    ncs_code: str | None = None
    ncs_path: dict[str, str] = field(default_factory=dict)
    institution: str = ""
    year: int | None = None

    # ── 저장 형식
    #
    # 필드 이름을 JSON 쪽에서 바꾸지 않는다. 기존 data/jd_units.json 을
    # 그대로 읽을 수 있어야 재수집 없이 갈아탈 수 있다.

    def to_dict(self) -> dict:
        return {"fileNo": self.file_no, "unit": self.unit, "title": self.title,
                "text": self.text, "sections": self.sections, "quals": self.quals,
                "ncs_code": self.ncs_code, "ncs_path": self.ncs_path,
                "inst": self.institution, "year": self.year}

    @classmethod
    def from_dict(cls, d: dict) -> "JobUnit":
        return cls(
            file_no=str(d.get("fileNo", "")), unit=int(d.get("unit", 0) or 0),
            title=d.get("title", ""), text=d.get("text", ""),
            sections=d.get("sections") or {}, quals=d.get("quals") or {},
            ncs_code=d.get("ncs_code"), ncs_path=d.get("ncs_path") or {},
            institution=d.get("inst", "") or d.get("institution", ""),
            year=d.get("year"))

    @property
    def competencies(self) -> list[str]:
        """역량 섹션을 평평하게. 어느 섹션을 쓸지는 config.SETTINGS 가 정한다."""
        out = []
        for k in ("필요지식", "필요기술", "직무수행태도"):
            out += self.sections.get(k, [])
        return out


class UnitSplitter:
    """문서 텍스트 → JobUnit 목록.

    >>> units = UnitSplitter().split(text, file_no="2917829")
    >>> units[0].title
    '전산(시스템/정보보안)'
    """

    def __init__(self, parser: SectionParser | None = None):
        self.parser = parser or SectionParser()

    def split(self, text: str, file_no: str = "", **meta) -> list[JobUnit]:
        out = []
        for i, block in enumerate(self.blocks(text)):
            body = block["text"]
            if len(body) < 200:
                continue
            sections = self.parser.parse(body)
            if not any(sections.get(k) for k in
                       ("필요지식", "필요기술", "직무수행태도")):
                continue
            out.append(JobUnit(
                file_no=file_no, unit=i, title=block["title"], text=body,
                sections=sections, quals=self.qualifications(body), **meta))
        return out

    # ── 블록 분할

    def blocks(self, text: str) -> list[dict]:
        anchors = [m.start() for m in ANCHOR.finditer(text or "")]
        # 같은 표를 두 번 잡는 경우(분류체계 표제 + 대분류 줄)를 합친다
        merged = [a for i, a in enumerate(anchors)
                  if i == 0 or a - anchors[i - 1] > 80]
        if not merged:
            return [{"title": "", "text": text or ""}]
        out = []
        for i, a in enumerate(merged):
            prev_end = merged[i - 1] if i else 0
            head = max(prev_end, a - 300)
            start = head if i else 0
            end = (max(merged[i + 1] - 300, a + 1)
                   if i + 1 < len(merged) else len(text))
            out.append({"title": self._title(text[head:a]),
                        "text": text[start:end]})
        return out

    @staticmethod
    def _title(before: str) -> str:
        lines = [l.strip(" ■□○●▪◆-–—") for l in before.split("\n")]
        for l in reversed(lines[-8:]):
            if not l or TITLE_NOISE.match(l) or len(l) > 60:
                continue
            if re.fullmatch(r"채\s?용\s?분\s?야|모\s?집\s?분\s?야|직\s?무\s?명?", l):
                continue
            return l
        return ""

    # ── 분류체계 표 구간 (NcsResolver 가 쓴다)

    @staticmethod
    def taxonomy_region(block_text: str, span: int = 1200) -> str:
        m = ANCHOR.search(block_text)
        if not m:
            return ""
        seg = block_text[m.end():]
        e = TABLE_END.search(seg)
        return seg[:e.start()] if e else seg[:span]

    # ── 조건 추출

    @staticmethod
    def qualifications(text: str, span: int = 160) -> dict[str, str]:
        out = {}
        for key, pat in QUAL_FIELDS.items():
            m = re.search(pat, text)
            if not m:
                out[key] = ""
                continue
            seg = text[m.end():m.end() + span]
            e = QUAL_STOP.search(seg)
            if e:
                seg = seg[:e.start()]
            out[key] = re.sub(r"\s+", " ", seg).strip(" :·-—[]()")[:120]
        return out


def load_units(path=None) -> list[JobUnit]:
    """저장된 직무 단위를 읽는다. 파이프라인과 평가가 공통으로 쓴다."""
    import json
    from pathlib import Path as _P
    from ..config import PATHS
    p = _P(path or PATHS.units)
    if not p.exists():
        return []
    return [JobUnit.from_dict(d)
            for d in json.loads(p.read_text(encoding="utf-8"))]


def save_units(units, path=None) -> int:
    import json
    from pathlib import Path as _P
    from ..config import PATHS
    p = _P(path or PATHS.units)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([u.to_dict() for u in units],
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return len(units)
