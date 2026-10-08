// Index pencarian tambahan (idempoten). Dipakai oleh kb/search.py; bila belum ada, kode otomatis jatuh ke index lama (*_ft).
// Analyzer 'indonesian' = stemming + stopword bahasa Indonesia ("penyusunan" ~ "disusun", "isinya" ~ "isi").
// Verifikasi nama analyzer di versi Neo4j Anda:  CALL db.index.fulltext.listAvailableAnalyzers();
CREATE FULLTEXT INDEX chunk_text_idn IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text, n.breadcrumb] OPTIONS {indexConfig: {`fulltext.analyzer`: 'indonesian'}};
CREATE FULLTEXT INDEX document_idn IF NOT EXISTS FOR (n:Document) ON EACH [n.title, n.description, n.benefit, n.tags_text, n.subcategory] OPTIONS {indexConfig: {`fulltext.analyzer`: 'indonesian'}};
CREATE FULLTEXT INDEX question_text_idn IF NOT EXISTS FOR (n:Question) ON EACH [n.text] OPTIONS {indexConfig: {`fulltext.analyzer`: 'indonesian'}};
CREATE FULLTEXT INDEX answer_text_idn IF NOT EXISTS FOR (n:Answer) ON EACH [n.text] OPTIONS {indexConfig: {`fulltext.analyzer`: 'indonesian'}};
// Entitas untuk ekspansi graf (pertanyaan menyebut tag / regulasi / organisasi, bukan judul dokumen)
CREATE FULLTEXT INDEX tag_idn IF NOT EXISTS FOR (n:Tag) ON EACH [n.name];
CREATE FULLTEXT INDEX reference_idn IF NOT EXISTS FOR (n:Reference) ON EACH [n.title];
CREATE INDEX chunk_chunk_index IF NOT EXISTS FOR (n:Chunk) ON (n.doc_id, n.chunk_index);
