"""공고 페르소나 — 공고 데이터로 채점표(루브릭)·채용담당자 페르소나를 만들고,
그 채점표로 서류 심사와 텍스트 면접을 진행한다.

    from persona import load_roles, build_rubric, review_letter, InterviewSession
"""
from .data import load_roles, get_role, job_market
from .rubric import build_rubric, load_or_build, to_interview_rubric
from .doc_review import review_letter
from .interview import InterviewSession

__all__ = ["load_roles", "get_role", "job_market", "build_rubric", "load_or_build",
           "to_interview_rubric", "review_letter", "InterviewSession"]
