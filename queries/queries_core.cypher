// ARCANA Unified Generic Schema - query inti (identik Bappenas & Bencana). 11 label, 11 relasi. Ganti literal sesuai kebutuhan.
// ---- Analitik taksonomi / sebaran ----
// A1. Rekap dokumen per kategori & sub-kategori (jenis bencana/topik adalah SubCategory)
MATCH (d:Document)-[:IN_CATEGORY]->(s:SubCategory)-[:SUBCATEGORY_OF]->(c:Category)
RETURN c.name AS kategori, s.name AS sub_kategori, count(DISTINCT d) AS jumlah, collect(DISTINCT d.year)[..6] AS tahun ORDER BY jumlah DESC;

// A2. Sebaran dokumen per sub-kategori dan tahun (tahun = properti Document)
MATCH (d:Document)-[:IN_CATEGORY]->(s:SubCategory) RETURN s.name AS sub_kategori, d.year AS tahun, count(d) AS jumlah ORDER BY sub_kategori, tahun;

// A3. Tingkat keparahan genangan per kecamatan (dari baris tabel; bencana) - kelas dari properti Chunk.inundation_cm
MATCH (c:Chunk)-[:LOCATED_IN]->(l:Location) WHERE c.inundation_cm IS NOT NULL
OPTIONAL MATCH (l)-[:LOCATED_IN*0..3]->(k:Location {level:'kecamatan'})
WITH coalesce(k, l) AS wilayah, c
RETURN wilayah.name AS wilayah, count(c) AS kejadian, round(avg(c.inundation_cm),1) AS rata2_cm, max(c.inundation_cm) AS maks_cm,
       sum(CASE WHEN c.inundation_cm >= 100 THEN 1 ELSE 0 END) AS berat_gte_100cm,
       sum(CASE WHEN c.inundation_cm >= 50 AND c.inundation_cm < 100 THEN 1 ELSE 0 END) AS sedang_50_99cm,
       sum(CASE WHEN c.inundation_cm < 50 THEN 1 ELSE 0 END) AS ringan_lt_50cm ORDER BY maks_cm DESC LIMIT 20;

// A4. Rekap dampak infrastruktur: dokumen dampak per Tag berjenis infrastruktur
MATCH (d:Document {category:'Data Dampak'})-[:TAGGED_WITH]->(t:Tag {kind:'infrastruktur'})
RETURN t.name AS infrastruktur, count(d) AS dataset, collect(d.title)[..3] AS contoh ORDER BY dataset DESC;

// A5. Status kerusakan & total kerugian per kota (properti Chunk dari baris tabel)
MATCH (c:Chunk)-[:LOCATED_IN]->(l:Location) WHERE c.damage_status IS NOT NULL OR c.loss_value IS NOT NULL
OPTIONAL MATCH (l)-[:LOCATED_IN*0..3]->(k:Location) WHERE k.level IN ['kota','kabupaten']
RETURN coalesce(k.name, l.name) AS kota, c.damage_status AS status, count(c) AS jumlah, sum(c.loss_value) AS total_kerugian ORDER BY kota, jumlah DESC;

// A6. Hierarki lokasi (anak LOCATED_IN induk) + jumlah dokumen yang mencakupnya
MATCH (l:Location) OPTIONAL MATCH (l)-[:LOCATED_IN]->(p:Location) OPTIONAL MATCH (d:Document)-[:LOCATED_IN]->(l)
RETURN l.level AS level, l.name AS lokasi, p.name AS induk, count(d) AS dokumen ORDER BY level, lokasi LIMIT 50;

// A7. Hierarki organisasi: unit -> kedeputian -> instansi (semua Organization; level di properti)
MATCH (u:Organization)-[b:BELONGS_TO_ORG]->(p:Organization) RETURN p.name AS induk, p.level AS level_induk, collect(u.name)[..8] AS anggota, b.level_path AS jalur ORDER BY level_induk LIMIT 30;

// A8. Dokumen per organisasi menurut peran (penerbit / penyusun_utama / kedeputian / mitra_internal / mitra_eksternal)
MATCH (d:Document)-[b:BELONGS_TO_ORG]->(o:Organization) RETURN b.role AS peran, o.name AS organisasi, count(d) AS dokumen ORDER BY dokumen DESC LIMIT 30;

