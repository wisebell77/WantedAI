# `pipelines/` — 실행 스크립트

`overlap/` 은 라이브러리고, 여기는 **그걸 순서대로 부르는 얇은 껍데기**다.
로직을 여기에 두지 않는다. 스크립트가 하는 일은 인자 파싱, 호출, 출력뿐이다.
그래야 같은 기능을 웹 서버나 노트북에서도 그대로 쓸 수 있다.

## 전체 흐름

```
1. collect_public.py     ALIO 공고 → 첨부 텍스트          [느림 · 한도 있음 · 실패함]
2. build_units.py        첨부 텍스트 → 직무 단위 + NCS 코드  [캐시만 읽음]
3. refresh_private.py    민간 공고 → 직무 단위             [느림 · 외부 사이트]
4. build_dictionary.py   단위 → L2 군집 + 확장 노드         [임베딩. 캐시 있음]
5. build_matrix.py       단위 + 사전 → 행렬 + 근거 인덱스     [빠름]
6. evaluate.py           설정이 나은지 확인                 [빠름]
   recommend_demo.py     실제로 돌려 보기
```

1·3 만 네트워크를 탄다. 2·4·5·6 은 캐시만 읽으므로 규칙을 고칠 때마다
부담 없이 다시 돌리면 된다. **이 경계가 이 프로젝트를 굴러가게 한 장치다** —
파싱 규칙 하나 고칠 때마다 공고를 다시 받아야 했다면 아무것도 못 고쳤다.

## 갱신할 때

데이터를 새로 받았으면 **2 → 4 → 5 → 6 을 순서대로** 다시 돌린다.
어휘가 바뀌면 군집이 바뀌고, 군집이 바뀌면 행렬이 바뀌고, 행렬이 바뀌면
문서에 적힌 숫자가 전부 바뀐다. 하나만 돌리고 끝내면 앞뒤가 안 맞는다.

```bash
python pipelines/build_units.py
python pipelines/build_dictionary.py
python pipelines/build_matrix.py
python pipelines/evaluate.py
```

## 스크립트별 메모

| 스크립트 | 주의 |
|---|---|
| `collect_public.py` | 한도 초과 시 exit 2, 파일 서버 다운 시 exit 3. 둘 다 **재실행하면 이어서** 받는다 |
| `build_units.py` | 네트워크를 안 탄다. 분류 확정 경로별 건수가 출력되니 이상하면 여기서 잡는다 |
| `refresh_private.py` | 본문 수집(Playwright)과 이미지 판독은 밖에 있다. 판독 후 `--merge-only` |
| `build_dictionary.py` | 임베딩이 오래 걸린다. 임계만 바꿀 땐 캐시를 써서 즉시 끝난다 |
| `build_matrix.py` | 행렬과 근거 인덱스를 **같이** 만든다. `--plan` 은 수집 계획도 |
| `evaluate.py` | 숫자에 **기준일**을 같이 적는다. 갱신하면 달라진다 |
| `recommend_demo.py` | 프리셋 3종이 여기 있다. 랜딩에 그대로 쓴다 |

화면으로 보려면 `python web/server.py` (설치 불필요, `web/README.md` 참고).

## 알아 둘 것

- `.env` 가 저장소 루트에 있어야 한다(`DATA_GO_KR_KEY`, `WORK24_KEY_RECRUIT`).
  **절대 커밋하지 않는다.**
- Anaconda 환경에서 torch 가 OpenMP 충돌로 죽으면
  `KMP_DUPLICATE_LIB_OK=TRUE` 를 걸고 돌린다.
- `data/` 는 커밋하지 않는다. 용량이 크고(수천 건의 HWP·PDF) 재현이 가능하다.
