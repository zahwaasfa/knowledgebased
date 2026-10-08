// Index properti (tahun, satuan, angka dampak = PROPERTI, bukan node)
CREATE INDEX chunk_doc IF NOT EXISTS FOR (n:Chunk) ON (n.doc_id);
CREATE INDEX chunk_level IF NOT EXISTS FOR (n:Chunk) ON (n.level);
CREATE INDEX chunk_section IF NOT EXISTS FOR (n:Chunk) ON (n.doc_id, n.section);
CREATE INDEX chunk_inundation IF NOT EXISTS FOR (n:Chunk) ON (n.inundation_cm);
CREATE INDEX chunk_damage_status IF NOT EXISTS FOR (n:Chunk) ON (n.damage_status);
CREATE INDEX document_year IF NOT EXISTS FOR (n:Document) ON (n.year);
CREATE INDEX document_category IF NOT EXISTS FOR (n:Document) ON (n.category);
CREATE INDEX document_file_type IF NOT EXISTS FOR (n:Document) ON (n.file_type);
CREATE INDEX document_domain IF NOT EXISTS FOR (n:Document) ON (n.domain);
CREATE INDEX organization_level IF NOT EXISTS FOR (n:Organization) ON (n.level);
CREATE INDEX location_level IF NOT EXISTS FOR (n:Location) ON (n.level);
CREATE INDEX tag_kind IF NOT EXISTS FOR (n:Tag) ON (n.kind);
