"""Embedding opsional (EMBEDDINGS=true). Bila paket tidak ada, otomatis nonaktif."""
from __future__ import annotations
from .config import S
_model = None


def embed(texts: list[str]) -> list[list[float]] | None:
    global _model
    if not S.embeddings:
        return None
    try:
        if _model is None:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            _model = HuggingFaceEmbeddings(model_name=S.embedding_model, encode_kwargs={"normalize_embeddings": True})
        return _model.embed_documents(texts)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] embedding dinonaktifkan: {e}")
        return None
