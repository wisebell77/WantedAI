"""근거 검증 — LLM이 낸 인용문이 원문에 실제로 있는지 코드로 확인한다.

'근거는 반드시 원문에서'라는 제약을 프롬프트에만 맡기지 않기 위한 장치.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?。])\s+|\n+")


def norm(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip()


def verify_quote(quote: str, source: str, min_len: int = 4) -> bool:
    q = norm(quote).strip("\"'“”‘’ ")
    return len(q) >= min_len and q in norm(source)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if len(s.strip()) >= 5]


def find_sentence(text: str, keywords: list[str]) -> str:
    """keywords 중 하나라도 포함한 첫 문장(대소문자 무시)."""
    kws = [k.lower() for k in keywords if k]
    for s in sentences(text):
        low = s.lower()
        if any(k in low for k in kws):
            return s[:160]
    return ""
