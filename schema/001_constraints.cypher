// ARCANA UNIFIED GENERIC SCHEMA - identik untuk Bappenas & Bencana. Hanya 11 label sah (lihat kb/ontology.py).
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.doc_id IS UNIQUE;
CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE;
CREATE CONSTRAINT category_name IF NOT EXISTS FOR (n:Category) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT subcategory_name IF NOT EXISTS FOR (n:SubCategory) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT tag_name IF NOT EXISTS FOR (n:Tag) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT org_id IF NOT EXISTS FOR (n:Organization) REQUIRE n.org_id IS UNIQUE;
CREATE CONSTRAINT location_name IF NOT EXISTS FOR (n:Location) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT step_id IF NOT EXISTS FOR (n:ProcessStep) REQUIRE n.step_id IS UNIQUE;
CREATE CONSTRAINT question_id IF NOT EXISTS FOR (n:Question) REQUIRE n.question_id IS UNIQUE;
CREATE CONSTRAINT answer_id IF NOT EXISTS FOR (n:Answer) REQUIRE n.answer_id IS UNIQUE;
CREATE CONSTRAINT reference_id IF NOT EXISTS FOR (n:Reference) REQUIRE n.ref_id IS UNIQUE;
