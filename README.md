# Overlap MVP

선택한 채용공고와 사용자의 경험을 바탕으로 취업 준비를 돕는 초기 서비스입니다.

## 현재 할 수 있는 일

- 선택 공고를 근거로 준비 타임라인, 이번 주 할 일, 자소서 시작 순서를 제안합니다.
- 공고별로 경험, 마감일, 대화, 할 일을 따로 저장합니다.
- 녹화 면접, 로컬 Whisper 전사, 규칙 기반 전달 지표 확인을 제공합니다.

## 실행

```bash
cp .env.example .env
# .env에 UPSTAGE_API_KEY 입력
npm run dev
```

브라우저에서 `http://127.0.0.1:4173`을 열면 AI 코치가 표시됩니다. 면접 연습은 `/index.html`입니다.

현재 로컬 서버는 Git에 포함하지 않는 테스트 공고 데이터 폴더를 읽습니다. 새로 받은 저장소에서는 크롤링 팀 API를 연결하거나 허용된 테스트 데이터를 별도로 받아야 AI 코치의 공고 목록이 표시됩니다.

## 팀 문서

- [현재 MVP 정리](docs/CURRENT_MVP_HANDOFF.md)
- [크롤링 팀 참고 가이드](docs/CRAWLER_TEAM_GUIDE.md)
- [화상면접 MVP 범위](docs/MVP_SCOPE.md)

## 환경 변수

```env
UPSTAGE_API_KEY=
UPSTAGE_FAST_MODEL=solar-mini
UPSTAGE_COACH_MODEL=solar-pro4
PORT=4173
```

API 키는 `.env`에만 두고 Git에 올리지 않습니다.
