"""Orkestrasi retrieval GraphRAG ARCANA: pertanyaan -> rencana -> dokumen -> bagian graf -> (hibrida | ekspansi) -> jawaban terstruktur + sitasi.

Tangga fallback (tidak pernah berhenti di "tidak ditemukan"):
  1. Resolusi dokumen   : Lucene fuzzy (judul berbobot) -> CONTAINS -> katalog toleran-typo -> konteks percakapan (pertanyaan lanjutan)
  2. Ambil bagian graf  : Chunk.section sesuai intent (manfaat/regulasi/mitra/...) -- lookup langsung, bukan tebak-teks
  3. Tanpa dokumen jelas: Q&A seed (hanya bila konsisten) -> chunk hibrida (full-text fuzzy + vektor, RRF) -> entitas (Tag/Reference/Org) -> ekspansi 1-2 hop
  4. Terakhir            : saran dokumen/pertanyaan yang bisa diajukan (bukan pesan gagal)
"""
from __future__ import annotations
import re
from . import search
from .chunker import lead
from .query_plan import OVERVIEW_SECTIONS, QueryPlan, analyze, stem, terms
from .text import overlap

SECTION_LABEL = {"identitas": "Identitas dokumen", "deskripsi": "Deskripsi", "manfaat": "Manfaat", "proses_bisnis": "Proses bisnis penyusunan",
                 "regulasi": "Dasar hukum", "data_sekunder": "Sumber data / rujukan", "mitra": "Mitra dan kolaborasi", "tag": "Kata kunci"}
SEED_CAT_TO_INTENT = {"deskripsi": "deskripsi", "manfaat": "manfaat", "identitas": "identitas", "proses": "proses", "regulasi": "regulasi",
                      "sumber": "sumber_data", "mitra": "mitra", "tag": "tag"}


# ------------------------------------------------------------------ util teks
def strip_prefix(text: str, title: str) -> str:
    """Buang awalan template ('Manfaat dokumen "<judul>": ...') yang ditambahkan saat ingest; sisakan isinya."""
    t = " ".join((text or "").split())
    k = t.find(f'"{title}"')
    if 0 <= k <= 80:
        m = re.search(r":\s+", t[k + len(title) + 2:k + len(title) + 2 + 40])
        if m:
            return t[k + len(title) + 2 + m.end():].strip()
    return t


def sentences(text: str, min_len: int = 25) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])", " ".join((text or "").split())) if p.strip()]
    out: list[str] = []
    for p in parts:
        if out and len(p) < min_len:
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def best_passage(text: str, topic: list[str], n: int = 320) -> str:
    """Ambil kalimat (+ tetangganya) yang paling banyak memuat istilah pertanyaan, bukan sekadar awal paragraf."""
    ss = sentences(text, 1)
    if len(ss) <= 1 or not topic:
        return lead(text, n)
    qs = {stem(t) for t in topic if not t.isdigit()}
    sc = [sum(stem(w) in qs for w in terms(x)) for x in ss]
    i = max(range(len(ss)), key=lambda k: (sc[k], -k))
    out = ss[i]
    for j in (i + 1, i - 1):
        if len(out) < n * 0.6 and 0 <= j < len(ss):
            out = f"{out} {ss[j]}" if j > i else f"{ss[j]} {out}"
    return lead(out, n)


def bullets(items: list[str], cap: int | None = None, more: str = "lainnya") -> str:
    items = [i for i in items if i]
    shown = items[:cap] if cap else items
    s = "\n".join(f"- {i}" for i in shown)
    if cap and len(items) > cap:
        s += f"\n- _…dan {len(items) - cap} {more}_"
    return s


class CiteBook:
    """Penomoran sitasi [n] yang konsisten antara teks jawaban dan daftar sitasi."""

    def __init__(self):
        self.items: list[dict] = []
        self._idx: dict[str, int] = {}

    def add(self, ev: dict, snippet: str | None = None, score: float = 1.0, extra_ids: list[str] | None = None, section: str | None = None) -> str:
        cid = ev["chunk_id"]
        if cid not in self._idx:
            self.items.append({"doc_id": ev["doc_id"], "title": ev["title"], "chunk_id": cid,
                               "breadcrumb": ev.get("breadcrumb") or ev["title"], "page": ev.get("page"), "url": ev.get("url") or None,
                               "file_name": ev.get("file_name") or None, "section": section or ev.get("section"),
                               "snippet": snippet or lead(strip_prefix(ev["text"], ev["title"]), 300), "score": round(float(score), 3),
                               "chunk_ids": extra_ids or [cid], "text": strip_prefix(ev["text"], ev["title"])})
            self._idx[cid] = len(self.items)
        return f"[{self._idx[cid]}]"


