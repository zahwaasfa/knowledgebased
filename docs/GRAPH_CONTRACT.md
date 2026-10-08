# Kontrak Graf ARCANA Bappenas (sesuai spesifikasi node & relasi)

```
(:Regulation/:Reference) <-[:USES_REFERENCE]- (:Document) -[:PUBLISHED_BY]-> (:Organization)
(:Document) -[:PRODUCED_BY]-> (:UnitKerja UKE_2) -[:PART_OF]-> (:UnitKerja UKE_1) -[:BELONGS_TO_ORG]-> (:Organization)
(:Document) -[:UNDER_DIVISION]-> (:UnitKerja UKE_1)       (:Document) -[:HAS_PARTNER]-> (:UnitKerja|:Organization)
(:Document) -[:CONTAINS_STEP]-> (:ProcessStep)             (:Document) -[:TAGGED_WITH]-> (:Tag) <-[:TAGGED_WITH]- (:Chunk)
(:Document) -[:IN_CATEGORY]-> (:Category) <-[:SUBCATEGORY_OF]- (:SubCategory) <-[:IN_SUB_CATEGORY]- (:Document)
(:Document) -[:LOCATED_IN]-> (:Location)

(:Document) -[:CONTAINS_CHUNK {sequence}]-> (:Chunk L0) <-[:SUB_CHUNK_OF {order, level_diff:1}]- (:Chunk L1) <-[:SUB_CHUNK_OF]- (:Chunk L2) <- ... Ln
(:Chunk) -[:NEXT_CHUNK {step:1}]-> (:Chunk)                      urutan saudara (sibling) dalam satu induk
(:Chunk) -[:REFERENCES_CHUNK {similarity, type}]-> (:Chunk)      lintas dokumen: semantic_similarity | policy_evidence

(:Question) -[:ANSWERED_BY]-> (:Answer) -[:CITES]-> (:Chunk);  (:Question) -[:ASKED_ABOUT]-> (:Document)   -- dataset seed
```

## Hierarki chunk (dinamis, tanpa batas kedalaman)
- Satu dokumen → banyak chunk level 0 (bab / bagian ringkasan) → anak (sub-bab) → cucu (paragraf, baris tabel, rekomendasi) → … sedalam struktur teks.
- Bagian yang punya > `CHUNK_FANOUT` (default 8) anak otomatis dikelompokkan menjadi chunk perantara ("… (bagian i/n)"), sehingga dokumen besar tumbuh ke level lebih dalam, bukan melebar.
- Setiap chunk non-daun berisi judul + ringkasan pembuka; chunk daun berisi teks utuh (≤ `MAX_CHUNK_CHARS`, dipotong di batas kalimat/kata, baris tabel tidak dipotong).
- Kapasitas: bila chunk per dokumen > `MAX_CHUNKS_PER_DOC`, ukuran chunk diperbesar otomatis sampai muat.
- `chunk_id` deterministik: `DOC-001_c0_c2_c1` (jejak indeks dari akar) → re-ingest tidak menimbulkan duplikat.
- Properti chunk: `chunk_id, doc_id, text, level, chunk_index, token_count, page_number, breadcrumb, section, item_no, is_leaf, embedding(opsional)`.

## Sumber isi
1. Metadata katalog (selalu): Ringkasan, Manfaat, Proses Bisnis (per langkah), Regulasi, Data Sekunder, Mitra, Kata Kunci → chunk dengan `section` baku (dipakai sitasi).
2. Berkas fisik (bila ada di `data/documents/`, dicocokkan dengan kolom *Nama File*): PDF/DOCX/PPTX/XLSX/CSV/TXT → bagian "Isi Dokumen" dengan hierarki heading asli.

## Ekstensi di luar spesifikasi (minimal)
`SUBCATEGORY_OF` (SubCategory→Category), label `Question/Answer` + `CITES/ANSWERED_BY/ASKED_ABOUT` untuk dataset seed, properti `Document.has_physical_file`.
