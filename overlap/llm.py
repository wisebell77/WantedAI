"""LLM — **입력을 다듬는 데만** 쓴다. 추천에는 관여하지 않는다.

이 선은 타협하지 않는다. CLAUDE.md 가 정한 것이다.

    "SQL이 부족하니 인강을 들으세요" 같은 일반적 학습 조언은 LLM 이 지어내는
    것이므로 넣지 않는다.

그리고 실용적인 이유가 하나 더 있다. 추천이 LLM 을 타면 같은 입력에 매번 다른
결과가 나와 어제와 오늘 점수가 달라지고, 성능 비교 자체가 불가능해진다.
군집·투영·대조는 전부 결정적이어야 한다.

그래서 여기서 하는 일은 하나뿐이다.

    사용자가 쓴 긴 글 → 경험 단위 문장들로 쪼개기

    사용자는 "저는 학회에서 운영진을 했고 거기서 8명 일정을 조율했는데
    그러면서 설문도 300건 정리해봤어요" 처럼 한 덩어리로 쓴다.
    문단째 임베딩하면 뭉개져서 유사도가 전부 0.3 대로 눌린다.

    규칙 기반 분리(Recommender.sentences)로도 되지만 구어체에서 잘 안 끊긴다.
    LLM 은 그걸 더 잘한다. **없으면 규칙으로 돌아간다 — 서비스는 안 죽는다.**

쪼갠 문장은 **사용자가 쓴 말 그대로**여야 한다. 요약하거나 바꿔 쓰면
그게 화면에 근거로 올라가는데, 사용자가 안 한 말이 근거가 되어 버린다.
프롬프트가 그 점을 못박고, 결과도 원문에 실제로 들어있는지 검사한다.
"""

from __future__ import annotations

import json
import re

from .config import api_key

UPSTAGE_URL = "https://api.upstage.ai/v1/chat/completions"
MODEL = "solar-pro2"

PROMPT = """너는 취업 준비생이 쓴 경험 서술을 **경험 단위로 쪼개는** 일만 한다.

규칙
- 원문에 있는 표현을 그대로 쓴다. 요약·의역·추가·미화를 하지 않는다.
- 한 문장에 한 가지 경험만 담는다.
- 경험이 아닌 문장(인사말, 각오, 지원 동기)은 버린다.
- 6자 미만이면 버린다.
- JSON 배열로만 답한다. 설명을 붙이지 않는다.

예시
입력: 저는 학회에서 운영진을 했고 거기서 8명 일정을 조율했는데 그러면서 설문도 300건 정리해봤어요
출력: ["학회에서 운영진을 했다", "8명 일정을 조율했다", "설문 300건을 정리했다"]"""


class UpstageClient:
    """Upstage Solar. 키가 없으면 조용히 비활성화된다.

    >>> c = UpstageClient()
    >>> c.available
    True
    >>> c.split("저는 학회 운영진을 했고 설문도 300건 정리해봤어요")
    ['학회 운영진을 했다', '설문 300건을 정리했다']
    """

    def __init__(self, key: str | None = None, model: str = MODEL,
                 timeout: int = 20):
        self.key = key if key is not None else api_key("UPSTAGE_API_KEY")
        self.model = model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.key)

    def split(self, text: str) -> list[str]:
        """긴 글 → 경험 문장 목록. 실패하면 빈 목록(호출자가 규칙으로 돌아간다)."""
        if not self.available or not (text or "").strip():
            return []
        try:
            import requests
            r = requests.post(
                UPSTAGE_URL, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "temperature": 0,
                      "messages": [{"role": "system", "content": PROMPT},
                                   {"role": "user", "content": text}]})
            body = r.json()["choices"][0]["message"]["content"]
        except Exception:
            # 무료 티어라 한도·지연으로 자주 실패한다. 실패가 서비스를 멈추면 안 된다.
            return []
        return self.verify(self.parse(body), text)

    @staticmethod
    def parse(body: str) -> list[str]:
        m = re.search(r"\[.*\]", body or "", re.S)
        if not m:
            return []
        try:
            got = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
        return [s.strip() for s in got if isinstance(s, str) and s.strip()]

    @staticmethod
    def verify(sentences: list[str], source: str) -> list[str]:
        """지어낸 문장을 걸러 낸다.

        원문의 어절이 절반 넘게 들어 있어야 통과시킨다. 완전 일치를 요구하면
        조사 정리(`했는데` → `했다`)까지 탈락하므로 어절 기준으로 느슨하게 본다.
        이 검사가 없으면 LLM 이 매끄럽게 지어낸 문장이 화면에 '당신의 경험'으로
        올라간다. 사용자가 안 한 말이 근거가 되는 건 어떤 이유로도 안 된다.
        """
        pool = {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", source or "")}
        out = []
        for s in sentences:
            words = re.findall(r"[가-힣A-Za-z0-9]{2,}", s)
            if len(s) >= 6 and words and \
                    sum(1 for w in words if w in pool) / len(words) >= 0.5:
                out.append(s)
        return out

    def __repr__(self) -> str:
        return f"<UpstageClient {self.model} {'사용 가능' if self.available else '키 없음'}>"
