"""맞춤 공고 추천 — 지금 모집 중인 민간 공고 중 내 경험과 겹치는 것을 근거와 함께 추천한다.

    from postings import OpenCatalog, recommend_postings
"""
from .catalog import OpenCatalog, OpenRole
from .match import UserProfile, recommend_postings

__all__ = ["OpenCatalog", "OpenRole", "UserProfile", "recommend_postings"]