# ------------------------------------------------------------------ render per-dokumen (ekstraktif, terstruktur)
def render_doc(plan: QueryPlan, doc: dict, ev: list[dict], prof: dict, cb: CiteBook, explicit: bool, with_header: bool = True) -> tuple[str, set[str]]:
    """Kembalikan (markdown, bagian-yang-tersedia). `explicit`=True bila pengguna meminta bagian tertentu (tampilkan lebih lengkap)."""
    by: dict[str, list[dict]] = {}
    for e in ev:
        by.setdefault(e["section"], []).append(e)
    title, out, have = doc["title"], [], set()
    if with_header:
        meta = " · ".join(x for x in [doc.get("output_type"), prof.get("unit") or doc.get("subcategory"), f'disusun {doc["year"]}' if doc.get("year") else ""] if x)
        out.append(f"### {title}" + (f"\n_{meta}_" if meta else ""))
    for sec in plan.sections:
        chunks = by.get(sec) or []
        if not chunks:
            continue
        have.add(sec)
        label = SECTION_LABEL[sec]
        texts = [strip_prefix(c["text"], title) for c in chunks]
        if sec == "identitas":
            rows = [("Jenis", " / ".join(x for x in [doc.get("output_type"), doc.get("knowledge_type")] if x)), ("Penyusun", prof.get("unit")),
                    ("Kedeputian/bidang", prof.get("division") or doc.get("category")), ("Tahun penyusunan", doc.get("year")),
                    ("Dipublikasikan", doc.get("publish_date")), ("Hak akses", doc.get("access_rights"))]
            body = bullets([f"**{k}**: {v}" for k, v in rows if v]) + f" {cb.add(chunks[0], section=sec)}"
        elif sec in ("deskripsi", "manfaat"):
            ss = sentences(texts[0])
            body = (bullets(ss, 8) if len(ss) > 1 else texts[0]) + f" {cb.add(chunks[0], section=sec)}"
        elif sec == "proses_bisnis":
            body = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1)) + f" {cb.add(chunks[0], snippet=lead('; '.join(texts), 300), extra_ids=[c['chunk_id'] for c in chunks], section=sec)}"
            label += f" ({len(texts)} langkah)"
        elif sec in ("regulasi", "data_sekunder"):
            texts = [re.sub(r"^(berlandaskan regulasi|menggunakan sumber data):\s*", "", t) for t in texts]
            body = bullets(texts, None if explicit else 6, "regulasi lainnya" if sec == "regulasi" else "sumber lainnya") + \
                f" {cb.add(chunks[0], snippet=lead('; '.join(texts), 300), extra_ids=[c['chunk_id'] for c in chunks], section=sec)}"
            label += f" ({len(texts)})"
        elif sec == "mitra":
            groups: dict[str, list[str]] = {}
            for p in prof.get("partner_details", []):
                groups.setdefault(p.get("label") or "Mitra", []).append(p["name"])
            if not groups:
                groups = {"Mitra": [re.sub(r"^.*?:\s*", "", t) for t in texts]}
            cap = 12 if explicit else 4
            if explicit:
                lines = [f"**{g}** ({len(n)})\n" + "\n".join(f"  - {x}" for x in n) for g, n in groups.items()]
            else:
                lines = [f"**{g}** ({len(n)}): " + "; ".join(n[:cap]) + (f"; _+{len(n) - cap} lainnya_" if len(n) > cap else "") for g, n in groups.items()]
            body = bullets(lines) + f" {cb.add(chunks[0], snippet=lead('; '.join(texts), 300), extra_ids=[c['chunk_id'] for c in chunks], section=sec)}"
        else:  # tag
            body = re.sub(r"^kata kunci dokumen .*?:\s*", "", texts[0], flags=re.I) + f" {cb.add(chunks[0], section=sec)}"
        m = re.search(r"\s(\[\d+\])$", body)
        if m:
            body, label = body[:m.start()], f"{label} {m.group(1)}"
        out.append(f"**{label}**\n{body}")
    return "\n\n".join(out), have


def source_line(doc: dict) -> str:
    bits = [f'*{doc["title"]}*']
    if doc.get("file_name"):
        bits.append(f'berkas `{doc["file_name"]}`')
    s = "**Sumber:** " + ", ".join(bits) + f' ({doc["doc_id"]})'
    return s + (f' — [Buka dokumen]({doc["url"]})' if doc.get("url") else "")


