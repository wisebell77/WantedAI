"""Upstage(Solar) 호출 래퍼. 승민 님 코치 서버와 같은 엔드포인트·환경변수를 쓴다.

키가 없거나 호출이 실패하면 None 을 돌려주고, 각 모듈은 규칙 기반으로 대체한다.
외부 패키지 없이 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from .data import ROOT

UPSTAGE_URL = "https://api.upstage.ai/v1/chat/completions"


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
    return bool(os.getenv("UPSTAGE_API_KEY"))


def chat_json(system: str, user: str | dict, *, fast: bool = False,
              temperature: float = 0.2, timeout: int = 60) -> dict | None:
    if not available():
        return None
    model = (os.getenv("UPSTAGE_FAST_MODEL", "solar-mini") if fast
             else os.getenv("UPSTAGE_COACH_MODEL", "solar-pro4"))
    body = {
        "model": model, "stream": False, "temperature": temperature,
        "messages": [
            {"role": "system", "content": system + " 반드시 JSON 하나만 반환한다."},
            {"role": "user", "content": user if isinstance(user, str)
             else json.dumps(user, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        UPSTAGE_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {os.environ['UPSTAGE_API_KEY']}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = json.load(resp)["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
        return json.loads(content)
    except Exception as e:  # 네트워크·파싱 실패 → 규칙 기반으로 대체
        print(f"[persona.llm] LLM 호출 실패, 규칙 기반으로 대체: {e}")
        return None
