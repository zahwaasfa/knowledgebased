# Rencana Kerja Minggu 2 — Knowledge Base Graf (Neo4j)

Asumsi: 8 deliverable dipetakan ke 5 hari kerja; geser sesuai kalender magang. Status ✅ = berkas sudah ada di repo.

| Hari | # | Kegiatan | Deliverable | Berkas / cara verifikasi | Status |
|---|---|---|---|---|---|
| 1 | 1 | Naikkan Neo4j sebagai layanan Docker Compose: APOC, volume persisten, memori, kredensial dari `.env`, prosedur jalan-ulang | Neo4j reprodusibel | `docker-compose.yml`, `.env.example`, README §Menjalankan; cek `GET /kb/health` → `apoc` terisi | ✅ |
| 1 | 2 | Constraint keunikan, index properti, full-text; skrip berversi & idempoten | Skrip Cypher skema berversi | `schema/001–004`, `python -m scripts.run_schema` (jalankan 2× → tanpa galat/efek samping) | ✅ |
| 2 | 3 | Susun 50–100 Q&A dari 3–5 dokumen, sitasi sumber, validasi supervisor | Dataset seed tervalidasi | `data/seed_qa.json` (62 Q&A, 5 dokumen) + `data/seed_qa.csv` untuk diisi supervisor (kolom `status`, `validated_by`) | ✅ draft → ⏳ validasi |
| 2–3 | 4 | Loader Python (driver resmi): baca → normalisasi → MERGE node/relasi → galat → laporan | Loader + data benih termuat | `scripts/run_ingest.py`, `kb/ingest.py`; laporan `reports/ingest_report.md` | ✅ |
| 3 | 5 | Query: pertanyaan serupa, jawaban+sumber, ekspansi 1–2 hop, topik | Kumpulan query teruji | `queries/queries_core.cypher` (Q1–Q10), `kb/search.py` | ✅ |
| 4 | 6 | FastAPI terpisah `GET /kb/health`, `POST /kb/query` (jawaban+sitasi dari graf), via Docker | Prototipe API lokal | `kb_api/main.py`, service `kb-api`; Swagger di `:8000/docs` | ✅ |
| 4 | 7 | Sambungkan Streamlit ke API: jawaban, sitasi, visualisasi entitas; sumber jawaban = graf | UI demo KB | `ui/app.py`, service `streamlit-ui` (`:8501`) | ✅ |
| 5 | 8 | Demo end-to-end ke supervisor & tim, catat umpan balik, sesuaikan rencana paruh kedua | Notulen demo + daftar perbaikan | `docs/demo_notes_template.md` | ⏳ dilakukan saat demo |

## Skenario demo (±15 menit)
1. `docker compose up -d neo4j` → buka `localhost:7474` (tunjukkan volume persisten: restart, data tetap).
2. `docker compose run --rm loader` → tunjukkan `reports/ingest_report.md` (jumlah chunk & kedalaman per dokumen).
3. Neo4j Browser: Q4 (pohon chunk satu dokumen), Q8 (tautan lintas dokumen), Q9 (hierarki UKE).
4. Streamlit: 3 pertanyaan seed + 1 pertanyaan di luar seed (fallback chunk) → tunjukkan sitasi & graf.
5. Catat umpan balik di `docs/demo_notes_template.md`.

## Risiko & mitigasi
| Risiko | Mitigasi |
|---|---|
| Berkas fisik belum tersedia | Graf tetap terbentuk dari metadata (≥5 chunk/dokumen); taruh berkas di `data/documents/` lalu ulangi `run_ingest` (idempoten) |
| PDF hasil scan (tanpa teks) | Dicatat di `ingest_report` (`file_error`/0 chunk isi); OCR dijadwalkan paruh kedua |
| RAM terbatas | Atur `NEO4J_HEAP_MAX`, `NEO4J_PAGECACHE`, `MAX_CHUNKS_PER_DOC` di `.env` |
| Jawaban seed belum divalidasi | Kolom `status` pada `seed_qa.csv`; API menandai sumber `seed_qa` vs `chunks` |
