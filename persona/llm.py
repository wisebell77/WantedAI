"""Upstage(Solar) 호출 래퍼. 승민 님 코치 서버와 같은 엔드포인트·환경변수를 쓴다.

키가 없거나 호출이 실패하면 None 을 돌려주고, 각 모듈은 규칙 기반으로 대체한다.
외부 패키지 없이 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
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
              temperature: float = 0.2, timeout: int | None = None,
              label: str = "", retries: int = 1) -> dict | None:
    """실패하면 retries 번 더 시도하고, 그래도 안 되면 None(→ 규칙 기반).
    UPSTAGE_TIMEOUT(초, 기본 150)으로 대기 시간을 조절한다."""
    if not available():
        return None
    timeout = timeout or int(os.getenv("UPSTAGE_TIMEOUT", "150"))
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
    data = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {os.environ['UPSTAGE_API_KEY']}",
               "Content-Type": "application/json"}
    tag = f"[{label}] " if label else ""
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(UPSTAGE_URL, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = json.load(resp)["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
            return json.loads(content)
        except json.JSONDecodeError as e:  # 형식 오류는 재시도해도 비슷하다
            print(f"[persona.llm] {tag}JSON 형식 오류, 규칙 기반으로 대체: {e}")
            return None
        except (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError) as e:
            code = getattr(e, "code", None)
            if code and code not in (429, 500, 502, 503, 504):
                print(f"[persona.llm] {tag}HTTP {code}, 규칙 기반으로 대체")
                return None
            wait = round(time.time() - t0)
            if attempt < retries:
                print(f"[persona.llm] {tag}{wait}초 후 실패({e}), 다시 시도합니다…")
                time.sleep(2 * (attempt + 1))
            else:
                print(f"[persona.llm] {tag}{wait}초 후 실패({e}), 규칙 기반으로 대체")
        except Exception as e:
            print(f"[persona.llm] {tag}호출 실패, 규칙 기반으로 대체: {e}")
            return None
    return None