// A9. Rujukan/regulasi/sumber data (Reference lewat TAGGED_WITH berperan) yang paling banyak dipakai
MATCH (d:Document)-[b:TAGGED_WITH]->(r:Reference) RETURN r.title AS rujukan, b.role AS peran, count(d) AS dokumen ORDER BY dokumen DESC LIMIT 15;

// ---- Tanya-jawab & penelusuran ----
// B1. Pertanyaan serupa (full-text) -> jawaban
CALL db.index.fulltext.queryNodes('question_text_ft', 'manfaat OR laporan OR kejadian') YIELD node, score
MATCH (node)-[:ANSWERED_BY]->(a:Answer) RETURN node.question_id AS id, node.text AS pertanyaan, a.text AS jawaban, score ORDER BY score DESC LIMIT 5;

// B2. Jawaban beserta sumber (id chunk sitasi disimpan di Answer.cited_chunk_ids; Question -ASKED_ABOUT-> Chunk juga tersedia)
MATCH (q:Question {question_id:'Q001'})-[:ANSWERED_BY]->(a:Answer) UNWIND a.cited_chunk_ids AS cid
MATCH (c:Chunk {chunk_id:cid}) MATCH (d:Document {doc_id:c.doc_id}) RETURN q.text AS pertanyaan, a.text AS jawaban, d.title AS dokumen, c.breadcrumb AS lokasi, c.page_number AS halaman;

// B3. Pohon chunk satu dokumen (hierarki tak terbatas; urutan saudara = SUB_CHUNK_OF.order / Chunk.chunk_index)
MATCH (d:Document {doc_id:'DOC-001'})-[:CONTAINS_CHUNK]->(r:Chunk) MATCH (c:Chunk)-[:SUB_CHUNK_OF*0..]->(r)
RETURN c.level AS level, c.chunk_id AS id, c.is_leaf AS daun, substring(c.text,0,80) AS cuplikan ORDER BY c.chunk_id;

// B4. Ekspansi 1-2 hop: dokumen lain yang berbagi tag / kategori / lokasi
MATCH (d:Document {doc_id:'DOC-001'})-[:TAGGED_WITH|IN_CATEGORY|LOCATED_IN]->(x)<-[:TAGGED_WITH|IN_CATEGORY|LOCATED_IN]-(o:Document)
WHERE o <> d RETURN o.title, collect(DISTINCT coalesce(x.name, x.title))[..5] AS bersama, count(DISTINCT x) AS n ORDER BY n DESC LIMIT 10;

// B5. Tautan lintas dokumen antar chunk
MATCH (a:Chunk)-[r:REFERENCES_CHUNK]->(b:Chunk) WHERE a.doc_id <> b.doc_id
RETURN a.doc_id, a.breadcrumb, b.doc_id, b.breadcrumb, r.similarity, r.type ORDER BY r.similarity DESC LIMIT 10;

// B6. Langkah proses (ProcessStep) satu dokumen
MATCH (d:Document {doc_id:'DOC-003'})-[x:CONTAINS_STEP]->(s:ProcessStep) RETURN s.step_order AS no, s.description ORDER BY no;

// B7. Validasi skema: label/relasi di luar skema terpadu (harus kosong)
CALL db.labels() YIELD label WHERE NOT label IN ['Document','Chunk','Category','SubCategory','Tag','Organization','Location','ProcessStep','Question','Answer','Reference'] RETURN 'LABEL' AS jenis, label AS nama
UNION
CALL db.relationshipTypes() YIELD relationshipType AS nama0 WHERE NOT nama0 IN ['CONTAINS_CHUNK','SUB_CHUNK_OF','IN_CATEGORY','SUBCATEGORY_OF','TAGGED_WITH','BELONGS_TO_ORG','LOCATED_IN','REFERENCES_CHUNK','CONTAINS_STEP','ASKED_ABOUT','ANSWERED_BY'] RETURN 'RELASI' AS jenis, nama0 AS nama;

// B8. Chunk yatim (harus 0)
MATCH (c:Chunk) WHERE NOT (c)-[:SUB_CHUNK_OF]->() AND NOT (:Document)-[:CONTAINS_CHUNK]->(c) RETURN count(c) AS chunk_yatim;
