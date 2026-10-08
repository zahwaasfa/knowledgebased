# ARCANA Bappenas — Knowledge Base Graf (Neo4j + FastAPI + Streamlit)

Dokumen → chunk hierarkis (induk → anak → cucu … tak terbatas) yang saling terhubung, ditambah organisasi, regulasi, tag, langkah proses, dan tautan lintas dokumen. Spesifikasi node/relasi: `docs/GRAPH_CONTRACT.md`. Jadwal: `docs/TIMELINE.md`.

## LLM (LangChain + Groq)
`kb/rag.py`: chain LangChain `prompt | ChatGroq | StrOutputParser` merangkum konteks graf (chunk + entitas) menjadi jawaban ber-sitasi [n]. Atur `GROQ_API_KEY`, `GROQ_MODEL_NAME`, `USE_LLM` di `.env`. Bila Groq gagal/nonaktif, API otomatis memakai jawaban ekstraktif (`answer_mode`).

## Menjalankan (Docker)
Default memakai Neo4j Aura dari `.env` (`neo4j+s://…`). Untuk Neo4j lokal (APOC, volume): set `NEO4J_USERNAME=neo4j`, `NEO4J_URI_DOCKER=bolt://neo4j:7687`, lalu `docker compose --profile local-db up -d neo4j`.
```bash
cp .env.example .env        # lalu ganti NEO4J_PASSWORD (file .env bawaan memakai password dev)
# (opsional) taruh berkas dokumen fisik di data/documents/ ; nama harus mengandung/sama dengan kolom "Nama File"
docker compose --profile local-db up -d neo4j   # (hanya Neo4j lokal) tunggu healthy (~1 menit; start pertama mengunduh plugin APOC -> perlu internet)
docker compose run --rm loader      # skema + muat data + seed Q&A  -> reports/ingest_report.md
docker compose up -d kb-api streamlit-ui
```
- Neo4j Browser http://localhost:7474 · API http://localhost:8000/docs · UI http://localhost:8501
- Jalan-ulang aman (idempoten): `docker compose run --rm loader` berkali-kali tidak menggandakan data. Reset total: `docker compose down -v`.
- Lokal tanpa Docker untuk app: `pip install -r requirements.txt`, set `NEO4J_URI=bolt://localhost:7687`, lalu `python -m scripts.run_schema && python -m scripts.run_ingest`, `uvicorn kb_api.main:app`, `streamlit run ui/app.py`.

## Perintah
| Tujuan | Perintah |
|---|---|
| Buat ulang dataset seed | `python -m scripts.generate_seed_qa` |
| Muat sebagian dokumen | `python -m scripts.run_ingest --only DOC-003 DOC-011` |
| Tes (tanpa DB) | `python -m pytest -q tests` |
| Query inti | `queries/queries_core.cypher` |

## Cara kerja jawaban (tanpa LLM, 100% dari graf)
1. Cari `Question` serupa (full-text) → bila cukup mirip: jawaban seed + `CITES` chunk sumber.
2. Jika tidak: full-text `Chunk` (+rerank tumpang-tindih kata) → cuplikan chunk sebagai jawaban + sitasi (dokumen, breadcrumb, halaman, URL).
3. Entitas terkait (unit, kedeputian, kategori, tag, regulasi, mitra) dan dokumen terkait 1–2 hop dikembalikan untuk visualisasi.

## Penyetelan chunking (`.env`)
`MAX_CHUNK_CHARS` (ukuran daun), `CHUNK_FANOUT` (anak per induk), `MAX_CHUNKS_PER_DOC` (kapasitas), `CROSSLINK_TOPK/MIN_SIM` (tautan lintas dokumen). Embedding opsional: `EMBEDDINGS=true` + `pip install sentence-transformers`.

## Catatan keamanan
Kredensial hanya di `.env` (di-`.gitignore`). Kunci Aura/Groq pada `.env` lama sudah bocor di berkas zip sebelumnya — **cabut/ganti** di konsol masing-masing.
