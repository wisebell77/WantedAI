"""채점표(루브릭) + 채용담당자 페르소나 생성.

공고 1건(직무 단위) → {persona, items[]}. 각 항목은 공고 원문 인용(jd_quote)을 반드시 갖는다.
- LLM 경로: Upstage가 항목을 뽑고, grounding.verify_quote 로 인용을 검증해 가짜 근거를 버린다.
- 규칙 경로: 키가 없거나 LLM 결과가 부실하면 머리글·글머리표 구조로 뽑는다.
가중치는 항목 종류(필수/업무/우대) × 같은 직무군 공고의 기술 요구 빈도로 준다.
"""
from __future__ import annotations

import re

from . import llm
from .data import RoleDoc, job_market
from .grounding import verify_quote

KIND_WEIGHT = {"required": 1.0, "duty": 0.8, "preferred": 0.6}
MAX_ITEMS = 6

_BULLET = re.compile(r"^\s*(?:[-•·ㆍ*○●▶▪■□◦]|\d+[.)])\s*")
_INLINE = re.compile(r"^\s*(주요\s*업무|담당\s*업무|필요\s*역량|자격\s*요건|지원\s*자격|우대\s*사항|우대)\s*[:：]\s*(.+)")
_SKIP = re.compile(r"(병역|결격|해외여행|쿠키|채용\s*절차|전형|접수|마감|근무지|연봉|복리|학사\s*이상|학력|졸업|채용\s*시\s*까지|장애인|보훈|취업지원|유의|문의|합격|내규|미충족|제출|허위|어학성적|기간|지원하|해당 시|입사|영업비밀|개인정보|^전공)")
_STOP = {"및", "등", "관련", "경험", "이해", "능력", "역량", "보유", "우대", "가능", "업무",
         "있는", "분", "자", "이상", "대한", "위한", "활용", "기반", "통한"}


def _split_top(text: str) -> list[str]:
    """괄호 밖의 쉼표·슬래시(공백 포함)에서만 나눈다. 'C/C++ (C, C++)' 같은 표기를 보존."""
    parts, buf, depth = [], "", 0
    for i, ch in enumerate(text):
        depth += ch in "([" and 1 or 0
        depth -= ch in ")]" and 1 or 0
        sep = ch in ",，" or (ch == "/" and text[i - 1:i] == " " and text[i + 1:i + 2] == " ")
        if sep and depth <= 0:
            parts.append(buf.strip()); buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return [p for p in parts if p]


def _kind(header: str) -> str | None:
    h = header.replace(" ", "")
    if "우대" in h:
        return "preferred"
    if re.search(r"(자격|필수|요건|역량|조건|스킬)", h):
        return "required"
    if re.search(r"(업무|하는일|담당|주요)", h):
        return "duty"
    return None


def _keywords(text: str, techs: list[str]) -> list[str]:
    low = text.lower()
    kws = [t for t in techs if t.lower() in low]
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}|[가-힣]{2,}", text):
        tok = re.sub(r"(을|를|이|가|은|는|의|에|로|으로|과|와)$", "", tok)
        if len(tok) >= 2 and tok not in _STOP and tok not in kws:
            kws.append(tok)
    return kws[:4]


def _heuristic_items(doc: RoleDoc) -> list[dict]:
    items, kind = [], "duty"
    for raw in doc.text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _INLINE.match(line)
        if m:
            k = _kind(m.group(1)) or "duty"
            parts = _split_top(m.group(2))
            items += [(k, p) for p in parts]
            continue
        body = _BULLET.sub("", line)
        if len(line) <= 16 and _kind(line):  # 머리글
            kind = _kind(line)
            inline = re.sub(r"^\[[^\]]*\]\s*", "", line)
            if inline != line and len(inline) >= 4:
                items.append((kind, inline))
            continue
        if _BULLET.match(line):
            items += [(kind, p) for p in _split_top(body)]

    seen, out = set(), []
    for k, text in items:
        text = text.strip(" -·")
        if not (4 <= len(text) <= 70) or _SKIP.search(text) or text in seen:
            continue
        seen.add(text)
        out.append({"kind": k, "label": text[:40], "jd_quote": text})
    # 기술이 들어간 필수 > 필수 > 업무 > 우대 순으로 자른다
    rank = {"required": 0, "duty": 1, "preferred": 2}
    out.sort(key=lambda it: (rank[it["kind"]],
                             -sum(t.lower() in it["jd_quote"].lower() for t in doc.techs)))
    return out[:MAX_ITEMS]


