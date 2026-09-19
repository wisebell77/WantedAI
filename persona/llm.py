"""LLM 호출 래퍼. 코치 서버(server/upstage-career-coach.js)와 같은 환경변수를 쓴다.

키가 없거나 호출이 실패하면 None 을 돌려주고, 각 모듈은 규칙 기반으로 대체한다.
외부 패키지 없이 표준 라이브러리만 쓴다.

**제공자는 환경변수로 고른다.** 요청 본문이 OpenAI 호환 형식(`model`·`messages`·
`temperature`)이라 URL·키·모델명만 바꾸면 Upstage 든 OpenAI 든 그대로 돈다.

    LLM_BASE_URL    기본 https://api.upstage.ai/v1/chat/completions
    LLM_API_KEY     없으면 UPSTAGE_API_KEY 를 쓴다
    LLM_COACH_MODEL 판단이 필요한 곳 (채점표·서류심사·면접채점)
    LLM_FAST_MODEL  가벼운 곳 (면접 질문 생성)

기존 `UPSTAGE_*` 를 폴백으로 남겨 둔다 — 되돌릴 때 변수만 지우면 된다.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request

from .data import ROOT

UPSTAGE_URL = "https://api.upstage.ai/v1/chat/completions"     # 기본값(하위 호환)


def _endpoint() -> str:
    return os.getenv("LLM_BASE_URL") or UPSTAGE_URL


def _api_key() -> str:
    return os.getenv("LLM_API_KEY") or os.getenv("UPSTAGE_API_KEY") or ""


def _model(fast: bool) -> str:
    if fast:
        return (os.getenv("LLM_FAST_MODEL")
                or os.getenv("UPSTAGE_FAST_MODEL") or "solar-mini")
    return (os.getenv("LLM_COACH_MODEL")
            or os.getenv("UPSTAGE_COACH_MODEL") or "solar-pro4")


def _load_dotenv() -> None:
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_dotenv()


def available() -> bool:
    return bool(_api_key())


def chat_json(system: str, user: str | dict, *, fast: bool = False,
              temperature: float = 0.2, timeout: int = 60) -> dict | None:
    if not available():
        return None
    model = _model(fast)
    body = {
        "model": model, "stream": False, "temperature": temperature,
        "messages": [
            {"role": "system", "content": system + " 반드시 JSON 하나만 반환한다."},
            {"role": "user", "content": user if isinstance(user, str)
             else json.dumps(user, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        _endpoint(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {_api_key()}",
                 "Content-Type": "application/json"})
    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
        return json.loads(content)
    except Exception as e:  # 네트워크·파싱 실패 → 규칙 기반으로 대체
        print(f"[persona.llm] LLM 호출 실패, 규칙 기반으로 대체: {e}")
        return None
