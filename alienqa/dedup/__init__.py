"""alienqa.dedup：证据去重（Evidence → Issue）。"""
from .engine import Deduplicator
from .models import Issue, Vector
from .similarity import ahash, cosine, hamming, text_jaccard

__all__ = ["Deduplicator", "Issue", "Vector", "text_jaccard", "ahash", "hamming", "cosine"]
