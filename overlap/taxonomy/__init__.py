"""NCS 분류 체계 — 이름과 코드를 잇고, 문서의 분류를 확정한다."""

from .ncs import NcsNode, NcsTaxonomy, normalize
from .resolver import NcsResolver, Resolution

__all__ = ["NcsTaxonomy", "NcsNode", "normalize", "NcsResolver", "Resolution"]
