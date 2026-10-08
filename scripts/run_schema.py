"""Terapkan skema Cypher berversi secara idempoten. Aman dijalankan berulang kali.
Pakai:  python -m scripts.run_schema [--wipe]"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kb.config import S  # noqa: E402
from kb.db import DB, split_statements  # noqa: E402


def apply_schema(db: DB) -> dict:
    res = {}
    for f in sorted(S.schema_dir.glob("*.cypher")):
        res[f.name] = db.run_script(f)
    if S.embeddings:
        tmpl = (S.schema_dir / "004_vector_indexes.cypher.tmpl").read_text().replace("${EMBEDDING_DIM}", str(S.embedding_dim))
        for st in split_statements(tmpl):
            db.write(st)
        res["004_vector_indexes"] = 1
    db.write("CALL db.awaitIndexes(120)")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wipe", action="store_true", help="hapus SELURUH graf sebelum menerapkan skema")
    a = ap.parse_args()
    db = DB(); db.wait_ready()
    if a.wipe:
        while db.write("MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
            pass
    print("Skema diterapkan:", apply_schema(db)); db.close()
