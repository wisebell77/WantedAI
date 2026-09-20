"""로컬 확인용 웹 서버.

    python web/server.py            # http://127.0.0.1:8000
    python web/server.py --port 9000

**표준 라이브러리만 쓴다.** Flask·FastAPI 를 넣지 않은 이유는 설치 없이
팀원이 바로 돌려 볼 수 있어야 하기 때문이다. 화면을 눈으로 보고 어디가
부족한지 찾는 게 목적이지, 배포용 서버가 아니다.

엔진은 시작할 때 한 번 올린다(임베딩 모델 로딩에 20초쯤 걸린다).
요청마다 올리면 매번 그만큼 기다려야 한다.

여기는 **엔진을 호출만 한다.** 판단 로직을 여기에 두지 않는다 —
화면에서 규칙을 어기면(퍼센트를 띄운다든가) 엔진이 지킨 게 무의미해진다.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overlap import Recommender, UpstageClient           # noqa: E402
from overlap.taxonomy import NcsTaxonomy                 # noqa: E402
from overlap.config import PATHS                         # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"

# ── 직무 추천(NCS 소분류) ↔ 실시간 공고(민간 13분류) 이름 맞추기
#
# 화면에서 두 축의 이름이 달라 같은 직무인지 알 수 없었다.
#     직무 추천   법무 · 홍보·광고 · 문화예술경영   (NCS 소분류)
#     실시간 공고  생산/품질 · 연구개발             (민간 자체 13분류)
#
# 기준은 overlap/evaluate/cross.py 의 GOLD(민간 분류 → 허용 NCS 대분류)다.
# 그 표를 불러올 수 있으면 원본을 쓰고, 못 불러오면 아래 사본(2026-09-20)을 쓴다.
# GOLD 자체는 추천 정확도 평가 대상을 정하는 데도 쓰이므로 건드리지 않는다.
# 표에 없는 대분류(법률·보건·교육·서비스 계열)만 _EXTRA_FAMILY 로 채운다 — 팀 확인 필요.
_GOLD_FALLBACK = {
    "개발/SW": {"20"}, "데이터/AI": {"20"}, "IT인프라/보안": {"20"},
    "경영지원": {"02", "01"}, "생산/품질": {"15", "16", "17", "19"},
    "안전/환경": {"23"}, "영업/마케팅": {"10", "02"}, "건설/플랜트": {"14"},
    "물류/SCM": {"09", "02"}, "연구개발": {"15", "16", "17", "19", "20"},
    "디자인": {"08"},
}
try:                                                     # 원본이 있으면 원본 우선
    from overlap.evaluate.cross import GOLD as _GOLD     # noqa: E402
except Exception:                                        # pragma: no cover
    _GOLD = _GOLD_FALLBACK

_EXTRA_FAMILY = {"04": ["교육/공공"], "05": ["경영지원"], "06": ["연구개발"],
                 "11": ["고객/서비스"], "12": ["고객/서비스"], "13": ["고객/서비스"]}
# 한 대분류에 여러 민간 분류가 걸릴 때 화면·필터에 쓸 대표값
_PRIMARY_FAMILY = {"01": "경영지원", "02": "경영지원", "08": "디자인", "09": "물류/SCM",
                   "10": "영업/마케팅", "14": "건설/플랜트", "15": "생산/품질",
                   "16": "생산/품질", "17": "생산/품질", "19": "생산/품질",
                   "20": "개발/SW", "23": "안전/환경"}

MAJOR_TO_FAMILY: dict[str, list[str]] = {}
for _job, _codes in _GOLD.items():
    for _code in _codes:
        MAJOR_TO_FAMILY.setdefault(_code, []).append(_job)
for _code, _jobs in _EXTRA_FAMILY.items():
    MAJOR_TO_FAMILY.setdefault(_code, []).extend(_jobs)


def job_families(code: str) -> list[str]:
    """NCS 소분류 코드 → 민간 직무군 목록 (대분류 앞 2자리 기준)."""
    return MAJOR_TO_FAMILY.get((code or "")[:2], [])


def job_family(code: str) -> str:
    """대표 민간 직무군 하나. 실시간 공고 필터에 그대로 넘길 값."""
    fam = job_families(code)
    pick = _PRIMARY_FAMILY.get((code or "")[:2], "")
    return pick if pick in fam else (fam[0] if fam else "")

PRESETS = {
    "데이터분석": "교내 학술동아리에서 공공데이터 30만 행을 파이썬으로 정리하고 시각화했다\n"
              "설문 300건을 수집해 교차분석하고 결과를 보고서로 정리했다\n"
              "학회 운영진으로 8명의 일정을 조율하고 예산 집행 내역을 관리했다",
    "마케팅": "교내 홍보팀에서 SNS 채널을 운영하며 콘텐츠를 기획하고 반응을 분석했다\n"
           "신입생 대상 행사를 기획해 참가자 200명을 모집했다\n"
           "협찬사 5곳과 연락하며 제안서를 작성하고 조건을 조율했다",
    "개발": "팀 프로젝트에서 웹 백엔드를 맡아 API 를 설계하고 데이터베이스를 구성했다\n"
          "깃으로 브랜치를 나눠 협업하고 코드 리뷰를 진행했다\n"
          "Spring Boot 로 REST API 를 개발하고 AWS 에 배포했다",
}


class Engine:
    """엔진 한 벌을 들고 요청을 받는다. 스레드 여럿이 공유하므로 락을 건다."""

    def __init__(self):
        tax = NcsTaxonomy.load() if PATHS.taxonomy.exists() else None
        self.rec = Recommender(taxonomy=tax)
        self.llm = UpstageClient()
        self.lock = threading.Lock()                     # 모델은 동시 호출에 안전하지 않다

    def jobs(self) -> list[dict]:
        """정방향에서 고를 수 있는 목표. 소분류 + 그 아래 세분류.

        잘 모르겠으면 소분류를, 희망 직무가 구체적이면 세분류를 고른다.
        목록이 122개라 화면에서 검색으로 좁힌다.
        """
        return self.rec.targets()

    # ── 직렬화 (화면에 나갈 모양 그대로)

    @staticmethod
    def _evidence(e) -> dict:
        return {"competency": e.competency, "sentence": e.sentence,
                "postings": e.postings, "extension": e.is_extension,
                "quotes": [{"text": q.text, "postings": q.postings,
                            "source": q.sources[0].label() if q.sources else "",
                            "url": q.sources[0].url if q.sources else ""}
                           for q in e.quotes]}

    def _units(self, code: str) -> list[dict]:
        """능력단위 (이름, 공식 정의). 화면에서 마우스를 올릴 때 쓴다."""
        d = self.rec.descriptions.get(code) if self.rec.descriptions else None
        return [{"name": u, "def": v} for u, v in d.pairs()] if d else []

    def _match(self, m) -> dict:
        return {"code": m.code, "name": m.name, "units": m.units,
                "jobFamily": job_family(m.code), "jobFamilies": job_families(m.code),
                "institutions": m.institutions, "sentence": m.sentence(),
                "description": m.description,
                "abilities": self._units(m.code),
                "subdivisions": [{"name": s.name, "units": s.units,
                                  "overlap": s.overlap,
                                  "description": s.description,
                                  "abilities": self._units(s.code)}
                                 for s in m.subdivisions],
                "gaps": [{"competency": g.competency, "kind": g.kind,
                          "postings": g.postings, "rate": round(g.rate, 3),
                          "breadth": g.breadth, "sentence": g.sentence(),
                          "near": g.near_sentence,
                          "similarity": round(g.near_similarity, 3),
                          "quote": g.quotes[0].text if g.quotes else "",
                          "source": (g.quotes[0].sources[0].label()
                                     if g.quotes and g.quotes[0].sources else "")}
                         for g in m.gaps],
                "have": [self._evidence(e) for e in m.have],
                "lack": [self._evidence(e) for e in m.lack],
                "postings": [{"label": p.source.label(), "url": p.source.url,
                              "competencies": list(p.competencies)}
                             for p in m.postings]}

    @staticmethod
    def _market(s) -> dict:
        return {"term": s.term, "parent": s.parent, "roles": s.roles,
                "corps": s.corps, "sentence": s.sentence(),
                "examples": [{"corp": c, "role": r} for c, r in s.examples]}

    # ── 처리

    def tidy(self, text: str) -> dict:
        """긴 글 → 경험 문장. LLM 이 있으면 쓰고, 없거나 실패하면 규칙으로."""
        got = self.llm.split(text) if self.llm.available else []
        if got:
            return {"sentences": got, "source": "llm"}
        return {"sentences": Recommender.sentences(text), "source": "rule"}

    def recommend(self, texts, target="", seen=(), limit=5) -> dict:
        with self.lock:
            res = self.rec.profile(texts)
            out = {"sentences": Recommender.sentences(texts),
                   "nodes": sorted(res.nodes),
                   "unmatched": [{"text": s, "best": round(b, 3)}
                                 for s, b in res.unmatched],
                   "market": [self._market(s)
                              for s in self.rec.market_signals(res)]}
            if target:
                rep = self.rec.forward(texts, target)
                out["mode"] = "forward"
                out["target"] = self._match(rep.target)
                out["matches"] = [self._match(m) for m in rep.compare]
            else:
                ms = (self.rec.unexpected(texts, seen=seen, limit=limit)
                      if seen else self.rec.reverse_from(res, limit=limit))
                out["mode"] = "reverse"
                out["matches"] = [self._match(m) for m in ms]
            return out


class Handler(BaseHTTPRequestHandler):
    engine: Engine = None                                # main() 에서 채운다

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            f = STATIC / "index.html"
            self._send(200, f.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/jobs":
            self._json({"jobs": self.engine.jobs(),
                        "presets": PRESETS,
                        "llm": self.engine.llm.available})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) or b"{}"
        try:
            # 브라우저는 UTF-8 로 보내지만, 콘솔에서 curl 로 찔러 볼 때
            # 셸이 cp949 로 바꿔 보내는 경우가 있다. 그때 UnicodeDecodeError 로
            # 연결이 끊기면 "서버가 멈췄다"로 보여 원인을 못 찾는다.
            body = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            try:
                body = json.loads(raw.decode("cp949"))
            except Exception:
                return self._json({"error": "본문 인코딩을 읽을 수 없습니다"}, 400)
        except json.JSONDecodeError:
            return self._json({"error": "잘못된 요청"}, 400)
        try:
            if self.path == "/api/tidy":
                return self._json(self.engine.tidy(body.get("text", "")))
            if self.path == "/api/recommend":
                texts = body.get("texts") or []
                if isinstance(texts, str):
                    texts = [texts]
                if not any(t.strip() for t in texts):
                    return self._json({"error": "경험을 입력해 주세요"}, 400)
                return self._json(self.engine.recommend(
                    texts, body.get("target", ""), tuple(body.get("seen") or ()),
                    int(body.get("limit") or 5)))
        except KeyError as e:
            return self._json({"error": f"직무를 찾을 수 없습니다: {e}"}, 400)
        except Exception as e:                           # 화면이 죽지 않게
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass                                             # 요청 로그는 끈다


class DualStackServer(ThreadingHTTPServer):
    """IPv6 소켓 하나로 IPv4 까지 받는다.

    **Railway 같은 컨테이너 플랫폼의 내부망은 IPv6 다.** `0.0.0.0` 에 묶으면
    AF_INET 소켓이라 IPv6 로 들어오는 연결을 거부한다. 앱 컨테이너가
    `engine.railway.internal:8080` 을 부르면 그대로 연결 거부가 나고,
    프록시 쪽에는 `RECOMMENDATION_ENGINE_UNAVAILABLE` 로만 보여 원인을 못 찾는다.
    Railway 문서도 같은 이유로 MongoDB 에 `--bind_ip ::,0.0.0.0` 을 권한다.

    IPV6_V6ONLY 를 끄면 한 소켓이 양쪽을 받는다(리눅스 기본값이 이미 0 이지만
    환경에 따라 1 인 경우가 있어 명시한다).
    """

    address_family = socket.AF_INET6

    def server_bind(self):
        with contextlib.suppress(OSError):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        return super().server_bind()


def serve(host: str, port: int) -> ThreadingHTTPServer:
    """듀얼 스택으로 띄우되, IPv6 가 없는 환경이면 IPv4 로 떨어진다."""
    if host in ("0.0.0.0", "::", ""):
        try:
            return DualStackServer(("::", port), Handler)
        except OSError:
            pass                                     # IPv6 미지원 — IPv4 로
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # 컨테이너 플랫폼(Railway·Render·Cloud Run)은 PORT 를 주입한다. 그래서 환경변수를
    # 기본값으로 읽되, 기본 호스트는 127.0.0.1 로 둔다 — 로컬에서 실수로 외부에
    # 열리는 쪽이 컨테이너에서 안 열리는 쪽보다 나쁘다. 배포는 Dockerfile 이
    # --host 0.0.0.0 을 명시한다.
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT") or 8000))
    ap.add_argument("--host", default=os.getenv("HOST") or "127.0.0.1")
    ap.add_argument("--no-warmup", action="store_true",
                    help="기동 시 모델 예열을 건너뛴다(개발용)")
    args = ap.parse_args()

    if not PATHS.job_matrix.exists():
        print("행렬이 없다. 먼저 pipelines/build_matrix.py 를 돌릴 것.")
        return 1

    print("엔진을 올리는 중...", flush=True)
    t0 = time.time()
    Handler.engine = Engine()

    # **예열을 여기서 한다.** Engine() 은 0.2 초에 끝나지만 임베딩 모델은 첫
    # 투영에서야 올라온다. 예열이 없으면 컨테이너가 곧바로 "준비 완료"를 알리고
    # 헬스체크도 통과하는데, 정작 **첫 사용자가 19 초를 기다린다.**
    # 심사 기간에 그 첫 사용자가 심사위원일 수 있다.
    if not args.no_warmup:
        print("  임베딩 모델 예열 중... (20초쯤)", flush=True)
        Handler.engine.recommend([PRESETS["데이터분석"].split("\n")[0]], limit=1)

    n = len(Handler.engine.rec.matrix)
    llm = "켜짐" if Handler.engine.llm.available else "꺼짐(규칙 분리로 동작)"
    print(f"준비 완료 ({time.time() - t0:.1f}초) — 직무 {n}개 · "
          f"근거 {len(Handler.engine.rec.evidence):,}쌍 · LLM {llm}")
    print(f"  http://{args.host}:{args.port}  (Ctrl+C 로 종료)", flush=True)

    srv = serve(args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