def followups(doc: dict, shown: set[str]) -> list[str]:
    t = doc["title"]
    pool = [("manfaat", f"Apa manfaat {t}?"), ("regulasi", f"Regulasi apa yang menjadi landasan {t}?"), ("mitra", f"Siapa saja mitra dalam penyusunan {t}?"),
            ("proses_bisnis", f"Bagaimana tahapan proses penyusunan {t}?"), ("data_sekunder", f"Sumber data apa yang digunakan {t}?"), ("tag", f"Apa kata kunci {t}?")]
    return [q for s, q in pool if s not in shown][:3]


# ------------------------------------------------------------------ pemilihan dokumen
def pick_resolved(plan: QueryPlan, cands: list[dict]) -> list[dict]:
    if not cands:
        return []
    qn = [t for t in plan.topic if not t.isdigit()]
    top = cands[0]
    unique = len(cands) == 1 or cands[1]["rank"] < top["rank"] - 0.08
    # 1 istilah saja (mis. "apa itu RPJMN") dianggap menyebut dokumen hanya bila jelas unik DAN pengguna meminta bagian tertentu
    confident = top["cover"] >= 0.6 and (len(qn) >= 2 or (top["cover"] >= 1.0 and unique and bool(plan.intents)))
    if not confident:
        return []
    return [c for c in cands if c["cover"] >= 0.6 and c["rank"] >= top["rank"] - 0.06][:3]


def _doc_brief(d: dict, cb: CiteBook | None = None) -> str:
    first = sentences(d.get("description") or d.get("benefit") or "")
    return f'**{d["title"]}**' + (f' — {lead(first[0], 180)}' if first else "")


def _expansion_block(exp: list[dict], limit: int = 5) -> str:
    if not exp:
        return ""
    lines = []
    for r in exp[:limit]:
        why = ", ".join(f'{s["kind"]} “{s["name"]}”' if s["kind"] != "Chunk" else f'isi mirip ({s["name"]})' for s in r["shared"][:3])
        lines.append(f'**{r["title"]}** ({r["doc_id"]}) — {r["hops"]}-hop via {why or r["via"]}')
    return "**Dokumen terkait (ditelusuri dari graf)**\n" + bullets(lines)


