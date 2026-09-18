# Next Step 프론트엔드 통합 인계

## 화면 흐름

1. 시작 화면: 로그인 / 로그인 없이 둘러보기
2. 1차 화면: 홈 / 직무 추천 / 실시간 공고 / 프로필
3. 공고 하위 화면: AI 코치
4. 코치 하위 화면: 자소서 준비 / 면접 연습

게스트는 모든 화면과 체험용 공고의 AI 코치를 볼 수 있지만 공고·프로필·일정은
영구 저장하지 않습니다. 로그인 데모는 브라우저 저장소를 쓰며 실제 계정 DB가
아닙니다. 실제 인증 API가 정해지면 `state.auth`와 `storage` adapter만 교체합니다.

## 연결 상태

| 기능 | 프론트 연결 | 현재 실행 조건 |
| --- | --- | --- |
| 실시간 공고 | `GET /api/v1/live-postings` | `data/overlap/gongchae_all.json` |
| 공고 상세 | `GET /api/v1/job-contexts/:postingId` | `roles.json`, `jd_tiered.json` |
| 직무 추천 | `POST /api/recommend` | 별도 추천 API/container, `RECOMMENDATION_BASE_URL` |
| AI 코치 | `POST /api/v1/agent/chat` | `UPSTAGE_API_KEY` |
| 공고 Persona | `GET /api/v1/agent/interview-persona` | Persona 패키지와 공고 상세 |
| 자소서 심사 | `POST /api/v1/essays/review` | 기존 `persona.review_letter` wrapper |
| 영상 통합 처리 | `POST /api/v1/interview/process` | faster-whisper, MediaPipe 모델 |
| Tracker | UI 연결 지점 준비 | 팀 backend에서 briefing API 노출 필요 |
| 인증/계정 저장 | adapter 자리 준비 | 인증·사용자 DB API 필요 |

## 데이터 원칙

- `coachReady=true`는 현재 공고가 canonical `postingId`, JD 본문, Persona 평가
  근거를 모두 갖춘 경우에만 표시합니다.
- 공고 목록은 실제 `gongchae_all.json`을 사용합니다.
- 추천 API나 Agent가 연결되지 않았을 때 mock 성공 응답을 만들지 않습니다.
- 대용량 embedding 모델과 민간 공고 처리 파이프라인은 이 프론트 통합 범위에서
  새로 구현하지 않습니다.

## 배포 연결

- 정적 프론트는 Vercel에서 배포할 수 있습니다.
- `/api/*`는 Vercel 정적 배포만으로 생기지 않으므로 backend/container URL을
  rewrite 또는 환경변수 기반 adapter에 연결해야 합니다.
- 영상 업로드 한도, CORS, HTTPS, 인증 쿠키 정책은 배포 backend에서 확정합니다.
- API 키는 브라우저 코드에 넣지 않고 서버 환경변수로만 관리합니다.
