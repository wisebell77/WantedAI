# `persona/` — 공고 페르소나 (서류 심사 · 텍스트 면접)

담당: 김소연 · 브랜치 `feat/persona`

## 한 줄 요약
수집 공고 1건을 읽어 **그 공고 전용 채점표**와 **채용담당자 페르소나**를 만들고,
같은 채점표로 **자소서 심사**와 **텍스트 면접**을 한다. 모든 판단은 공고 원문 인용에 묶인다.

```
[오프라인] 공고(data/overlap) ──► build_rubric ──► out/rubrics/{role_id}.json
                                                   └► interview/{role_id}.json (승민 님 화상면접 형식)
[온라인]   채점표 + 자소서 + 경험 ──► review_letter ──► 항목별 충분/약함/없음 + 고칠 방향
           채점표 + 서류심사 결과 ──► InterviewSession ──► 약한 항목부터 질문 → 채점 → 꼬리질문
```

## 파일
| 파일 | 하는 일 |
|---|---|
| `data.py` | roles.json + jd_tiered.json → 직무 단위 `RoleDoc`. 공고 본문에서 직무 구간만 잘라냄. `job_market()` 은 직무군별 기술 요구 빈도 |
| `rubric.py` | 채점표·페르소나 생성. LLM → 인용 검증 → 부족하면 규칙 기반. 가중치 = 항목 종류 × (1 + 직무군 요구 비율) |
| `doc_review.py` | 서류 심사. strong/weak/missing + action(keep·revise·insert·prepare) |
| `interview.py` | 텍스트 면접 세션. 0~3점, 2점 미만이면 꼬리질문 1회, 꼬리 답은 최초 답과 합쳐 재평가 |
| `grounding.py` | LLM 인용문이 원문에 실제로 있는지 검사 (가짜 근거 폐기) |
| `llm.py` | Upstage 호출. 승민 님 서버와 같은 URL·환경변수. 키 없으면 None → 규칙 기반 |

## 실행
```bash
# 1) 데이터: Overlap_데이터 zip의 data/roles.json, jd_tiered.json, analysis.json → data/overlap/
# 2) (선택) .env 에 UPSTAGE_API_KEY=...   (없어도 규칙 기반으로 돈다)
python demo_persona.py                      # 채점표 → 서류 심사 → 면접 데모
python demo_persona.py --interactive        # 면접 답변 직접 입력
python scripts/build_rubrics.py --no-llm    # A등급 채점표 일괄 생성
```
외부 패키지 없음(표준 라이브러리만).

## 지켜야 할 원칙
- **없는 경험을 지어내지 않는다.** 근거 경험이 없으면 `prepare`(준비 필요)로 넘긴다.
- **인용은 코드로 검증한다.** 원문에 없는 인용 → 항목 폐기(채점표) / 근거 불인정(심사·면접).
- **점수는 합격 가능성이 아니다.** 결과에 항상 note 를 붙인다. 성격·외모 등은 평가하지 않는다.
- **표본을 부풀리지 않는다.** 시장 신호는 "같은 직무군 A등급 N건 중 k건"으로만 표시.
- **`data/overlap/`, `out/` 은 커밋 금지** (공고 원문 재배포 금지).

## 다른 파트와의 연결
- **승민(화상면접)**: `out/rubrics/interview/*.json` 을 읽어 하드코딩 루브릭 대체.
  `checks: item.keywords.map(k => new RegExp(k, "i"))`. 내용 평가·꼬리질문은 `InterviewSession` 로직을 API로 붙이면 됨.
- **근하(트래커)**: 근하 님 커버 판정 = 역량이 드러났나 / 여기 = 심사자가 설득되나. `review_letter` 의 `prepare` 항목을 트래커 할 일로 넘길 수 있음.
- **직무추천(예린·현종)**: 현재 시장 신호는 수집 공고 빈도. 추천 엔진의 직무 프로파일(IDF)로 교체 가능한 자리가 `data.job_market()`.

## 현재 한계
- 규칙 기반 채점표는 A등급 91개 직무 중 약 60개만 3항목 이상 나온다(공고 형식이 제각각임). 나머지는 LLM 필요.
- 규칙 기반 심사·채점은 키워드·수치 유무만 본다 → 발표에서 "LLM 판정이 필요한 이유"로 대비 가능.
- LLM 경로는 아직 실제 키로 품질 검증 전.
