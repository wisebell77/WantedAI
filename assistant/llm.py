"""LLM 클라이언트 래퍼.

의도:
- 실제 LLM 호출부를 한 곳에 격리해, 나머지 엔진은 LLM을 몰라도 되게 한다.
- API 키가 없으면 자동으로 None을 반환 → 상위 로직이 휴리스틱 fallback을 쓴다.
  (덕분에 키 없이도 데모가 돌아가고, 개발 중 비용이 0이 된다.)

키를 꽂으려면 환경변수 ANTHROPIC_API_KEY 를 설정하면 된다.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol

_ENV_LOADED = False


def _load_dotenv() -> None:
    """프로젝트 루트의 .env 를 읽어 환경변수로 주입(의존성 없이).

    이미 환경에 있는 값은 덮어쓰지 않는다. .env 는 .gitignore 로 커밋 제외됨.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
    except OSError:
        pass


# 저가/저지연 모델을 기본값으로 → 데모/개발 비용 최소화
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class LLMClient(Protocol):
    """엔진이 기대하는 최소 인터페이스."""

    def complete_json(self, system: str, user: str) -> dict: ...


class AnthropicClient:
    """Anthropic API 기반 클라이언트. `anthropic` 패키지가 필요하다."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        import anthropic  # 지연 import: 패키지 없어도 fallback 경로엔 영향 없음

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete_json(self, system: str, user: str) -> dict:
        """모델에게 JSON만 답하도록 요청하고 파싱해서 반환."""
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        return _extract_json(text)


def get_default_client() -> Optional[LLMClient]:
    """환경에서 쓸 수 있는 클라이언트를 만든다. 없으면 None."""
    _load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    # 실제 Anthropic 키만 인정 (빈 값·placeholder·오타를 걸러 '가짜 LLM 모드'를 막는다)
    if not api_key or not api_key.startswith("sk-ant-"):
        return None
    try:
        return AnthropicClient(api_key)
    except ImportError:
        # anthropic 패키지 미설치 → fallback 사용
        return None


def _extract_json(text: str) -> dict:
    """모델 응답에서 JSON 객체를 최대한 견고하게 뽑아낸다."""
    text = text.strip()
    # 코드펜스 제거
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise
