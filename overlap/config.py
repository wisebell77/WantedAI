"""경로·상수·인증키를 한곳에서 관리한다.

모든 모듈은 경로를 직접 적지 않고 여기의 Paths 를 쓴다.
데이터 위치를 옮길 때 이 파일만 고치면 된다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:                                   # dotenv 없이도 동작
    def load_dotenv(*a, **k):
        return False


def _root() -> Path:
    """저장소 루트. 이 파일 기준 두 단계 위(overlap/ → 저장소)."""
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paths:
    """데이터·산출물 경로.

    data/ 는 API 응답 캐시와 중간 산출물이라 저장소에 커밋하지 않는다.
    용량이 크고(수천 건의 HWP·PDF) 재현이 가능하기 때문이다.
    """

    root: Path = field(default_factory=_root)

    @property
    def data(self) -> Path:
        """데이터 뿌리.

        찾는 순서가 있다.
            1. 환경변수 OVERLAP_DATA
            2. 저장소 안 data/      — 정상적인 배치
            3. 저장소 바로 위 data/ — 저장소를 기존 작업 폴더 안에 만든 경우.
               수천 건의 캐시를 옮기지 않고도 그대로 쓸 수 있게 열어 둔다.
        """
        import os
        env = os.getenv("OVERLAP_DATA")
        if env:
            return Path(env)
        here = self.root / "data"
        if here.exists():
            return here
        up = self.root.parent / "data"
        return up if up.exists() else here

    # 수집 캐시
    @property
    def alio_detail(self) -> Path:          # 공공 채용공시 상세 응답
        return self.data / "alio"

    @property
    def jd_files(self) -> Path:             # 내려받은 첨부 원본
        return self.data / "jdfiles"

    @property
    def jd_text(self) -> Path:              # 첨부에서 뽑은 텍스트
        return self.data / "jdtext"

    @property
    def private_static(self) -> Path:       # 민간 공고 정적 수집
        return self.data / "jd"

    @property
    def private_browser(self) -> Path:      # 민간 공고 브라우저 수집
        return self.data / "jd_js"

    @property
    def private_ocr(self) -> Path:          # 이미지 공고 판독 결과
        return self.data / "ocr"

    # 중간 산출물
    @property
    def units(self) -> Path:                # 직무 단위 (공공)
        return self.data / "jd_units.json"

    @property
    def roles(self) -> Path:                # 직무 단위 (민간)
        return self.data / "roles.json"

    @property
    def taxonomy(self) -> Path:             # NCS 공식 분류표
        return self.data / "ncs_taxonomy.json"

    @property
    def l2_clusters(self) -> Path:          # L2 의미 군집
        return self.data / "l2_clusters_35.json"

    @property
    def l2_embeddings(self) -> Path:        # 임베딩 캐시
        return self.data / "l2_emb.npz"

    @property
    def ext_nodes(self) -> Path:            # 확장 노드
        return self.data / "ext_nodes.json"

    @property
    def job_matrix(self) -> Path:           # 직무 × 역량 행렬
        return self.data / "job_matrix.json"

    def ensure(self) -> None:
        for p in (self.data, self.alio_detail, self.jd_files, self.jd_text,
                  self.private_static, self.private_browser, self.private_ocr):
            p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    """실측으로 확정한 설정값.

    근거는 docs/추천_알고리즘_설계_v2.md 4절. 바꿀 때는 감이 아니라
    overlap.evaluate 로 재고 정한다.
    """

    # 역량 추출
    sections: tuple[str, ...] = ("필요지식", "필요기술")
    """직무수행태도는 뺀다. 넣어도 Top-1 이 0.6%p 만 오르고 어휘가 27% 늘어난다."""

    # 직무 프로파일
    min_df: int = 1
    """df>=2 로 올리면 Top-1 이 7.3%p 떨어진다. 희귀 역량이 직무를 가장 잘 식별한다."""

    top_k: int = 300
    """df x IDF 상위 K. 300 과 500 이 같은 성능이라 가벼운 쪽을 쓴다."""

    # 문장 투영 (자연어 → 역량 노드)
    embed_model: str = "jhgan/ko-sroberta-multitask"
    min_similarity: float = 0.40
    project_top_k: int = 5
    """교차평가 Top-3 79.4%. 임계 0.35~0.50 구간은 평탄하다."""

    # 직무군 포함 기준
    min_effective_units: int = 30
    """기관당 8단위 상한을 건 뒤의 수. 한 기관 독점을 자동으로 걸러낸다."""

    max_hhi: float = 0.25
    """허핀달 지수. 유효단위는 통과했지만 상위 몇 곳이 절반 이상인 경우를 잡는다."""

    institution_cap: int = 8
    """유효단위 계산과 수집 양쪽에서 쓰는 기관당 상한."""


def api_key(name: str) -> str:
    """.env 에서 인증키를 읽는다. 없으면 빈 문자열.

    따옴표 제거와 URL 디코딩을 **둘 다** 해야 한다. 한쪽만 하고
    "키가 죽었다"고 두 번 오판했다. 공공데이터포털이 주는 Encoding 키는
    `%2F` 같은 이스케이프를 포함하고, .env 에 따옴표까지 붙는 경우가 있다.
    """
    root = _root()
    for p in (root / ".env", root.parent / ".env"):
        if p.exists():
            load_dotenv(p)
            break
    v = (os.getenv(name) or "").strip().strip("'\"")
    if "%" in v:                                      # 공공데이터포털 Encoding 키
        from urllib.parse import unquote
        v = unquote(v)
    return v


PATHS = Paths()
SETTINGS = Settings()
