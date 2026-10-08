// Full-text (Lucene)
CREATE FULLTEXT INDEX question_text_ft IF NOT EXISTS FOR (n:Question) ON EACH [n.text];
CREATE FULLTEXT INDEX chunk_text_ft IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text, n.breadcrumb];
CREATE FULLTEXT INDEX document_ft IF NOT EXISTS FOR (n:Document) ON EACH [n.title, n.description, n.tags_text];
CREATE FULLTEXT INDEX location_ft IF NOT EXISTS FOR (n:Location) ON EACH [n.name];
CREATE FULLTEXT INDEX organization_ft IF NOT EXISTS FOR (n:Organization) ON EACH [n.name];