def _followup(item: dict) -> str:
    if item["kind"] == "preferred":
        return f"'{item['label']}'와 관련해 직접 해 본 것이 있다면, 어떤 상황에서 무엇을 했는지 말씀해 주세요."
    if item["kind"] == "duty":
        return f"입사하면 '{item['label']}' 업무를 맡게 됩니다. 비슷한 일을 해 본 경험과 그때 본인의 역할을 말씀해 주세요."
    return f"'{item['label']}'을(를) 실제로 써 본 경험을 말씀해 주세요. 본인이 맡은 부분과 결과는 무엇이었나요?"


_SYSTEM = (
    "너는 채용공고를 읽고 서류·면접 채점표를 만드는 채용 전문가다. "
    "공고에 적힌 내용만 쓴다. 공고에 없는 요구사항을 만들지 않는다. "
    "학력·병역·어학점수·법정 가점처럼 역량이 아닌 요건은 제외한다. "
    "형식: {\"items\":[{\"kind\":\"required|duty|preferred\",\"label\":\"20자 이내 항목명\","
    "\"jd_quote\":\"공고 원문에서 그대로 복사한 구절(수정 금지)\",\"keywords\":[\"답변에서 찾을 단어 2~4개\"],"
    "\"followup\":\"이 항목이 답변에서 약할 때 던질 꼬리질문 1개\"}]} 항목은 4~6개."
)


def _llm_items(doc: RoleDoc) -> list[dict]:
    res = llm.chat_json(_SYSTEM, {"company": doc.corp, "role": doc.role, "job": doc.job,
                                  "techs": doc.techs, "posting_text": doc.text})
    good = []
    for it in (res or {}).get("items", []):
        if it.get("kind") not in KIND_WEIGHT or not verify_quote(it.get("jd_quote", ""), doc.text):
            continue  # 원문에 없는 인용 = 폐기
        good.append(it)
    return good[:MAX_ITEMS]


def build_rubric(doc: RoleDoc, use_llm: bool = True) -> dict:
    items, source = ([], "heuristic")
    if use_llm and llm.available():
        items = _llm_items(doc)
        source = "llm" if len(items) >= 3 else "heuristic"
    if source == "heuristic":
        items = _heuristic_items(doc)

    market = job_market(doc.job)
    total = 0.0
    for i, it in enumerate(items, 1):
        it["id"] = f"r{i}"
        it["keywords"] = it.get("keywords") or _keywords(it["jd_quote"], doc.techs)
        it["followup"] = it.get("followup") or _followup(it)
        # 같은 직무군 공고 중 이 항목의 기술을 요구한 비율(가장 높은 것)
        hits = [(market["tech"].get(k.lower(), 0), k) for k in it["keywords"]]
        k_cnt, tech = max(hits) if hits else (0, "")
        it["market"] = ({"tech": tech, "k": k_cnt, "n": market["n"], "job": doc.job}
                        if k_cnt else None)
        share = k_cnt / market["n"] if market["n"] else 0
        it["weight"] = round(KIND_WEIGHT[it["kind"]] * (1 + share), 3)
        total += it["weight"]
    for it in items:
        it["weight"] = round(it["weight"] / total, 3) if total else 0

    focus = [it["label"] for it in sorted(items, key=lambda x: -x["weight"])[:3]]
    persona = {
        "name": f"{doc.corp} {doc.job} 채용담당자",
        "focus": focus,
        "system_prompt": (
            f"당신은 {doc.corp}의 '{doc.role}' 채용담당자다. 공고와 채점표에 적힌 기준으로만 판단한다. "
            f"특히 {', '.join(focus)}을(를) 본다. 지원자에게 없는 경험을 가정하지 않고, "
            "합격 가능성·성격·외모 등은 평가하지 않는다. 정중하지만 구체적으로 묻는다."),
    }
    return {"rubric_id": doc.role_id, "version": 1, "generated_by": source,
            "posting": doc.to_dict(), "persona": persona, "items": items}


def to_interview_rubric(rubric: dict) -> list[dict]:
    """승민 님 화상면접(dist/app.js)의 rubric 형식으로 변환.
    JSON에는 정규식을 담을 수 없어 keywords 배열로 넘긴다 → JS에서
    checks: item.keywords.map(k => new RegExp(k, 'i')) 로 바꿔 쓰면 된다."""
    return [{"label": it["label"], "keywords": it["keywords"], "followup": it["followup"],
             "jd_quote": it["jd_quote"]} for it in rubric["items"]]
