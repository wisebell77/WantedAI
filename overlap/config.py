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
        return self.data / "l2_clusters_38.json"

    @property
    def l2_embeddings(self) -> Path:        # 임베딩 캐시
        return self.data / "l2_emb.npz"

    @property
    def ext_nodes(self) -> Path:            # 확장 노드
        return self.data / "ext_nodes.json"

    @property
    def job_matrix(self) -> Path:           # 직무 × 역량 행렬
        return self.data / "job_matrix.json"

    @property
    def evidence(self) -> Path:             # 근거 인덱스 (공고 원문 + 출처)
        return self.data / "evidence.json"

    @property
    def user_queries(self) -> Path:         # 사용자 방언 평가 질의
        return self.data / "user_queries_written.json"

    @property
    def descriptions(self) -> Path:         # NCS 분류 설명 (고용24 능력단위 정의)
        return self.data / "ncs_descriptions.json"

    @property
    def sub_matrix(self) -> Path:           # 세분류 × 역량 행렬
        return self.data / "job_matrix_sub.json"

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
    """교차평가 Top-3 78.8%. 임계 0.35~0.50 구간은 평탄하다."""

    min_best: float = 0.45
    """문장별 **최고** 유사도 하한. 이보다 낮으면 그 문장은 통째로 미매칭이다.

    **사용자 방언 문장으로 골랐다.** 처음엔 공고 질의로 0.55 를 골랐는데
    그게 틀렸다 — 공고 요건 문장은 명사구라 우리 축과 가깝고(평균 0.665,
    94%가 0.55 초과), 사용자 경험 서술은 멀다(평균 0.540, 50%).
    공고로 고른 문턱이 사용자에게는 너무 빡빡했다.

    실제로 랜딩 프리셋 `데이터분석` 세 문장이 0.518 / 0.489 / 0.431 로
    전부 잘려 빈 화면이 나왔다.

    사용자 방언 176문장(evaluate.userset)으로 다시 재니 이렇다.

        min_best   공고 Top-1   사용자 Top-1   사용자 질의 중 읽어낸 비율
          0.55       54.5%        25.6%            49%
          0.50       52.3%        37.5%            77%
          0.45       52.5%        43.2%            92%

    0.45 를 쓴다. 공고 기준 2.0%p 를 내주고 사용자 기준 17.6%p 를 얻는다.
    더 내려도(0.40) 1.7%p 더 오르지만, 그러면 min_similarity 와 같아져
    '아무것도 안 맞는 문장'을 거르는 장치가 사라진다.

    처음 0.55 로 올린 이유였던 오매칭(`Matlab` 이 '학회 운영진 경험'에 붙던 것)은
    **다른 수정이 이미 해결했다.** is_noise 로 잔해 노드를 빼고 코퍼스를 늘리니
    그 문장의 상위 5개가 전부 멀쩡한 노드가 됐고 Matlab 은 8위로 밀렸다.
    막고 있던 문제가 사라진 뒤에도 문턱을 계속 높게 잡고 있었던 셈이다."""

    df_weight: str = "sqrt"
    """점수에 '그 직무 안에서 얼마나 자주 요구되는가'를 반영한다.

    IDF 만 쓰면 `몇 개 직무에 나타나는가`만 본다. 그 직무 안에서 1건이 요구했든
    100건이 요구했든 같은 무게가 된다. 실제로 이런 일이 났다.

        자동차운전·운송   회의운영 공고   1건   ┐ 같은 무게로 더해져
        일반사무         회의운영 공고 100건   ┘ 1건짜리 쪽이 이겼다

    `데이터분석` 프리셋의 1위가 `자동차운전·운송` 이던 게 그 결과다.

    **raw df 를 곱하면 안 된다.** 큰 직무일수록 df 가 크므로 표본 크기 편향이
    되살아난다(일반사무 493단위 vs 정보보호 63단위). 비율(df/units)을 쓴다.

        방식                공고 T1  사용자 T1  사용자 T3  편향
        none (IDF 만)        52.5%    46.9%     71.0%   1.10
        rate (x 비율)        50.1%    46.9%     68.5%   0.69
        log  (x log(1+10r))  52.8%    48.8%     67.9%   0.76
        sqrt (x √비율)        51.7%    49.4%     69.8%   0.82   <- 이걸 쓴다

    sqrt 가 사용자 Top-1 이 가장 높고 Top-3 손실이 가장 적다.
    무엇보다 프리셋 1위가 `자동차운전·운송` → `정보기술개발` 로 바로잡힌다.

    부수 효과 하나가 더 있다. 화면의 역량 순서(JobProfile.matched)가 이 가중치로
    정렬되므로, `회의운영(공고 100건)` 이 `조직의연간행사일정(공고 1건)` 보다
    위에 온다. 근거로 내밀기에도 그쪽이 맞다."""

    # 직무군 포함 기준
    min_effective_units: int = 30
    """기관당 8단위 상한을 건 뒤의 수. 한 기관 독점을 자동으로 걸러낸다."""

    max_hhi: float = 0.25
    """허핀달 지수. 유효단위는 통과했지만 상위 몇 곳이 절반 이상인 경우를 잡는다."""

    institution_cap: int = 8
    """유효단위 계산과 수집 양쪽에서 쓰는 기관당 상한."""

    profile_unit_cap: int = 60
    """프로파일을 만들 때 직무당 쓰는 단위 수 상한. 표본 크기를 맞춘다.

    큰 직무는 어휘 폭이 넓어 어떤 질의든 걸릴 확률이 높다. 실측하니
    예측 1위 직무의 평균 단위 수가 전체 평균의 **2.07배**였다
    (경영기획 474단위가 369질의 중 87번 1위).

    다른 보정도 재 봤지만 전부 정확도를 크게 깎았다.
        점수 ÷ 단위 수      편향 0.44 — 방향만 뒤집혔다. Top-1 −12.0%p
        직무별 z 정규화      편향 0.90 — 가장 깨끗하지만 Top-1 −10.1%p.
                            잘 맞는 직무는 원래 높은 점수가 나오는 게 정상인데
                            z 변환이 그걸 '평범한 점수'로 눌러 버린다
        유효단위 문턱 80     후보가 14직무로 줄어 정답이 사라진다. Top-1 −14.1%p

    단위 맞춤만 정확도를 안 잃는다 — Top-1 57.2%(시드 5회, ±1.4%p) vs 57.5%,
    편향 2.07 → 1.31. 프로파일은 어차피 top_k 로 자르므로 60단위면 충분하다.

    **무작위로 고르지 않는다.** 기관을 번갈아 가며 고른다. 재현 가능해야 하고,
    그래야 한 기관이 표본을 차지하는 것도 같이 막힌다."""


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
