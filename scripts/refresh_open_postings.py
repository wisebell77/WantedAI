"""고용24 공채속보(210L21) 목록을 새로 받아 data/overlap/gongchae_open.json 에 저장한다.

    python scripts/refresh_open_postings.py

.env 에 WORK24_KEY_RECRUIT=... (고용24 '채용정보' 개인회원 키, 직무추천 파트와 같은 이름) 필요.
목록·마감일만 갱신한다. 새 공고의 본문 수집은 팀 파이프라인(recommendation 브랜치
pipelines/refresh_private.py)이 맡고, 그 전까지 새 공고는 '본문 미수집'으로 따로 보여 준다.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import persona.llm  # noqa: E402,F401  (.env 로드)
from persona.data import DATA_DIR  # noqa: E402

URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do"
FIELDS = ("empSeqno", "empWantedTitle", "empBusiNm", "coClcdNm", "empWantedStdt",
          "empWantedEndt", "empWantedTypeNm", "empWantedHomepgDetail", "empWantedMobileUrl")

key = os.getenv("WORK24_KEY_RECRUIT")
if not key:
    sys.exit(".env 에 WORK24_KEY_RECRUIT 가 없습니다.")

rows, page, total = [], 1, None
while page <= 20:
    q = urllib.parse.urlencode({"authKey": key, "callTp": "L", "returnType": "XML",
                                "startPage": page, "display": 100})
    with urllib.request.urlopen(f"{URL}?{q}", timeout=30) as r:
        xml = r.read().decode("utf-8", "replace")
    blocks = re.findall(r"<dhsOpenEmpInfo>(.*?)</dhsOpenEmpInfo>", xml, re.S)
    for b in blocks:
        rows.append({f: (m.group(1).strip() if (m := re.search(rf"<{f}>(.*?)</{f}>", b, re.S)) else "")
                     for f in FIELDS})
    m = re.search(r"<total>(\d+)</total>", xml)
    total = int(m.group(1)) if m else total
    if not blocks or (total and len(rows) >= total):
        break
    page += 1

path = os.path.join(DATA_DIR, "gongchae_open.json")
old = set()
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        old = {r["empSeqno"] for r in json.load(f)}
with open(path, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
new = [r for r in rows if r["empSeqno"] not in old]
print(f"받음 {len(rows)}건 (신규 {len(new)}건) → {path}")
