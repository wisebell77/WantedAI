# 화상면접 FE 통합 가이드

## 핵심 원칙

화상면접의 분석은 브라우저에서 MediaPipe를 실행하지 않고 서버에서 처리합니다.
FE는 카메라로 녹화한 Blob을 API에 한 번 업로드하고, 응답으로 받은 세 결과를 화면에
표시하면 됩니다.

```text
녹화 Blob
  → POST /api/v1/interview/process
  → MediaPipe 영상 지표 + faster-whisper 전사
  → 선택 공고 페르소나의 JD 루브릭 평가
  → videoAnalysis / transcription / personaEvaluation
```

## 요청

```js
const response = await fetch(
  `/api/v1/interview/process?postingId=${encodeURIComponent(selectedPostingId)}`,
  {
    method: "POST",
    headers: { "Content-Type": recordedBlob.type || "video/webm" },
    body: recordedBlob
  }
);
const result = await response.json();
```

`postingId`는 반드시 사용자가 선택한 공고의 canonical ID를 사용합니다. `role-1`을
고정하면 항상 같은 테스트 공고가 평가됩니다.

특정 질문과 루브릭 항목을 선택했다면 query string에 함께 보낼 수 있습니다.

```text
?postingId=role-322&itemId=r1&question=제품%20기회를%20발굴한%20경험을%20설명해%20주세요.
```

생략하면 해당 공고 페르소나의 첫 질문과 첫 루브릭 항목을 사용합니다.

## 응답 계약

```json
{
  "videoAnalysis": {
    "model": "mediapipe-tasks-python",
    "sampleFps": 10.1,
    "durationSeconds": 11.4,
    "framesAnalyzed": 115,
    "faceCoverage": 1,
    "handFrames": 0,
    "poseCoverage": 1,
    "blinkCount": 5,
    "upperBodyMovementEvents": 0,
    "note": "관찰 가능한 신호이며 채용 적합성·감정·성격을 판정하지 않습니다."
  },
  "transcription": {
    "text": "전체 전사 문장",
    "segments": [{ "start": 0.08, "end": 6.8, "text": "구간별 전사" }],
    "model": "faster-whisper-medium",
    "beamSize": 5,
    "language": "ko"
  },
  "personaEvaluation": {
    "feedback": [{
      "label": "평가 항목",
      "title": "평가 항목 · 2/3",
      "body": "JD 기준 피드백",
      "type": "good"
    }],
    "followupQuestion": "부족한 근거를 묻는 꼬리질문",
    "evidence": [
      { "source": "JD", "quote": "공고 원문 근거" },
      { "source": "답변", "quote": "전사 답변 근거" }
    ],
    "score": 2,
    "modelUsed": "solar-pro4",
    "itemId": "r1",
    "question": "사용된 면접 질문"
  },
  "retention": "deleted-after-processing"
}
```

## 화면 표시 권장

- 녹화 영상 옆: `videoAnalysis`의 수치와 관찰 가능한 설명 표시
- 답변 영역: `transcription.text` 표시
- AI 코치 영역: `personaEvaluation.feedback`, `evidence`, `followupQuestion` 표시
- `modelUsed`가 `rule-based`이면 “규칙 기반 대체 평가”로 표시
- `personaEvaluation`이 `null`이거나 `error`를 포함하면 AI 평가 실패 상태를 표시하고 전사 결과는 유지

MediaPipe 지표는 연습용 관찰 정보입니다. 감정, 성격, 합격 가능성 또는 채용 적합성으로
표현하지 않습니다.

## 공고 페르소나 확인 API

화면에서 질문 목록을 먼저 보여줘야 한다면 다음 API를 호출합니다.

```text
GET /api/v1/agent/interview-persona?postingId={postingId}
```

`generatedBy: "llm"`이면 실제 Upstage가 생성한 페르소나이고, `heuristic`이면
Upstage 실패 시 JD에서 만든 대체 결과입니다.

## 오류 처리

- `422 VIDEO_REQUIRED`: 업로드 Blob이 비어 있음
- `413 VIDEO_TOO_LARGE`: 업로드 크기 초과
- `503 INTERVIEW_PROCESSING_UNAVAILABLE`: 서버 분석기 또는 전사기 준비 안 됨
- 응답의 `personaEvaluation.error`: 영상·전사는 성공했지만 페르소나 평가 실패

서버는 분석이 끝나면 임시 영상 파일을 삭제합니다. FE에서 녹화 영상을 별도 저장하거나
재생하려면 현재 브라우저 Blob URL을 사용하고, 서버 보관을 전제로 하지 않습니다.

## 로컬 검증

```bash
curl -s -X POST \
  --data-binary @IMG_1353.MOV \
  "http://127.0.0.1:4173/api/v1/interview/process?postingId=role-322" \
  | jq .
```

성공 기준은 `videoAnalysis`, `transcription.text`, `personaEvaluation`이 모두 있고,
실제 AI 평가라면 `personaEvaluation.modelUsed`가 `solar-pro4`인 것입니다.
