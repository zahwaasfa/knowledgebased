"""Lapisan kueri graf (Neo4j) untuk skema terpadu: dokumen, chunk per-bagian, full-text fuzzy, vektor, ekspansi 1-2 hop.

Semua Cypher hanya memakai label/relasi sah (lihat ontology.ALLOWED_*). Setiap pemanggilan index dibungkus `_safe`
sehingga index yang belum ada / salah ketik tidak menjatuhkan API (hasil kosong + log), dan `_ft` otomatis mencoba
index berikutnya (mis. *_idn lalu *_ft lama).
"""
from __future__ import annotations
import difflib
import logging
import re
import time
from .config import S
from .db import DB
from .query_plan import fold, stem, terms

log = logging.getLogger("kb.search")

# ---------------------------------------------------------------- full-text helper
FT_INDEXES = {
    "chunk": ["chunk_text_idn", "chunk_text_ft"],
    "document": ["document_idn", "document_ft"],
    "question": ["question_text_idn", "question_text_ft"],
    "answer": ["answer_text_idn"],
    "tag": ["tag_idn"],
    "reference": ["reference_idn"],
    "organization": ["organization_ft"],
}
_dead: set[str] = set()


def lucene(ts: list[str], fuzzy: bool = True, field: str | None = None, max_terms: int = 12) -> str:
    """Query Lucene aman & toleran: tiap istilah = exact^2 OR fuzzy (~1 untuk >=5 huruf, ~2 untuk >=9) OR prefiks (stem*)."""
    parts = []
    for t in ts[:max_terms]:
        t = re.sub(r"[^a-z0-9]", "", t)
        if not t:
            continue
        alts = [f"{t}^2"]
        if fuzzy and len(t) >= 5:
            alts.append(f"{t}~{2 if len(t) >= 9 else 1}")
        st = stem(t)
        if fuzzy and len(st) >= 4:
            alts.append(f"{st}*")
        parts.append("(" + " OR ".join(alts) + ")")
    q = " OR ".join(parts)
    return f"{field}:({q})" if field and q else q


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        log.warning("query graf gagal (diabaikan, memakai fallback): %s", str(e)[:200])
        return default if default is not None else []


def _ft(db: DB, kind: str, cypher_after_call: str, q: str, **params) -> list[dict]:
    """Jalankan `CALL db.index.fulltext.queryNodes($index,$q) YIELD node, score` + cypher_after_call pada index pertama yang hidup."""
    if not q:
        return []
    for idx in FT_INDEXES[kind]:
        if idx in _dead:
            continue
        try:
            return db.read(f"CALL db.index.fulltext.queryNodes($index, $q) YIELD node, score\n{cypher_after_call}", index=idx, q=q, **params)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "index" in msg.lower() and ("not found" in msg.lower() or "no such" in msg.lower() or "does not exist" in msg.lower()):
                _dead.add(idx); log.warning("index %s tidak ada, coba berikutnya", idx)
                continue
            log.warning("fulltext %s gagal: %s", idx, msg[:200])
            return []
    return []


# ---------------------------------------------------------------- DOKUMEN
DOC_COLS = """d.doc_id AS doc_id, d.title AS title, d.year AS year, d.description AS description, d.benefit AS benefit,
       d.document_url AS url, d.file_name AS file_name, coalesce(d.has_physical_file,false) AS has_file, d.category AS category,
       d.subcategory AS subcategory, d.output_type AS output_type, d.knowledge_type AS knowledge_type, d.access_rights AS access_rights,
       toString(d.publish_date) AS publish_date, coalesce(d.tags_text,'') AS tags_text"""

