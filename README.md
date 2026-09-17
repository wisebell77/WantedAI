# Overlap MVP

선택한 채용공고와 사용자의 경험을 바탕으로 취업 준비를 돕는 초기 서비스입니다.

## 현재 할 수 있는 일

- 선택 공고를 근거로 준비 타임라인, 이번 주 할 일, 자소서 시작 순서를 제안합니다.
- 공고별로 경험, 마감일, 대화, 할 일을 따로 저장합니다.
- 녹화 면접, 공고 JD 용어를 힌트로 쓰는 faster-whisper medium 전사(beam size 5), MediaPipe 영상 지표를 제공합니다.
- 선택 공고에서 만든 직무 루브릭으로 답변을 평가하고, 약한 항목에는 한 번 꼬리질문합니다.

## 실행

```bash
cp .env.example .env
# .env에 UPSTAGE_API_KEY 입력
npm run dev
```

브라우저에서 `http://127.0.0.1:4173`을 열면 AI 코치가 표시됩니다. 면접 연습은 `/index.html`입니다.

## 서버에서 개별 기능 확인

화상 분석은 브라우저가 아니라 서버에서 실행할 수 있습니다. Python 의존성과
MediaPipe 작업 모델은 서버에 한 번만 준비합니다.

```bash
.venv/bin/pip install -r requirements-server.txt
.venv/bin/python scripts/download_mediapipe_models.py

# 각 명령은 JSON 한 줄을 출력합니다.
.venv/bin/python server/transcribe.py ./sample.webm "지원 직무의 전문 용어"
.venv/bin/python server/analyze_video.py ./sample.webm
```

HTTP로 확인할 때는 영상 파일을 서버에 보내면 처리 완료 후 임시 파일이
삭제됩니다.

```bash
curl -X POST --data-binary @sample.webm \
  http://127.0.0.1:4173/api/v1/interview/transcribe
curl -X POST --data-binary @sample.webm \
  http://127.0.0.1:4173/api/v1/interview/analyze
# 한 번 업로드해 전사와 영상 분석을 함께 실행
curl -X POST --data-binary @sample.webm \
  'http://127.0.0.1:4173/api/v1/interview/process?postingId=role-1'
```

`process` 응답에는 `videoAnalysis`, `transcription`, `personaEvaluation`이 함께
포함됩니다. `postingId`의 공고 페르소나가 전사 텍스트를 같은 루브릭으로
평가하며, 특정 질문·항목을 쓰려면 `question`과 `itemId`를 query string으로
전달합니다.

`MEDIAPIPE_NOT_INSTALLED` 또는 `MEDIAPIPE_MODELS_MISSING`이 나오면 서버 준비가
끝나지 않은 상태입니다. 모델은 `MEDIAPIPE_MODEL_DIR` 또는 개별
`MEDIAPIPE_*_MODEL` 환경 변수로 다른 위치를 지정할 수 있습니다.

서버는 요청이 끝나는 즉시 업로드 임시 파일을 삭제합니다. 브라우저가 닫힌
뒤에 삭제하는 방식은 브라우저 종료 이벤트가 보장되지 않으므로, 보관하지
않는 현재 방식이 더 안전합니다.

현재 로컬 서버는 Git에 포함하지 않는 테스트 공고 데이터 폴더를 읽습니다. 새로 받은 저장소에서는 크롤링 팀 API를 연결하거나 허용된 테스트 데이터를 별도로 받아야 AI 코치의 공고 목록이 표시됩니다.

## 팀 문서

- [현재 MVP 정리](docs/CURRENT_MVP_HANDOFF.md)
- [크롤링 팀 참고 가이드](docs/CRAWLER_TEAM_GUIDE.md)
- [화상면접 MVP 범위](docs/MVP_SCOPE.md)
- [직무 페르소나 구현 안내](persona/README.md)
- [팀 공유용 MVP 요약](docs/TEAM_MVP_SUMMARY.md)

## 환경 변수

```env
UPSTAGE_API_KEY=
UPSTAGE_FAST_MODEL=solar-mini
UPSTAGE_COACH_MODEL=solar-pro4
PORT=4173
```

API 키는 `.env`에만 두고 Git에 올리지 않습니다.
