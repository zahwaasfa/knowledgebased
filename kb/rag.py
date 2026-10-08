"""LangChain + Groq: SEMPURNAKAN draf jawaban terstruktur dari graf (bukan menjawab dari nol). Gagal / tidak valid -> None (pakai draf ekstraktif).

Draf dari kb.retrieval sudah berisi fakta + sitasi [n]. LLM hanya merapikan: kalimat jawaban langsung, poin-poin, tanpa menambah fakta.
"""
from __future__ import annotations
import re
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from .config import S

PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Anda asisten knowledge base Kementerian PPN/Bappenas. Tugas Anda MERAPIKAN DRAF JAWABAN yang diambil dari graf pengetahuan.\n"
               "Aturan:\n1. Gunakan HANYA fakta pada DRAF dan KUTIPAN. Jangan menambah angka, nama, regulasi, atau kesimpulan baru.\n"
               "2. Mulai dengan 1 kalimat jawaban langsung atas PERTANYAAN, lalu rincian dalam poin-poin (bullet) bila berupa daftar/rincian.\n"
               "3. Pertahankan penanda sitasi [n] persis seperti di DRAF dan jangan menghapus fakta penting (daftar, nama regulasi, jumlah).\n"
               "4. Jika DRAF memuat fakta, JANGAN menjawab 'tidak ditemukan'. Jika sebagian informasi memang tidak ada, katakan bagian itu saja.\n"
               "5. Bahasa Indonesia formal, ringkas. Pertahankan baris 'Sumber:' di akhir bila ada."),
    ("human", "PERTANYAAN: {question}\n\nDRAF JAWABAN (terstruktur dari graf):\n{draft}\n\nKUTIPAN SUMBER:\n{context}\n\nJawaban final:"),
])
_chain = None


def available() -> bool:
    return bool(S.use_llm and S.groq_api_key)


def get_chain(llm=None):
    global _chain
    if llm is not None:
        return PROMPT | llm | StrOutputParser()
    if _chain is None:
        from langchain_groq import ChatGroq
        _chain = PROMPT | ChatGroq(api_key=S.groq_api_key, model=S.groq_model, temperature=0.1, max_tokens=1500, timeout=45, max_retries=2) | StrOutputParser()
    return _chain


def valid(out: str, draft: str) -> bool:
    """Tolak keluaran yang menghapus sitasi, mengaku 'tidak ditemukan' padahal draf berisi fakta, atau terlalu pendek."""
    need = set(re.findall(r"\[\d+\]", draft))
    if need and not need <= set(re.findall(r"\[\d+\]", out)):
        return False
    if re.search(r"tidak (ditemukan|ada informasi)", out, re.I) and not re.search(r"tidak (ditemukan|ada informasi)", draft, re.I):
        return False
    return len(out) >= 0.35 * min(len(draft), 600)


def synthesize(question: str, draft: str, evidence: list[dict], llm=None) -> str | None:
    if not draft or not evidence or (llm is None and not available()):
        return None
    ctx = "\n\n".join(f'[{i}] ({e.get("title", "")} / {e.get("section") or "isi"}) {e.get("text", "")}' for i, e in enumerate(evidence, 1))
    try:
        out = get_chain(llm).invoke({"question": question, "draft": draft, "context": ctx}).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Groq gagal, memakai draf ekstraktif: {e}")
        return None
    if not out or not valid(out, draft):
        return None
    src = [l for l in draft.splitlines() if l.startswith("**Sumber:**")]
    return out if not src or src[0] in out else out + "\n\n" + "\n".join(src)