DOC_FT = f"WITH node AS d, score ORDER BY score DESC LIMIT $limit RETURN {DOC_COLS}, score"
DOC_CATALOG = f"MATCH (d:Document) RETURN {DOC_COLS} LIMIT $limit"
DOC_BY_IDS = f"MATCH (d:Document) WHERE d.doc_id IN $ids RETURN {DOC_COLS}"
DOC_LEXICAL = f"""
MATCH (d:Document)
WITH d, [t IN $terms WHERE toLower(d.title) CONTAINS t] AS ht,
        [t IN $terms WHERE toLower(coalesce(d.tags_text,'') + ' ' + coalesce(d.subcategory,'') + ' ' + coalesce(d.description,'')) CONTAINS t] AS ho
WHERE size(ht) > 0 OR size(ho) > 0
RETURN {DOC_COLS}, toFloat(size(ht) * 2 + size(ho)) AS score ORDER BY score DESC LIMIT $limit"""

_catalog: dict = {"t": 0.0, "rows": []}


def doc_catalog(db: DB, ttl: int = 600) -> list[dict]:
    """Katalog ringan seluruh dokumen (di-cache) -> pencocokan judul toleran-typo di Python; menjamin 'tidak pernah kosong'."""
    if time.time() - _catalog["t"] > ttl or not _catalog["rows"]:
        _catalog.update(t=time.time(), rows=_safe(lambda: db.read(DOC_CATALOG, limit=5000)))
    return _catalog["rows"]


def docs_by_ids(db: DB, ids: list[str]) -> list[dict]:
    rows = _safe(lambda: db.read(DOC_BY_IDS, ids=ids)) if ids else []
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(r["doc_id"], 99))


def _tok_match(qs: set[str], ts: set[str], fuzzy_cut: float = 0.84) -> float:
    """Jumlah istilah query yang ada di himpunan token (exact/stem = 1, mirip huruf (typo) = 0.8)."""
    hit = 0.0
    for q in qs:
        if q in ts:
            hit += 1
        else:
            best = max((difflib.SequenceMatcher(None, q, t).ratio() for t in ts if abs(len(t) - len(q)) <= 3), default=0)
            if len(q) >= 5 and best >= fuzzy_cut:
                hit += 0.8
    return hit


def rank_documents(plan, rows: list[dict]) -> list[dict]:
    """Beri skor tiap kandidat: cakupan istilah topik pada JUDUL (utama), pada tag/deskripsi (pelengkap), tahun, skor Lucene (pemecah seri)."""
    q = plan.topic_stems
    qn = {t for t in q if not t.isdigit()}
    mx = max((r.get("score") or 0 for r in rows), default=0) or 1.0
    out = []
    for r in rows:
        tt = {stem(t) for t in terms(r["title"])}
        other = {stem(t) for t in terms(f'{r.get("tags_text","")} {r.get("subcategory") or ""} {(r.get("description") or "")[:400]}')}
        cov = _tok_match(qn, tt) / len(qn) if qn else 0.0
        cov2 = _tok_match(qn - tt, other) / len(qn) if qn else 0.0
        prec = len(qn & tt) / max(len(tt), 1)
        s = 0.62 * cov + 0.12 * cov2 + 0.12 * prec + 0.06 * ((r.get("score") or 0) / mx)
        if plan.year:
            s += 0.12 if plan.year in tt else (0.04 if str(r.get("year")) == plan.year else -0.12)
        out.append({**r, "cover": round(cov, 3), "rank": round(s, 4)})
    return sorted(out, key=lambda x: x["rank"], reverse=True)


def find_documents(db: DB, plan, limit: int = 8) -> tuple[list[dict], list[str]]:
    """Cari kandidat dokumen: Lucene fuzzy (judul berbobot) -> fallback CONTAINS -> katalog Python toleran-typo. Mengembalikan (ranked, tahapan)."""
    stages, rows = [], {}
    ts = [t for t in plan.topic if t]
    if not ts:
        return [], stages
    q = lucene(ts, field="title") + " OR " + lucene(ts)
    for r in _ft(db, "document", DOC_FT, q, limit=30):
        rows[r["doc_id"]] = r
    if rows:
        stages.append("document_ft(fuzzy)")
    if len(rows) < 3:
        for r in _safe(lambda: db.read(DOC_LEXICAL, terms=ts, limit=30)):
            rows.setdefault(r["doc_id"], r)
        stages.append("document_contains")
    cat = doc_catalog(db)
    if cat:
        qn = {stem(t) for t in ts if not t.isdigit()}
        for r in cat:
            if r["doc_id"] in rows:
                continue
            tt = {stem(t) for t in terms(r["title"])}
            if qn and _tok_match(qn, tt) / len(qn) >= 0.5:
                rows[r["doc_id"]] = {**r, "score": 0.0}
        stages.append("katalog_typo")
    return rank_documents(plan, list(rows.values()))[:limit], stages