# ------------------------------------------------------------------ pipeline utama
def answer(db, question: str, top_k: int = 5, context_doc_ids: list[str] | None = None) -> dict:
    plan = analyze(question)
    trace: list[str] = []
    cb, res = CiteBook(), {"matched_question": None, "evidence": [], "suggestions": [], "context_doc_ids": []}

    cands, st = search.find_documents(db, plan) if plan.topic else ([], [])
    trace += st
    resolved = pick_resolved(plan, cands)
    if "daftar_dokumen" in plan.intents and not resolved:
        res.update(_list_documents(db, plan, cands, trace))
        res.update(citations=[], evidence=[], plan={"intents": plan.intents, "sections": [], "topic": plan.topic, "year": plan.year, "followup": False, "resolved": [], "trace": trace})
        return res
    ctx = [d for d in (context_doc_ids or [])]
    weak = not cands or cands[0]["cover"] < 0.4
    if ctx and (plan.followup or (weak and plan.intents)) and not resolved:
        resolved = search.docs_by_ids(db, ctx[:1])
        if resolved:
            trace.append("konteks_percakapan")
            for d in resolved:
                d.setdefault("cover", 1.0)

    # ---------- A. dokumen teridentifikasi -> ambil bagian graf secara langsung
    if resolved:
        plan.reintent(resolved[0]["title"])
        if not plan.sections:
            if "terkait" in plan.intents or "daftar_dokumen" in plan.intents:
                plan.sections = []
            else:
                plan.intents = ["ringkasan"]; plan.sections = list(OVERVIEW_SECTIONS)
        explicit = "ringkasan" not in plan.intents or plan.detail
        ids = [d["doc_id"] for d in resolved]
        ev = search.section_chunks(db, ids, plan.sections)
        profs = {p["doc_id"]: p for p in search.doc_entities(db, ids)}
        trace.append("section_chunks")
        blocks, shown, missing = [], set(), []
        with_ev = [d for d in resolved if any(e["doc_id"] == d["doc_id"] for e in ev)]
        if explicit and with_ev and len(with_ev) < len(resolved):  # dokumen serupa tanpa bagian yang diminta: ringkas saja
            skipped = [d["title"] for d in resolved if d not in with_ev]
            resolved = with_ev
            note_skipped = f'_{len(skipped)} dokumen serupa lain tidak mencatat bagian ini di katalog._'
        else:
            note_skipped = ""
        for d in resolved:
            d_ev = [e for e in ev if e["doc_id"] == d["doc_id"]]
            md, have = render_doc(plan, d, d_ev, profs.get(d["doc_id"], {}), cb, explicit, with_header=True)
            if "ringkasan" in plan.intents:
                body = search.body_chunks(db, [d["doc_id"]])
                if body:
                    trace.append("body_chunks")
                    md += "\n\n**Isi dokumen (bagian utama)**\n" + bullets([f'**{b["breadcrumb"].split(" > ")[-1]}** — {lead(b["text"].split(chr(10), 1)[-1], 220)} {cb.add(b)}' for b in body[:6]])
                    have.add("isi")
                elif not d.get("has_file"):
                    md += ("\n\n> ℹ️ Graf saat ini baru memuat **metadata katalog** dokumen ini; isi lengkap berkasnya (angka capaian, bab per bab) belum di-ingest. "
                           "Letakkan PDF di `data/documents/` lalu jalankan ulang ingest agar rincian isi ikut terjawab.")
            if md.strip():
                blocks.append(md)
            shown |= have
            miss = [SECTION_LABEL[s].lower() for s in plan.sections if s not in have and explicit]
            if miss:
                missing.append(f'**{d["title"]}**: {", ".join(miss)}')
        text = "\n\n---\n\n".join(blocks)
        if missing:
            text += ("\n\n" if text else "") + "_Tidak tercatat di katalog untuk_ " + "; ".join(missing) + "."
        if note_skipped:
            text += "\n\n" + note_skipped
        if not text:
            text = "\n\n".join(_doc_brief(d) for d in resolved)
        exp: list[dict] = []
        if "terkait" in plan.intents or not ev:
            exp = search.expand_graph(db, ids); trace.append("expand_graph")
            blk = _expansion_block(exp)
            text += ("\n\n" + blk) if blk else ""
        text += "\n\n" + "\n".join(source_line(d) for d in resolved)
        # konfirmasi dengan Q&A seed tervalidasi (hanya bila dokumen & jenis pertanyaan konsisten)
        for c in search.similar_questions(db, plan):
            if set(c.get("doc_ids", [])) & set(ids) and SEED_CAT_TO_INTENT.get(c.get("category")) in plan.intents and overlap(question, c["question"]) >= 0.4:
                res["matched_question"] = {"question_id": c["question_id"], "question": c["question"], "similarity": round(overlap(question, c["question"]), 3), "status": c.get("status")}
                trace.append("seed_qa_konfirmasi"); break
        res["suggestions"] = followups(resolved[0], shown)
        res.update(answer=text, source="graph_sections", context_doc_ids=ids, expansion=exp)
    else:
        res.update(_open_question(db, plan, cands, cb, top_k, trace, question))

    cites = cb.items[:max(top_k + 6, 12)]
    res.update(citations=[{k: v for k, v in c.items() if k != "text"} for c in cites], evidence=[{"n": i, "title": c["title"], "section": c.get("section"), "text": c["text"][:900]} for i, c in enumerate(cites, 1)],
               plan={"intents": plan.intents, "sections": plan.sections, "topic": plan.topic, "year": plan.year, "followup": plan.followup,
                     "resolved": [d["doc_id"] for d in resolved], "trace": trace})
    return res


