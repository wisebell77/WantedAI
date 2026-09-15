"""L1 — 역량 문자열의 표기 정규화.

같은 역량이 문서마다 다르게 적힌다. 그중 '의미가 아니라 표기만 다른 것'을
기계적으로 합친다. 여기까지는 AI 가 필요 없다.

    컴퓨터 활용 능력 / 컴퓨터활용능력            → 컴퓨터활용
    문서작성 기술 / 문서 작성 능력 / 문서작성능력  → 문서작성
    회계에 관한 지식 / 회계 관련 지식 등          → 회계

여기서 안 합쳐지는 것이 L2(의미 군집)의 몫이다.

    서버 보안 소프트웨어 설치 및 운영 기술
    정보보안 시스템 운영 능력
    → 표기만으로는 남남이다. 의미를 봐야 같아진다.

L1 이 얼마나 합치는지를 먼저 재야 L2 의 기여분을 분리할 수 있다.
실측: L1 만으로는 어휘가 3% 밖에 안 줄고 분류 간 겹침도 2.5% → 3.0% 에 그친다.
표기 흔들림은 이 데이터의 주된 문제가 아니다.

합치는 일 말고 **고치는 일**도 여기서 한다. HWP 표에서 뽑은 텍스트는
괄호가 자주 깨져 들어오는데, 그대로 두면 깨진 문자열이 역량 이름이 되어
화면까지 나간다. 실제로 `UI((UserInterface)구현`, `SW프로세스조정(tailoring`,
`협조성(인식과배려` 가 그렇게 나갔다. 어휘 55,237종 중 2,539종(7,441건)이
짝이 안 맞는 괄호를 달고 있었고, repair_brackets 로 0종이 됐다.
"""

from __future__ import annotations

import re

# 앞머리 괄호 태그. "(IT시스템관리) 시스템 운영 기획" 의 앞부분.
# 여는 괄호가 추출 과정에서 사라진 경우도 잦다. "자료관리) 자료수집·저장"
# 그대로 두면 `자료관리)자료수집저장` 이 독립 역량이 된다.
LEAD_TAG = re.compile(
    r"^\s*(?:[(（\[]([^)）\]]{1,20})[)）\]]|([^()（）\[\]]{1,20})[)）\]])\s*")
LEAD_NUM = re.compile(r"^\s*(?:\d+[.)]|[가-힣][.)]|[○●ㅇ□■▪·•\-])\s*")

# 꼬리에 붙는 유형 표지. 의미를 바꾸지 않고 문서마다 제멋대로 붙는다.
TAIL = re.compile(
    r"(?:에\s*관(?:한|하는)|에\s*대(?:한|하는)|와?\s*관련(?:한|된)?|을|를|의|이|가|은|는|및)?\s*"
    r"(?:기초|전문|기본|일반|관련)?\s*"
    r"(?:지식|이해|능력|역량|기술|스킬|기법|방법(?:론)?|절차|프로세스|태도|자세|마인드"
    r"|의지|사고|노력|활용법|사용법|숙지|파악|수준|경험|사항|내용|요소|여부)"
    r"\s*(?:등)?\s*$")
VERB_TAIL = re.compile(
    r"\s*(?:하려(?:는|고)|하고자\s*하는|할\s*수\s*있는|하는|되는|있는|없는)\s*$")
DROP_TAIL = re.compile(r"\s*(?:등|기타|외)\s*$")

# 짝이 맞지 않는 괄호. 어휘 55,237종 중 2,539종(7,441건)이 여기 걸렸다.
# 원인이 셋인데 처리가 다르다.
#
#   ① 원문이 줄바꿈에서 잘렸다 — 가장 많다
#        `협조성 (인식과 배려`      (닫는 괄호가 다음 줄로 넘어감)
#        `프로젝트 관리 (프로세스 효율성`
#      여는 괄호 뒤는 부연이므로 거기서부터 끝까지 버린다 → `협조성`
#
#   ② 원문에 괄호가 두 번 찍혔다
#        `UI((User Interface) 구현 능력`
#      겹친 여는 괄호를 하나로 줄인다 → `UI(User Interface)구현`
#
#   ③ 꼬리를 떼면서 닫는 괄호만 떨어졌다 — 우리 쪽 버그였다
#        `SW 프로세스 조정 (tailoring) 능력`
#        → 능력 제거 → `... (tailoring)` → strip 이 `)` 만 떼어 `(tailoring` 이 남음
#      ①과 같은 규칙으로 정리된다 → `SW프로세스조정`
OPEN, CLOSE = "([{（［", ")]}）］"
DOUBLED = re.compile(r"([(（\[])\1+")