# ---------------------------------------------------------------- CHUNK
CHUNK_COLS = """c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.section AS section, c.item_no AS item_no, c.text AS text, c.level AS level,
       c.is_leaf AS is_leaf, c.breadcrumb AS breadcrumb, c.page_number AS page, c.chunk_index AS chunk_index,
       d.title AS title, d.document_url AS url, d.file_name AS file_name"""

SECTION_CHUNKS = f"""
MATCH (c:Chunk) WHERE c.doc_id IN $ids AND c.section IN $sections
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN {CHUNK_COLS}
ORDER BY c.doc_id, c.section, coalesce(c.item_no, 0), c.chunk_index"""

# ringkasan isi berkas fisik (bagian "Isi Dokumen: <file>") level atas; kosong bila dokumen hanya punya metadata
BODY_CHUNKS = f"""
MATCH (c:Chunk) WHERE c.doc_id IN $ids AND c.section IS NULL AND c.breadcrumb CONTAINS 'Isi Dokumen' AND c.level <= $maxlevel
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN {CHUNK_COLS}
ORDER BY c.doc_id, c.level, c.chunk_index LIMIT $limit"""

CHUNK_FT = f"""
WITH node AS c, score ORDER BY score DESC LIMIT $limit
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN {CHUNK_COLS}, score"""

CHUNK_VEC = f"""
CALL db.index.vector.queryNodes('chunk_embedding', $limit, $vec) YIELD node AS c, score
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN {CHUNK_COLS}, score"""

# fallback leksikal terarah: hanya pada dokumen terpilih (pakai index chunk_doc), tanpa bergantung pada full-text
CHUNK_LEXICAL = f"""
MATCH (c:Chunk) WHERE c.doc_id IN $ids
WITH c, [t IN $terms WHERE toLower(c.text) CONTAINS t] AS hit WHERE size(hit) > 0
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN {CHUNK_COLS}, toFloat(size(hit)) AS score ORDER BY score DESC LIMIT $limit"""


def section_chunks(db: DB, doc_ids: list[str], sections: list[str]) -> list[dict]:
    return _safe(lambda: db.read(SECTION_CHUNKS, ids=doc_ids, sections=sections)) if doc_ids and sections else []


def body_chunks(db: DB, doc_ids: list[str], maxlevel: int = 2, limit: int = 8) -> list[dict]:
    return _safe(lambda: db.read(BODY_CHUNKS, ids=doc_ids, maxlevel=maxlevel, limit=limit)) if doc_ids else []


