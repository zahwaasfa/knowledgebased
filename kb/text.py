"""Utilitas teks: tokenisasi, stopword Indonesia, query Lucene aman, skor tumpang-tindih."""
from __future__ import annotations
import re

STOP = set("""yang dan di ke dari untuk dengan pada dalam adalah ini itu atau oleh sebagai akan juga serta
dapat para atas bagi tidak ada apa siapa saja apakah bagaimana mengapa berapa kapan mana dokumen tentang
secara telah sudah lebih antara terhadap melalui yaitu yakni agar sehingga karena the of and for in to a""".split())


def tokens(text: str, min_len: int = 3) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) >= min_len and t not in STOP]


def lucene_query(text: str, max_terms: int = 12) -> str:
    seen, out = set(), []
    for t in tokens(text):
        if t not in seen:
            seen.add(t); out.append(t)
    return " OR ".join(out[:max_terms])


def overlap(query: str, candidate: str) -> float:
    q, c = set(tokens(query)), set(tokens(candidate))
    if not q or not c:
        return 0.0
    inter = len(q & c)
    return (inter / len(q)) * (inter / len(c)) ** 0.5
