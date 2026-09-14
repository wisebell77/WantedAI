# `overlap/` — 직무 추천 엔진

이 패키지 하나가 **직무 추천 파트 전부**다. 수집부터 대조까지 한 방향으로 흐른다.

```
collect  →  parse  →  taxonomy  →  competency  →  recommend
공고 수집    문서 해석   분류 확정     역량 사전       대조

                    evaluate  ← 어느 단계든 "이 설정이 나은가"를 숫자로 답한다
                    config    ← 경로·상수·인증키. 모든 폴더가 여기만 본다
```

## 폴더

| 폴더 | 역할 | 네트워크 | 무거운 의존성 |
|---|---|---|---|
| `collect/` | 공고를 받아 온다 | O | requests |
| `parse/` | 바이트·HTML → 구조 | X | PyMuPDF(선택) |
| `taxonomy/` | NCS 분류 확정 | X | 없음 |
| `competency/` | 역량 사전 구축·투영 | X | sentence-transformers, scikit-learn |
| `recommend/` | 직무 × 역량 대조 | X | 없음(투영 제외) |
| `evaluate/` | 설정 비교 | X | 없음 |

경계가 이렇게 그어진 이유는 **다시 돌릴 수 있게** 하기 위해서다.
수집은 느리고 한도가 있고 실패한다. 나머지는 캐시만 있으면 몇 분이면 끝난다.
파싱 규칙을 고칠 때마다 공고를 다시 받아야 한다면 아무것도 고치지 못한다.

## 의존 방향

위에서 아래로만 의존한다. 거꾸로 부르는 곳은 없다.

```
config      ← 모두가 본다. 아무것도 import 하지 않는다
parse       ← collect(첨부 파싱), taxonomy(hwp 읽기), competency(요건 문장)
taxonomy    ← recommend(직무 이름), 파이프라인(분류 확정)
competency  ← recommend(역량 접기·투영), evaluate
recommend   ← evaluate(프로파일 만드는 방식을 공유)
```

## 가장 짧은 사용법

```python
from overlap import Recommender

r = Recommender()
for m in r.reverse(["학회 운영진으로 8명 일정 조율", "설문 300건 정리해 보고서 작성"]):
    print(m.sentence())
    for e in m.have[:3]:
        print("   ", e.competency, "<-", e.sentence)
```

## 이 패키지가 지키는 것 (CLAUDE.md)

1. **판정하지 않는다.** "당신은 HR 이 맞습니다"가 아니라 "HR 공고가 요구하는 역량
   7개와 겹칩니다 (마케팅은 3개)". 우리는 대조만 하고 해석은 사용자가 한다.
2. **근거 없는 출력은 없다.** 모든 역량에 사용자 문장과 공고 건수가 붙는다.
   못 붙이면 그 항목을 뺀다.
3. **퍼센트를 쓰지 않는다.** 겹침 비율은 무작위 대조군(61.1%)이 실제 군집(53.8%)보다
   높게 나온 지표다. 숫자가 커 보일 뿐 아무것도 증명하지 못한다.
4. **채용 플랫폼을 크롤링하지 않는다.** 공개 API 와 기업 자체 채용 페이지만 쓴다.