def rrf(lists: list[list[dict]], key: str = "chunk_id", k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: gabungkan peringkat full-text & vektor tanpa perlu menyamakan skala skor."""
    acc: dict = {}
    for lst in lists:
        for rank, r in enumerate(lst):
            e = acc.setdefault(r[key], {**r, "rrf": 0.0})
            e["rrf"] += 1.0 / (k + rank + 1)
    return sorted(acc.values(), key=lambda x: x["rrf"], reverse=True)


def search_chunks(db: DB, plan, top_k: int = 6, doc_ids: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Hibrida: full-text fuzzy + (opsional) vektor, difusi RRF, bonus bila di dokumen terpilih; fallback leksikal terarah."""
    stages, lists = [], []
    ts = [t for t in plan.topic if not t.isdigit()] or plan.topic
    q = lucene(ts)
    ft = _ft(db, "chunk", CHUNK_FT, q, limit=max(top_k * 8, 40))
    if ft:
        lists.append(ft); stages.append("chunk_ft(fuzzy)")
    if S.embeddings:
        from .embeddings import embed
        v = embed([plan.raw])
        if v:
            vec = _safe(lambda: db.read(CHUNK_VEC, vec=v[0], limit=max(top_k * 4, 20)))
            if vec:
                lists.append(vec); stages.append("chunk_vector")
    fused = rrf(lists) if lists else []
    if doc_ids and len(fused) < top_k:
        lex = _safe(lambda: db.read(CHUNK_LEXICAL, ids=doc_ids, terms=ts, limit=top_k * 4))
        if lex:
            fused = rrf([fused, lex]) if fused else lex
            stages.append("chunk_lexical(doc)")
    qn = {stem(t) for t in ts if not t.isdigit()}
    if qn:  # gerbang relevansi: kecocokan fuzzy Lucene yang 'kebetulan' (mis. 'resep' ~ 'resmi') tidak boleh tampil sebagai jawaban
        for r in fused:
            toks = {stem(t) for t in terms(f'{r.get("breadcrumb") or ""} {r["text"]}')}
            r["cov"] = _tok_match(qn, toks) / len(qn)
        fused = [r for r in fused if r["cov"] >= 0.5]
    pref = set(doc_ids or [])
    for r in fused:
        r["rank"] = (r.get("rrf", 0.0) + (0.02 if r["doc_id"] in pref else 0) + (0.002 if r.get("is_leaf") else 0)) * (0.6 if r.get("section") == "identitas" else 1.0)
    fused.sort(key=lambda x: x["rank"], reverse=True)
    best, per_doc = [], {}
    for r in fused:
        if per_doc.get(r["doc_id"], 0) >= 3:
            continue
        per_doc[r["doc_id"]] = per_doc.get(r["doc_id"], 0) + 1
        best.append(r)
        if len(best) >= top_k:
            break
    return best, stages


# ---------------------------------------------------------------- SEED Q&A
SIMILAR_Q = """
WITH node AS q, score ORDER BY score DESC LIMIT $limit
MATCH (q)-[:ANSWERED_BY]->(a:Answer)
OPTIONAL MATCH (q)-[:ASKED_ABOUT]->(d:Document)
RETURN q.question_id AS question_id, q.text AS question, a.text AS answer, q.status AS status, q.category AS category,
       collect(DISTINCT d.doc_id) AS doc_ids, score"""

ANSWER_SOURCES = f"""
MATCH (q:Question {{question_id:$qid}})-[:ANSWERED_BY]->(a:Answer)
MATCH (c:Chunk) WHERE c.chunk_id IN coalesce(a.cited_chunk_ids, []) OR (q)-[:ASKED_ABOUT]->(c)
MATCH (d:Document {{doc_id:c.doc_id}})
RETURN DISTINCT {CHUNK_COLS} ORDER BY doc_id, chunk_index LIMIT $limit"""


def similar_questions(db: DB, plan, limit: int = 6) -> list[dict]:
    return _ft(db, "question", SIMILAR_Q, lucene(plan.topic + [i for i in plan.intents if i in ("manfaat", "regulasi")]), limit=limit)


def answer_sources(db: DB, qid: str, limit: int = 8) -> list[dict]:
    return _safe(lambda: db.read(ANSWER_SOURCES, qid=qid, limit=limit))


# ---------------------------------------------------------------- ENTITAS & EKSPANSI GRAF (1-2 hop)
DOC_ENTITIES = """
MATCH (d:Document) WHERE d.doc_id IN $ids
RETURN d.doc_id AS doc_id, d.title AS title, d.year AS year,
  head([(d)-[b:BELONGS_TO_ORG]->(o:Organization) WHERE b.role = 'penyusun_utama' | o.name]) AS unit,
  head([(d)-[b:BELONGS_TO_ORG]->(o:Organization) WHERE b.role = 'kedeputian' | o.name]) AS division,
  head([(d)-[:IN_CATEGORY]->(c:Category) | c.name]) AS category,
  [(d)-[:IN_CATEGORY]->(s:SubCategory) | s.name] AS subcategories,
  [(d)-[:TAGGED_WITH]->(t:Tag) | t.name] AS tags,
  [(d)-[r:TAGGED_WITH]->(x:Reference) | {id: x.ref_id, title: x.title, type: x.ref_type, role: r.role}] AS refs,
  [(d)-[b:BELONGS_TO_ORG]->(o:Organization) WHERE b.role IN ['mitra_internal', 'mitra_eksternal'] | {name: o.name, role: b.role, label: b.detail}] AS partner_details"""

# 1 hop: dokumen lain yang berbagi entitas (Tag / Reference / Organization / Category / Location), dibobot 1/log(derajat) agar hub (mis. Bappenas) tak mendominasi
EXPAND_ENTITY_HOP = """
MATCH (d:Document) WHERE d.doc_id IN $ids
MATCH (d)-[r1:TAGGED_WITH|IN_CATEGORY|BELONGS_TO_ORG|LOCATED_IN]->(x)<-[r2:TAGGED_WITH|IN_CATEGORY|BELONGS_TO_ORG|LOCATED_IN]-(o:Document)
WHERE NOT o.doc_id IN $ids AND NOT (x:Organization AND x.level = 'instansi') AND NOT (x:Location AND x.name = 'Nasional')
WITH o, x, r1, 1.0 / log(2.0 + COUNT { (x)<--(:Document) }) AS w
WITH o, collect(DISTINCT {kind: labels(x)[0], name: coalesce(x.name, x.title), rel: type(r1)}) AS shared, sum(w) AS score
RETURN o.doc_id AS doc_id, o.title AS title, 1 AS hops, 'entitas_bersama' AS via, shared[..5] AS shared, score
ORDER BY score DESC LIMIT $limit"""

# lintas dokumen via kemiripan chunk (REFERENCES_CHUNK: semantic_similarity | policy_evidence)
EXPAND_CHUNK_HOP = """
MATCH (c:Chunk)-[r:REFERENCES_CHUNK]-(c2:Chunk) WHERE c.doc_id IN $ids AND c2.doc_id <> c.doc_id AND NOT c2.doc_id IN $ids
MATCH (o:Document {doc_id: c2.doc_id})
WITH o, max(r.similarity) AS sim, collect(DISTINCT r.type)[..2] AS types, collect(DISTINCT c2.chunk_id)[..3] AS chunk_ids
RETURN o.doc_id AS doc_id, o.title AS title, 1 AS hops, 'kemiripan_chunk' AS via,
       [t IN types | {kind: 'Chunk', name: t, rel: 'REFERENCES_CHUNK'}] AS shared, sim AS score, chunk_ids
ORDER BY sim DESC LIMIT $limit"""

# 2 hop: dokumen -> tag -> dokumen tetangga -> tag lain (topik yang 'bertetangga'); dipakai bila 1 hop miskin hasil
EXPAND_TWO_HOP = """
MATCH (d:Document) WHERE d.doc_id IN $ids
MATCH (d)-[:TAGGED_WITH|IN_CATEGORY]->(x1)<-[:TAGGED_WITH|IN_CATEGORY]-(m:Document)-[:TAGGED_WITH|IN_CATEGORY]->(x2)<-[:TAGGED_WITH|IN_CATEGORY]-(o:Document)
WHERE NOT o.doc_id IN $ids AND m <> o AND m <> d AND NOT (x1:Organization) AND NOT (x2:Organization) AND NOT (x1:Location) AND NOT (x2:Location)
WITH o, collect(DISTINCT m.title)[..2] AS lewat, count(DISTINCT x2) AS n
RETURN o.doc_id AS doc_id, o.title AS title, 2 AS hops, 'dua_hop' AS via,
       [t IN lewat | {kind: 'Document', name: t, rel: 'via'}] AS shared, toFloat(n) / 10.0 AS score
ORDER BY score DESC LIMIT $limit"""

ENTITY_DOCS = """
WITH node, score ORDER BY score DESC LIMIT $limit
MATCH (d:Document)-[r:TAGGED_WITH|BELONGS_TO_ORG|IN_CATEGORY|LOCATED_IN]->(node)
RETURN labels(node)[0] AS kind, coalesce(node.name, node.title) AS entity, type(r) AS rel, r.role AS role,
       d.doc_id AS doc_id, d.title AS title, score ORDER BY score DESC LIMIT $limit"""

BY_TOPIC = """
MATCH (t:Tag) WHERE toLower(t.name) CONTAINS toLower($topic)
MATCH (d:Document)-[r:TAGGED_WITH]->(t)
RETURN t.name AS tag, d.doc_id AS doc_id, d.title AS title, d.year AS year, r.frequency AS frequency
ORDER BY frequency DESC LIMIT $limit"""


def doc_entities(db: DB, ids: list[str]) -> list[dict]:
    rows = _safe(lambda: db.read(DOC_ENTITIES, ids=ids)) if ids else []
    for r in rows:  # kompatibel dengan format lama (daftar nama mitra)
        r["partners"] = list(dict.fromkeys(p["name"] for p in r.get("partner_details", [])))
        r["refs"] = [x for x in r.get("refs", []) if x.get("id")]
    return rows


def expand_graph(db: DB, doc_ids: list[str], limit: int = 6, two_hop: bool = True) -> list[dict]:
    """Ekspansi 1-2 hop dari dokumen/chunk terpilih -> dokumen terkait + ALASAN keterkaitan (entitas/kemiripan yang dibagi)."""
    if not doc_ids:
        return []
    found: dict[str, dict] = {}
    for q in (EXPAND_ENTITY_HOP, EXPAND_CHUNK_HOP) + ((EXPAND_TWO_HOP,) if two_hop else ()):
        if q is EXPAND_TWO_HOP and len(found) >= limit:
            break
        for r in _safe(lambda q=q: db.read(q, ids=doc_ids, limit=limit)):
            if r["doc_id"] in found:
                found[r["doc_id"]]["shared"] = (found[r["doc_id"]]["shared"] + r["shared"])[:6]
                found[r["doc_id"]]["score"] += float(r["score"] or 0)
            else:
                found[r["doc_id"]] = {**r, "score": float(r["score"] or 0)}
    return sorted(found.values(), key=lambda x: (x["hops"] > 1, -x["score"]))[:limit]


def related_docs(db: DB, doc_id: str, limit: int = 5) -> list[dict]:
    """Kompatibel dengan format lama {doc_id,title,shared,n}; kini memakai ekspansi graf skema terpadu."""
    out = []
    for r in expand_graph(db, [doc_id], limit):
        out.append({"doc_id": r["doc_id"], "title": r["title"], "shared": [s["name"] for s in r["shared"]][:5], "n": len(r["shared"]), "hops": r["hops"], "via": r["via"]})
    return out


def entity_docs(db: DB, plan, limit: int = 12) -> list[dict]:
    """Pertanyaan menyebut entitas (tag/regulasi/organisasi) bukan judul -> temukan entitas lalu dokumen yang terhubung."""
    q, out = lucene(plan.topic, fuzzy=True), []
    for kind in ("tag", "reference", "organization"):
        out += _ft(db, kind, ENTITY_DOCS, q, limit=limit)
    out.sort(key=lambda r: r["score"], reverse=True)
    top = out[0]["score"] if out else 0
    return [r for r in out if r["score"] >= 0.5 * top][:limit * 2]  # buang entitas yang hanya 'mirip sebagian'; sisakan yang sekelas skor tertinggi


def by_topic(db: DB, topic: str, limit: int = 10) -> list[dict]:
    return _safe(lambda: db.read(BY_TOPIC, topic=topic, limit=limit))