def _open_question(db, plan: QueryPlan, cands: list[dict], cb: CiteBook, top_k: int, trace: list[str], question: str) -> dict:
    """Tidak ada dokumen yang jelas dituju: Q&A seed konsisten -> chunk hibrida -> entitas -> ekspansi -> saran."""
    out = {"source": "none", "context_doc_ids": []}
    # 1) Q&A seed hanya bila sangat mirip (dan bukan sekadar kebetulan berbagi kata judul)
    best = None
    for c in search.similar_questions(db, plan):
        sc = overlap(question, c["question"])
        if sc >= 0.55 and (best is None or sc > best[0]):
            best = (sc, c)
    if best:
        sc, c = best
        srcs = search.answer_sources(db, c["question_id"], top_k)
        body = c["answer"]
        ss = [s.strip() for s in re.split(r";\s+", body) if s.strip()]
        text = bullets(ss, 10) if len(ss) > 2 else body
        text += " " + "".join(cb.add(s, score=sc) for s in srcs[:2])
        trace.append("seed_qa")
        out.update(source="seed_qa", answer=text, matched_question={"question_id": c["question_id"], "question": c["question"], "similarity": round(sc, 3), "status": c.get("status")},
                   context_doc_ids=list(dict.fromkeys(s["doc_id"] for s in srcs))[:3])
        return out
    # 2) chunk hibrida
    hits, st = search.search_chunks(db, plan, top_k, [d["doc_id"] for d in cands[:3]] if cands else None)
    trace += st
    if hits:
        lines, ids = [], list(dict.fromkeys(h["doc_id"] for h in hits))
        for h in hits:
            psg = best_passage(strip_prefix(h["text"], h["title"]), plan.topic)
            lines.append(f'{psg} {cb.add(h, snippet=psg, score=h.get("rank", 0))} — _{h["title"]}_')
        text = "Berikut bagian dokumen yang paling relevan dengan pertanyaan Anda:\n" + bullets(lines)
        exp = search.expand_graph(db, ids[:2]) if len(hits) < 3 else []
        if exp:
            trace.append("expand_graph"); text += "\n\n" + _expansion_block(exp)
        out.update(source="chunks", answer=text, context_doc_ids=ids[:3], expansion=exp, suggestions=[f"Jelaskan isi {hits[0]['title']}"])
        return out
    # 3) entitas (tag/regulasi/organisasi) -> dokumen terhubung
    ents = search.entity_docs(db, plan)
    if ents:
        trace.append("entity_docs")
        by: dict[str, dict] = {}
        for e in ents:
            by.setdefault(e["doc_id"], {"title": e["title"], "via": []})["via"].append(f'{e["kind"]} “{e["entity"]}”')
        ids = list(by)[:6]
        text = "Pertanyaan Anda terkait entitas berikut, dan ini dokumen yang menyebutnya:\n" + bullets([f'**{v["title"]}** ({i}) — {", ".join(dict.fromkeys(v["via"]))}' for i, v in list(by.items())[:6]])
        exp = search.expand_graph(db, ids[:2]); trace.append("expand_graph")
        text += ("\n\n" + _expansion_block(exp)) if exp else ""
        out.update(source="graph_entity", answer=text, context_doc_ids=ids[:3], expansion=exp, suggestions=[f"Jelaskan isi {by[ids[0]]['title']}"])
        return out
    # 4) kandidat dokumen yang mendekati (hanya yang punya kecocokan istilah nyata)
    cands = [d for d in cands if d["cover"] >= 0.34]
    if cands:
        trace.append("kandidat_dokumen")
        text = "Saya belum menemukan jawaban yang persis, tetapi dokumen berikut paling mendekati pertanyaan Anda:\n" + bullets([_doc_brief(d) + f' ({d["doc_id"]})' for d in cands[:4]])
        exp = search.expand_graph(db, [cands[0]["doc_id"]]); trace.append("expand_graph")
        text += ("\n\n" + _expansion_block(exp)) if exp else ""
        out.update(source="graph_expansion", answer=text, context_doc_ids=[cands[0]["doc_id"]], expansion=exp, suggestions=[f"Jelaskan isi {cands[0]['title']}"])
        return out
    # 5) terakhir: saran konkret, bukan pesan gagal
    cat = search.doc_catalog(db)
    ex = [d["title"] for d in cat[:4]]
    trace.append("saran")
    text = "Saya belum menemukan topik tersebut di graf pengetahuan. Coba sebutkan judul atau topik dokumen, misalnya:\n" + bullets(ex) if ex else \
        "Graf pengetahuan belum berisi dokumen yang dapat dicocokkan. Pastikan ingest sudah dijalankan."
    out.update(source="none", answer=text, suggestions=[f"Jelaskan isi {t}" for t in ex[:3]])
    return out


def _list_documents(db, plan: QueryPlan, cands: list[dict], trace: list[str]) -> dict:
    """'Dokumen apa saja yang disusun <unit>/membahas <topik>?' -> telusuri entitas (Organization/Tag/Reference) lalu dokumen yang terhubung."""
    by: dict[str, dict] = {}
    for e in search.entity_docs(db, plan, 30):
        by.setdefault(e["doc_id"], {"title": e["title"], "via": []})["via"].append(f'{e["kind"]} “{e["entity"]}”' + (f' ({e["role"]})' if e.get("role") else ""))
    trace.append("entity_docs")
    for d in cands:
        if d["cover"] >= 0.5:
            by.setdefault(d["doc_id"], {"title": d["title"], "via": []})["via"].append("judul/tag cocok")
    if not by:
        return _open_question(db, plan, cands, CiteBook(), 5, trace, plan.raw)
    items = [f'**{v["title"]}** ({i}) — {", ".join(dict.fromkeys(v["via"]))}' for i, v in list(by.items())[:15]]
    return {"source": "graph_entity", "answer": f"Ditemukan {len(by)} dokumen yang terkait:\n" + bullets(items), "context_doc_ids": list(by)[:1], "suggestions": [f"Jelaskan isi {list(by.values())[0]['title']}"], "expansion": []}
