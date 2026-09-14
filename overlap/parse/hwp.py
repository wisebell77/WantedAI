"""HWP 5.x / HWPX 에서 본문 텍스트를 뽑는다.

공공기관 직무기술서 첨부는 HWP 가 PDF 보다 많다. 한글 파서가 없으면 절반을
버리게 되므로 직접 뽑는다. 외부 의존은 olefile 하나뿐이다.

HWP 5.x 구조
    OLE2 복합문서. 본문은 BodyText/Section0..N 스트림에 있고,
    FileHeader 플래그 비트 0 이 서면 zlib(raw, -15) 로 압축되어 있다.
    레코드 헤더 4바이트(LE): tag_id bits 0-9 / level 10-19 / size 20-31.
    size 가 0xFFF 면 뒤따르는 4바이트가 실제 크기다.
    문단 텍스트는 tag_id 67(HWPTAG_PARA_TEXT), UTF-16LE.
"""

from __future__ import annotations

import io
import re
import struct
import zipfile
import zlib
from pathlib import Path

import olefile

HWPTAG_PARA_TEXT = 67

# 인라인 제어문자(뒤에 14바이트를 더 차지). 나머지 제어문자는 2바이트.
_INLINE = frozenset({4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23})

PARSEABLE = (".pdf", ".hwp", ".hwpx", ".zip")


class HwpTextExtractor:
    """HWP·HWPX·PDF·ZIP 을 텍스트로 만든다.

    >>> HwpTextExtractor().extract(Path("직무기술서.hwp"))
    '【NCS기반 채용 직무기술서】 ...'
    """

    def extract(self, data: bytes | str | Path) -> str:
        if isinstance(data, (str, Path)):
            data = Path(data).read_bytes()
        txt = self._dispatch(data, "")
        return self._tidy(txt)

    def extract_named(self, data: bytes, name: str) -> str:
        """확장자를 알 때. ZIP 안을 재귀로 훑을 때 파일명이 필요하다."""
        return self._tidy(self._dispatch(data, name))

    # ── 내부

    def _dispatch(self, data: bytes, name: str) -> str:
        low = name.lower()
        try:
            if low.endswith(".pdf") or data[:4] == b"%PDF":
                return self._pdf(data)
            if low.endswith(".zip") or data[:4] == b"PK\x03\x04":
                if low.endswith(".hwpx"):
                    t = self._hwpx(io.BytesIO(data))
                    if len(t) > 200:
                        return t
                return self._zip(data)
            if low.endswith((".hwp", ".hwpx")) or data[:8] == \
                    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                return self._hwp5(io.BytesIO(data))
        except Exception:
            return ""
        return ""

    @staticmethod
    def _pdf(data: bytes) -> str:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(p.get_text() for p in doc)

    def _zip(self, data: bytes) -> str:
        out = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for inner in z.namelist():
                if inner.endswith("/") or not inner.lower().endswith(PARSEABLE[:3]):
                    continue
                try:
                    sub = z.read(inner)
                except Exception:
                    continue
                try:                                   # 압축파일 안 이름은 cp949 가 흔하다
                    shown = inner.encode("cp437").decode("cp949")
                except Exception:
                    shown = inner
                t = self._dispatch(sub, shown)
                if t.strip():
                    out.append(f"[{shown}]\n{t}")
        return "\n\n".join(out)

    def _hwpx(self, buf) -> str:
        """hwpx 는 zip + XML. section*.xml 의 텍스트 노드만 모은다."""
        with zipfile.ZipFile(buf) as z:
            names = [n for n in z.namelist()
                     if re.search(r"Contents/section\d*\.xml$", n, re.I)]
            out = []
            for n in sorted(names):
                xml = z.read(n).decode("utf-8", "ignore")
                for m in re.finditer(r"<hp:t[^>]*>(.*?)</hp:t>", xml, re.S):
                    out.append(re.sub(r"<[^>]+>", "", m.group(1)))
                out.append("\n")
            return "".join(out)

    def _hwp5(self, buf) -> str:
        ole = olefile.OleFileIO(buf)
        try:
            head = ole.openstream("FileHeader").read()
            compressed = bool(head[36] & 0x01) if len(head) > 36 else True
            sections = sorted(
                ("/".join(s) for s in ole.listdir() if s[0] == "BodyText"),
                key=lambda x: int(re.sub(r"\D", "", x.split("/")[-1]) or 0),
            )
            chunks = []
            for name in sections:
                raw = ole.openstream(name).read()
                if compressed:
                    try:
                        raw = zlib.decompress(raw, -15)
                    except zlib.error:
                        continue
                for tag, payload in self._records(raw):
                    if tag == HWPTAG_PARA_TEXT:
                        chunks.append(self._para_text(payload))
            return "\n".join(chunks)
        finally:
            ole.close()

    @staticmethod
    def _records(buf: bytes):
        i, n = 0, len(buf)
        while i + 4 <= n:
            (header,) = struct.unpack_from("<I", buf, i)
            i += 4
            tag = header & 0x3FF
            size = (header >> 20) & 0xFFF
            if size == 0xFFF:
                if i + 4 > n:
                    break
                (size,) = struct.unpack_from("<I", buf, i)
                i += 4
            yield tag, buf[i:i + size]
            i += size

    @staticmethod
    def _para_text(payload: bytes) -> str:
        out = []
        i, n = 0, len(payload)
        while i + 2 <= n:
            (code,) = struct.unpack_from("<H", payload, i)
            if code < 32:
                i += 16 if code in _INLINE else 2
                if code in (10, 13):
                    out.append("\n")
                continue
            out.append(chr(code))
            i += 2
        s = "".join(out)
        # 본문은 UTF-16LE 다. 코드 단위를 한 글자씩 chr() 로 만들면 BMP 밖 문자
        # (이모지·확장 한자)가 서로게이트 '쌍'이 아니라 낱개로 남아,
        # UTF-8 로 저장할 때 UnicodeEncodeError 로 수집이 통째로 죽는다.
        if any("\ud800" <= c <= "\udfff" for c in s):
            s = s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
        return s

    @staticmethod
    def _tidy(txt: str) -> str:
        # 어떤 경로로 들어오든 UTF-8 로 못 쓰는 문자가 섞이면 저장이 죽는다.
        txt = txt.encode("utf-8", "replace").decode("utf-8")
        txt = txt.replace("\r", "\n")
        txt = re.sub(r"[ \t ]+", " ", txt)
        return re.sub(r"\n{3,}", "\n\n", txt).strip()
