# WantedAI — Overlap · AI 비서 파트

원티드 AI 해커톤 프로젝트. **Overlap**(진단: 내 경험 ↔ 채용 공고 요구 역량 대조)의
결과를 **실행**으로 잇는 개인 비서 레이어다.

> 이 레포의 `ai_tracker` 브랜치는 **AI 비서 파트**를 담당한다.
> Overlap(진단) 본체는 별도 파트에서 진행한다.

## 무엇을 하나

공고를 담아두면, 내가 쓰는 자소서와 마감일을 **능동적으로 추적**해서
"오늘 뭘 어디까지 해야 하는지"를 짚어준다.

```
공고(요구 역량) + 자소서 초안 + 마감일
  → ① 역량별 커버 판정   (자소서가 요구 역량을 얼마나 드러내나 + 근거 문장)
  → ② 커버율·격차 계산
  → ③ 넛지 문구 + 오늘의 목표
  → 여러 공고면 우선순위 랭킹
```

두 개의 축을 분리해서 본다:

| 축 | 의미 | 무엇과 무엇을 비교 |
| --- | --- | --- |
| **fit (적합도)** | 이 직무가 나한테 맞나 | 내 **전체 경험** ↔ 공고 요구 |
| **coverage (진행도)** | 이 자소서에 얼마나 담았나 | 이 공고용 **자소서 초안** ↔ 공고 요구 |

→ "경험은 충분한데(fit↑) 아직 안 썼다(coverage↓)" = 좋은 기회 → 우선순위↑

## 실행

LLM 키 **없이도** 동작한다(휴리스틱 fallback). 있으면 판정 품질이 올라간다.

```bash
python demo.py         # 합성 샘플 (데이터 불필요)
python run_nudge.py    # 실제 공고로 엔진(fit·커버판정·넛지·우선순위) 시연 (data/overlap/ 필요)
python run_tracker.py  # 담아두고 날짜별로 추적 (저장/복원) 시연
```

LLM 판정을 쓰려면:

```bash
pip install -r requirements.txt
cp .env.example .env   # .env 에 ANTHROPIC_API_KEY 를 채운다 (커밋 금지)
python demo_real.py
```

## 구조

```
assistant/
  models.py          데이터 계약 (Competency·Posting·EssayDraft/Section·CoverageResult…)
  llm.py             LLM 래퍼 + .env 로더 (키 없으면 None → 휴리스틱)
  coverage.py        ① 자소서(문항별) → 역량 커버 판정 (근거 문장 + 어느 문항인지)
  fit.py             적합도 간이 추정기 (경험 기반, Overlap 연동 전 대체)
  scheduler.py       ③ 우선순위 = 격차 × 마감임박도 × 적합도
  nudge.py           ③ 넛지 + 오늘의 목표 (미충족 역량을 어느 문항에 넣을지까지)
  overlap_loader.py  실제 Overlap 공고 데이터 → 엔진 모델 변환
  tracker.py         담아둔 공고+자소서 보관 & 일자별 진행 스냅샷 (저장/복원)
demo.py / run_nudge.py / run_tracker.py   (실행 스크립트 — 루트=실행, assistant/=부품)
data/                로컬 전용 (⚠ .gitignore — Overlap 데이터·자소서 보관본 커밋 금지)
```

### 자소서 입력 구조 (프론트엔드 대응)

자소서는 한 덩어리가 아니라 **문항별**로 받는다(`EssayDraft` = `EssaySection` 리스트).
프론트엔드의 문항 입력란과 1:1로 맞물린다.

- **A. 입력**: 공고별 자소서 문항(질문+답변)을 그대로 받음
- **B. 넛지**: 엔진이 답변→요구역량을 매핑하고, 빈 역량을 *"어느 문항에 넣어라"* 로 안내

## 데이터 취급 ⚠️

Overlap 수집 공고 본문은 **내부 검토용이며 외부 재배포 금지**다.
`data/overlap/`, `.env` 는 `.gitignore`로 커밋에서 차단돼 있다. 각자 로컬에만 둔다.

## 진행 상황

- [x] 핵심 엔진 (커버 판정 → 커버율/격차 → 넛지 → 우선순위)
- [x] 우선순위에 **적합도(fit)** 축 반영 (`격차 × 마감임박도 × 적합도^1.5`, 가중치 튜닝 가능)
- [x] 실제 Overlap 공고 데이터 연동 (로더, 중요도는 코퍼스 빈도로 근사)
- [x] 적합도 **자체 추정기** (경험 기반, mock 제거)
- [x] 자소서 **문항별** 입력 구조 + 넛지가 어느 문항에 넣을지 안내
- [x] **오늘 할 일 브리핑** (여러 공고 종합 → 한 가지 집중 + 마감 경보)
- [x] 진행도 스냅샷 기록 (`tracker.py` — 여러 날 추이, 저장/복원)
- [x] **LLM 실연동 완료** — `.env` 키로 판정·넛지·fit·트래킹 모두 LLM 동작 확인
- [ ] FastAPI / 데모 UI

### 아직 mock / 미완인 값

| 값 | 상태 | 최종 출처 |
| --- | --- | --- |
| 요구 역량 | 실제 데이터의 기술 키워드 | Overlap (정규화·레벨링은 미완) |
| 역량 중요도 | 코퍼스 빈도로 근사 | Overlap 정식 가중치 |
| **적합도(fit)** | 경험 기반 자체 추정 | Overlap 진단 산출값 |
| **요구 수준** | 비어 있음 | Overlap '요구 수준 추출' |
| **마감일** | 데모용 임시값 | 사용자 입력 (공고 담을 때) |

### 알려진 한계

- 휴리스틱 판정은 `파이썬` vs `Python` 같은 표기 차이를 못 잡는다 → LLM 판정이 해결.
- 코퍼스가 제조/경영지원 편중(제조 130 : IT 36)이라 IT/데이터 공고 수가 적다.

### 환경 트러블슈팅 (LLM "Connection error" 시)

일부 환경(anaconda base 등)에서 응답 압축 해제 버그로 연결이 실패할 수 있다. 대응:
- `pip install -U httpcore` (1.0.9+)
- 코드가 `Accept-Encoding: identity` 로 압축을 끄고 요청한다(`assistant/llm.py`) — 정상 환경엔 무해.
- 그래도 안 되면 깨끗한 venv 사용: `python -m venv .venv` → 활성화 → `pip install anthropic`.
