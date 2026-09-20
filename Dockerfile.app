# 앱 컨테이너 — 프론트 + AI 코치 · 화상면접 · 서류심사.
#
#   docker build -f Dockerfile.app -t overlap-app .
#   docker run -p 4173:4173 -e HOST=0.0.0.0 \
#              -e RECOMMENDATION_BASE_URL=http://engine:8000 overlap-app
#
# 추천 엔진은 **별도 컨테이너**다(루트 Dockerfile). 여기 안 넣는 이유:
# 전사(faster-whisper)가 CPU 를 다 먹는 동안 추천이 같이 멈추면 안 된다.
# 둘을 한 프로세스에 두면 면접 한 건이 진단 전체를 막는다.
#
# Node 가 현관이고 Python 자식 프로세스를 띄운다 — 그래서 한 이미지에 둘 다 있다.
#   server/transcribe.py      faster-whisper      음성 → 텍스트
#   server/analyze_video.py   mediapipe           영상 → 랜드마크 지표
#   server/persona_bridge.py  persona (표준 라이브러리)  서류심사 · 텍스트 면접

# ── 1단계: 프론트 번들. 런타임에는 npm 이 필요 없다(esbuild 가 motion 을 묶어 넣는다).
FROM node:20-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY src/ ./src/
COPY dist/ ./dist/
RUN npm run build


# ── 2단계: 런타임. Python 이 무거운 쪽이라 python 을 베이스로 잡고 node 를 얹는다.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs \
        curl ca-certificates \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
#   nodejs            local-server.mjs 실행용. npm 은 빼도 된다(번들이 1단계에서 끝났다)
#   libgl1 · libglib  mediapipe 가 opencv 를 거쳐 요구한다. 없으면 import 에서 죽는다
#   curl              헬스체크

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    MEDIAPIPE_DISABLE_GPU=1 \
    MEDIAPIPE_MODEL_DIR=/app/models

# ── 무거운 파이썬 의존성
COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

# ── faster-whisper medium 을 이미지에 굽는다 (1.46GB).
#    런타임에 받게 두면 첫 면접 답변이 모델 내려받기부터 기다린다.
#    transcribe.py 가 WhisperModel("medium", device="cpu", compute_type="int8") 를
#    쓰므로 같은 조합으로 미리 받아 둔다 — 조합이 다르면 캐시를 못 쓴다.
RUN python -c "\
from faster_whisper import WhisperModel; \
WhisperModel('medium', device='cpu', compute_type='int8')"

# ── MediaPipe task 모델 (~17MB). 파일명은 analyze_video.py 가 찾는 이름에 맞춘다.
#    pose 는 lite 를 쓴다 — full 은 CPU 에서 프레임당 비용이 크다.
RUN mkdir -p /app/models && cd /app/models \
 && B=https://storage.googleapis.com/mediapipe-models \
 && curl -fsSL -o face_landmarker.task \
      $B/face_landmarker/face_landmarker/float16/1/face_landmarker.task \
 && curl -fsSL -o gesture_recognizer.task \
      $B/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task \
 && curl -fsSL -o pose_landmarker.task \
      $B/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task \
 && ls -l /app/models

# ── 코드
# 런타임 npm 의존성. 지금은 pg 하나뿐이다 — 세션은 서명 쿠키라 라이브러리가 없고,
# 프론트 번들은 1단계에서 끝나 여기선 필요 없다.
# --omit=dev 로 esbuild 는 빼고, 번들에 들어간 motion 도 런타임에는 안 쓴다.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force

COPY server/ /app/server/
COPY persona/ /app/persona/
COPY --from=frontend /build/dist/ /app/dist/

# ── 데이터. persona 와 /api/v1/live-postings 가 읽는다.
#    통합 레포에서 한글 폴더명이 깨진 채 커밋돼 있어 data/overlap 을 통째로 가져온다.
COPY data/overlap/ /app/data/overlap/
ENV OVERLAP_DATA_DIR=/app/data/overlap

# local-server.mjs 는 .venv/bin/python 을 먼저 찾고 없으면 python3 로 떨어진다.
# 컨테이너에는 .venv 가 없으니 명시해 둔다.
ENV PYTHON_BIN=/usr/local/bin/python

EXPOSE 4173

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-4173}/api/v1/agent/status" > /dev/null || exit 1

# HOST 를 넘겨야 0.0.0.0 에 묶인다(코드 기본값은 127.0.0.1).
ENV HOST=0.0.0.0 PORT=4173
CMD ["node", "server/local-server.mjs"]