class L1Normalizer:
    """표기만 정규화한다. 의미는 건드리지 않는다.

    >>> n = L1Normalizer()
    >>> n("컴퓨터 활용 능력")
    '컴퓨터활용'
    >>> n("자료관리) 자료수집·저장 방법")
    '자료수집저장'
    >>> n("(IT시스템관리) 시스템 운영 기획")
    '시스템운영기획'

    괄호가 깨진 것들. 한 번씩 실제로 역량 이름이 되어 화면까지 나갔던 사례다.

    >>> n("협조성 (인식과 배려")                       # 줄바꿈에서 잘림
    '협조성'
    >>> n("SW아키텍처) SW 프로세스 조정 (tailoring) 능력")
    'SW프로세스조정'
    >>> n("UI((User Interface) 구현 능력")             # 원문에 괄호가 두 번
    'UI(UserInterface)구현'
    >>> n("대체인력), ), ), ),")                       # 표 잔해
    '대체인력'

    짝이 맞는 괄호는 건드리지 않는다. 약어·부연이 변별에 쓰이기 때문이다.

    >>> n("고객만족도(VOC) 조사 기법")
    '고객만족도(VOC)조사'
    """

    def __call__(self, s: str) -> str:
        return self.normalize(s)

    @staticmethod
    def repair_brackets(s: str) -> str:
        """짝이 맞지 않는 괄호를 정리한다.

        LEAD_TAG 보다 **뒤에** 불러야 한다. 앞머리 소속 표시는
        `자료관리) 자료수집·저장` 처럼 여는 괄호가 없는 상태로 들어오는데,
        여기서 먼저 지워 버리면 LEAD_TAG 가 그 태그를 못 알아본다.
        """
        s = DOUBLED.sub(r"\1", s)                     # ② `((` → `(`

        depth = 0                                     # ① 닫히지 않은 괄호에서 자른다
        cut = -1
        for i, ch in enumerate(s):
            if ch in OPEN:
                if depth == 0:
                    cut = i
                depth += 1
            elif ch in CLOSE and depth:
                depth -= 1
        if depth and cut >= 0:
            head = s[:cut].strip()
            # 남는 게 너무 짧으면 부연이 아니라 본체다. 그대로 둔다.
            if len(re.sub(r"\s+", "", head)) >= 2:
                s = head

        stack, drop = [], set()                       # 남은 외톨이 괄호를 지운다
        for i, ch in enumerate(s):
            if ch in OPEN:
                stack.append(i)
            elif ch in CLOSE:
                stack.pop() if stack else drop.add(i)
        drop |= set(stack)
        return "".join(c for i, c in enumerate(s) if i not in drop)

    def normalize(self, s: str) -> str:
        t = (s or "").strip()
        t = LEAD_NUM.sub("", t)
        m = LEAD_TAG.match(t)
        if m and len(t) - m.end() >= 4:               # 앞머리 태그는 소속 표시라 뗀다
            t = t[m.end():]
        t = re.sub(r"[·․‧∙・]", " ", t)
        t = self.repair_brackets(t)
        t = re.sub(r"\s+", " ", t).strip()

        for _ in range(4):                            # "회계 관련 지식 등" → "회계"
            n = DROP_TAIL.sub("", t)
            n = TAIL.sub("", n)
            n = VERB_TAIL.sub("", n)
            n = n.strip(" ,./()[]")
            if n == t or len(n) < 2:
                break
            t = n

        # 꼬리를 떼면서 닫는 괄호만 떨어지는 경우가 있어 한 번 더 본다(③).
        t = self.repair_brackets(t).strip(" ,./")
        t = re.sub(r"\s+", "", t)                     # 띄어쓰기 흔들림 흡수
        if t:
            return t
        # 규칙을 다 태웠더니 아무것도 안 남는 경우가 있다. 빈 문자열을 내보낼 수는
        # 없으니 원문으로 돌아가되, 원문을 **그대로** 돌려주면 안 된다.
        # `대체인력), ), ), ), ...` 같은 표 잔해가 그대로 역량이 되어 버린다.
        fallback = self.repair_brackets(s or "").strip(" ,./()[]")
        return re.sub(r"\s+", "", fallback)
