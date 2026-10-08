"""Muat metadata (+ berkas di data/documents) ke Neo4j. Idempoten.
Pakai:  python -m scripts.run_ingest [--only DOC-001 DOC-002] [--no-seed]"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kb.ingest import run  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--no-seed", action="store_true")
    a = ap.parse_args()
    r = run(a.only, not a.no_seed)
    print(f'Selesai: {r["documents"]} dokumen, {sum(x["chunks"] for x in r["per_document"])} chunk, {r["crosslinks"]} crosslink, {len(r["errors"])} galat')
    sys.exit(1 if r["errors"] else 0)
