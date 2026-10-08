"""Tes skema terpadu: semua Cypher loader hanya memakai 11 label & 11 relasi, untuk domain mana pun."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
from kb import ingest, ontology
from kb.config import S
from kb.metadata import load_docs


class Rec:
    def __init__(self): self.calls = []
    def write(self, q, **p): self.calls.append(q); return []
    def read(self, q, **p): return []
    def write_many(self, stmts): self.calls += [q for q, _ in stmts]


def test_loader_uses_only_unified_schema():
    docs = load_docs(S.metadata_json)
    rec = Rec()
    for d in docs:
        ingest.ingest_document(rec, d)
    labels, rels = set(), set()
    for q in rec.calls:
        ontology.check(q)
        labels |= {l for m in ontology._LAB.finditer(q) for l in __import__("re").split(r"\s*[:|]\s*", m.group(1)) if l}
        rels |= {r for m in ontology._REL.finditer(q) for r in __import__("re").split(r"\s*\|\s*:?", m.group(1)) if r}
    assert labels <= set(ontology.ALLOWED_LABELS) and rels <= set(ontology.ALLOWED_RELS)
    assert {"Document", "Chunk", "Organization", "Category", "SubCategory", "Tag", "Location"} <= labels
    assert {"CONTAINS_CHUNK", "SUB_CHUNK_OF", "BELONGS_TO_ORG", "IN_CATEGORY", "TAGGED_WITH", "LOCATED_IN"} <= rels


def test_to_generic_has_no_domain_labels_and_keeps_properties():
    for d in load_docs(S.metadata_json):
        g = ontology.to_generic(d)
        assert g["orgs"] and g["doc_orgs"][0]["role"] == "penerbit"
        assert all(o["org_id"] for o in g["orgs"])
        assert {t[1] for t in g["tags"]} <= {"kata_kunci", "infrastruktur"}


def test_check_rejects_domain_labels_and_rels():
    for bad in ("MATCH (n:UnitKerja) RETURN n", "MATCH (n:Document) SET n:DamageReport", "MATCH ()-[:NEXT_CHUNK]->() RETURN 1", "MERGE (y:Year {value:1})"):
        with pytest.raises(ValueError):
            ontology.check(bad)


def test_sanitize_llm_output():
    out = ontology.sanitize({"nodes": [{"id": "1", "label": "UnitKerja", "properties": {"name": "Dit X"}}, {"id": "2", "label": "DisasterType", "properties": {"name": "Banjir"}},
                                       {"id": "3", "label": "Year", "properties": {"value": 2024}}, {"id": "4", "label": "Document"}, {"id": "5", "label": "Category"}],
                             "relationships": [{"source": "4", "type": "PRODUCED_BY", "target": "1"}, {"source": "4", "type": "FOR_YEAR", "target": "3"},
                                               {"source": "2", "type": "SUBCATEGORY_OF", "target": "5"}, {"source": "4", "type": "COVERS_DISASTER", "target": "2"}]})
    assert [n["label"] for n in out["nodes"]] == ["Organization", "SubCategory", "Document", "Category"]
    assert {(r["type"]) for r in out["relationships"]} == {"BELONGS_TO_ORG", "SUBCATEGORY_OF", "IN_CATEGORY"}
