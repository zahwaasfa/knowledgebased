"""Tautan lintas dokumen antar chunk (TF-IDF cosine leksikal) -> relasi REFERENCES_CHUNK."""
from __future__ import annotations
import math
import re
from collections import Counter, defaultdict
from .text import tokens

REG = re.compile(r"undang-undang|peraturan|perpres|permen|nomor \d+ tahun", re.I)
SKIP = {"identitas", "regulasi", "data_sekunder", "mitra", "tag"}


def compute(chunks: list[dict], k: int = 3, min_sim: float = 0.3) -> list[dict]:
    """chunks: [{chunk_id, doc_id, text, section}] -> [{src,dst,similarity,type}]"""
    cand = [c for c in chunks if c.get("section") not in SKIP and len(c["text"]) > 80]
    tf = {c["chunk_id"]: Counter(tokens(c["text"])) for c in cand}
    df = Counter(w for t in tf.values() for w in t)
    n = len(cand)
    idf = {w: math.log(n / (1 + d)) + 1 for w, d in df.items()}
    vec, norm, inv = {}, {}, defaultdict(list)
    for cid, t in tf.items():
        v = {w: (1 + math.log(f)) * idf[w] for w, f in t.items()}
        vec[cid], norm[cid] = v, math.sqrt(sum(x * x for x in v.values())) or 1.0
        for w in v:
            if df[w] <= max(5, 0.15 * n):
                inv[w].append(cid)
    doc = {c["chunk_id"]: c["doc_id"] for c in cand}
    txt = {c["chunk_id"]: c["text"] for c in cand}
    rows = []
    for cid, v in vec.items():
        sc: dict = defaultdict(float)
        for w, x in v.items():
            for o in inv.get(w, ()):
                if doc[o] != doc[cid]:
                    sc[o] += x * vec[o][w]
        for s, o in sorted(((s / (norm[cid] * norm[o]), o) for o, s in sc.items()), reverse=True)[:k]:
            if s >= min_sim:
                typ = "policy_evidence" if REG.search(txt[cid]) and REG.search(txt[o]) else "semantic_similarity"
                rows.append({"src": cid, "dst": o, "similarity": round(s, 4), "type": typ})
    return rows
