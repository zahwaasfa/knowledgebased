"""Konfigurasi terpusat dari environment/.env (tidak ada kredensial di kode)."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def _s(k: str, d: str = "", *alt: str) -> str:
    for key in (k, *alt):
        v = os.getenv(key)
        if v not in (None, ""):
            return v.split("#")[0].strip()
    return d


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = _s("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = _s("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = _s("NEO4J_PASSWORD", "")
    neo4j_database: str | None = _s("NEO4J_DATABASE") or None
    docs_dir: Path = ROOT / "data" / "documents"
    metadata_json: Path = ROOT / "data" / "metadata_bappenas.json"
    seed_json: Path = ROOT / "data" / "seed_qa.json"
    schema_dir: Path = ROOT / "schema"
    reports_dir: Path = ROOT / "reports"
    max_chunk_chars: int = int(_s("MAX_CHUNK_CHARS", "1200"))
    fanout: int = int(_s("CHUNK_FANOUT", "8"))
    max_chunks_per_doc: int = int(_s("MAX_CHUNKS_PER_DOC", "3000"))
    max_table_rows: int = (int(_s("MAX_TABLE_ROWS", "20000")) or 10**9)
    crosslink_topk: int = int(_s("CROSSLINK_TOPK", "3", "CROSS_DOC_CHUNK_LINKS"))
    crosslink_min_sim: float = float(_s("CROSSLINK_MIN_SIM", "0.30"))
    embeddings: bool = _s("EMBEDDINGS", "false").lower() == "true"
    embedding_model: str = _s("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2", "EMBEDDING_MODEL")
    embedding_dim: int = int(_s("EMBEDDING_DIM", "384"))
    groq_api_key: str = _s("GROQ_API_KEY")
    groq_model: str = _s("GROQ_MODEL_NAME", "openai/gpt-oss-120b")
    use_llm: bool = _s("USE_LLM", "true").lower() == "true"
    top_k: int = int(_s("TOP_K_CHUNKS", "5"))
    api_url: str = _s("KB_API_URL", "http://localhost:8000")


S = Settings()
