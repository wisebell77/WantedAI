# JD API 연동과 직무 AI 페르소나 설계

## 이번 MVP의 전제

- 사용자는 이미 직무를 선택했다.
- 채용공고/JD 크롤링 팀이 공고 원문과 정제 데이터를 보유한다.
- 프론트엔드는 선택된 `postingId`로 정제된 공고 하나를 조회한다.
- LLM API 키는 브라우저가 아니라 Agent 백엔드에만 둔다.

## 채용공고 컨텍스트 API 계약

### 요청

```http
GET /api/v1/job-contexts/{postingId}
Accept: application/json
```

개발 중 다른 도메인의 API를 쓸 경우 페이지가 실행되기 전에 다음 공개 URL만 설정한다. 인증 토큰이나 비밀값은 넣지 않는다.

```html
<script>window.OVERLAP_JD_API_BASE_URL = "https://api.example.com";</script>
```

면접 MVP는 다음처럼 `postingId`를 받아 API를 호출한다.

```text
/index.html?postingId=wanted-12345
```

### 성공 응답: `200 OK`

```json
{
  "postingId": "wanted-12345",
  "companyName": "예시 회사",
  "positionTitle": "데이터 분석가",
  "jobFamily": "data",
  "responsibilities": ["핵심 지표 분석", "실험 설계"],
  "requiredSkills": ["SQL", "Python", "통계 분석"],
  "preferredSkills": ["커머스 데이터", "A/B 테스트"],
  "deadline": "2026-10-15",
  "sourceUpdatedAt": "2026-09-14T10:00:00Z"
}
```

### 오류 규칙

| 상태 | 프론트 동작 |
| --- | --- |
| `404` | 선택 공고가 없다는 안내 후 직무 공통 루브릭 사용 |
| `422` | 공고 데이터가 정제되지 않았다는 안내 |
| `5xx` 또는 네트워크 오류 | 재시도 안내 후 직무 공통 루브릭 사용 |

`jobFamily` 값은 현재 프론트의 `data`, `pm`, `marketing` 중 하나로 맞춘다. 새 직무를 추가할 때는 해당 직무의 페르소나 설정도 함께 추가한다.

## 직무 AI 페르소나는 어떻게 만드는가

MVP에서 JD 원문을 모델 파인튜닝 데이터로 쓰지 않는다. 공고는 바뀌므로, 최신 JD를 조회해 근거로 쓰는 RAG/조회 방식이 더 적합하다. 페르소나는 아래 네 층을 합친 구성이다.

```text
1. 페르소나 정책: 역할, 말투, 평가 금지 범위
2. 검증 루브릭: 현직자/채용 담당자가 검수한 직무 공통 역량
3. JD 컨텍스트: 선택 기업의 업무·필수·우대사항과 출처
4. 사용자 상태: 경험 카드, 자소서, 면접 이력, 완료한 할 일
```

Agent는 매 요청에서 필요한 컨텍스트만 조합한다. 예를 들어 면접 평가에는 선택 공고, 직무 루브릭, 질문, 전사본, 음성 지표만 넣는다. 전체 크롤링 공고나 모든 과거 대화를 매번 넣지 않는다.

## Agent 도구 계약

| 도구 | 입력 | 출력 | LLM 필요 여부 |
| --- | --- | --- | --- |
| `get_job_context` | `postingId` | 위 JD API 응답 | 없음 |
| `get_user_profile` | `userId` | 경험·지원 현황·선호 | 없음 |
| `build_timeline` | 마감일, 준비 상태 | 할 일 후보와 우선순위 | 기본은 규칙 |
| `evaluate_answer` | 질문, 전사본, 루브릭, JD | 근거·부족점·꼬리질문 | 필요 시 1회 |
| `save_feedback` | 구조화 평가 결과 | 면접/자소서 이력 갱신 | 없음 |

LLM이 호출되더라도 JSON으로만 반환하게 한다.

```json
{
  "evidence": [{"rubricId": "analysis_judgment", "quote": "...", "confidence": "high"}],
  "gaps": [{"rubricId": "result_reflection", "reason": "성과 수치가 없다"}],
  "followupQuestion": "...",
  "nextActions": [{"title": "성과 수치 정리", "reason": "...", "priority": "high"}]
}
```

## 전문성 확보 순서

1. JD에서 반복되는 요구 역량을 정제하고, 직무별 공통 역량과 기업별 요구사항을 분리한다.
2. 현직자/채용 담당자가 직무 루브릭, 좋은·나쁜 답변 예시, 꼬리질문을 검수한다.
3. 위 예시로 Agent 출력의 근거 정확성·질문 적절성·일관성을 평가한다.
4. 충분한 전문가 라벨 데이터가 쌓인 뒤에만 파인튜닝을 검토한다. 파인튜닝은 지식 최신화 수단이 아니라 출력 형식·일관성 개선 수단이다.

현업 조언은 페르소나의 근거와 평가 기준을 검증하는 데 사용한다. 특정 현직자의 의견 하나를 일반적인 채용 기준으로 취급하지 않는다.
