# 직무 추천 엔진 컨테이너.
#
#   docker build -t overlap-engine .
#   docker run -p 8000:8000 overlap-engine
#
# 팀 통합 레포(feat/nextstep-ai-integration) 루트에서 빌드하는 것을 전제로 한다.
# Node 서버(server/local-server.mjs)는 여기 안 들어간다 — 런타임이 다르고 가볍다.
# 그쪽은 RECOMMENDATION_BASE_URL 로 이 컨테이너를 가리키면 된다.
#
# ── 왜 이렇게 생겼나 (실측 근거)
#   torch 기본 휠은 CUDA 를 끌고 와 이미지가 GB 단위로 뛴다. CPU 휠을 쓴다.
#   임베딩 모델(430MB)을 빌드 때 받아 굽는다. 런타임에 받으면 첫 기동이 60초+.
#   노드 캐시(l2_emb.npz)를 빌드 때 만든다. 없으면 기동이 18초 → 57초.
#   기동 시 예열한다(web/server.py). 안 하면 헬스체크는 통과하고 첫 사용자가 18초를 문다.

FROM python:3.11-slim

# libgomp 은 torch 가, curl 은 헬스체크가 쓴다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    KMP_DUPLICATE_LIB_OK=TRUE

# ── 1. 무거운 의존성 먼저. 코드가 바뀌어도 이 층은 재사용된다.
RUN pip install --no-cache-dir \
        torch>=2.4 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        "numpy>=2.0" "sentence-transformers>=5.0" "scikit-learn>=1.5" \
        "requests>=2.32" "python-dotenv>=1.0" "olefile>=0.47"
# olefile 은 서빙에 안 쓰일 것 같지만 빠지면 `import overlap` 이 죽는다 —
# overlap/parse/hwp.py 가 모듈 최상위에서 import 한다. PyMuPDF(fitz)는 지연
# import 라 서빙 이미지에 넣지 않는다(수집할 때만 쓴다).

# ── 2. 임베딩 모델을 이미지에 굽는다 (430MB).
#    런타임에 Hugging Face 에서 받게 두면 첫 기동이 60초+ 로 늘고,
#    HF 가 느리거나 막히면 컨테이너가 아예 못 뜬다.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('jhgan/ko-sroberta-multitask')"

# ── 3. 코드
COPY overlap/ /app/overlap/
COPY pipelines/ /app/pipelines/
COPY web/ /app/web/

# ── 4. 산출물.
#    통합 레포에서 한글 폴더명이 깨진 채 커밋돼 있다(`산출물` → `#Uc0b0#Ucd9c#Ubb3c`).
#    빌드 인자로 받아 두어 이름을 정리하면 --build-arg 로 넘기면 된다.
ARG ARTIFACTS=data/overlap/#Uc0b0#Ucd9c#Ubb3c
COPY ${ARTIFACTS}/ /app/data/
ENV OVERLAP_DATA=/app/data

# ── 5. 노드 임베딩 캐시를 여기서 만든다 (6.4MB, 40초).
#    군집 파이프라인이 만드는 원본 캐시는 143MB 라 이미지에 넣지 않는다.
#    사전(l2_clusters_*.json)만 있으면 되므로 원본 단위 68MB 가 필요 없다.
RUN python pipelines/build_node_cache.py \
    && test -f /app/data/l2_emb.npz

EXPOSE 8000

# 기동에 예열 18초가 걸린다. start-period 를 넉넉히 준다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/jobs" > /dev/null || exit 1

# --host 0.0.0.0 을 명시한다. 코드 기본값은 127.0.0.1 이다 —
# 로컬에서 실수로 외부에 열리는 쪽이 컨테이너에서 안 열리는 쪽보다 나쁘다.
# 포트는 플랫폼이 주입하는 PORT 를 따른다(Railway·Render·Cloud Run).
CMD ["sh", "-c", "python web/server.py --host 0.0.0.0 --port ${PORT:-8000}"]
