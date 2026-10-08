"""Hasilkan dataset seed 50-100 pasangan Q&A dari 3-5 dokumen terpilih (paling kaya metadata).
Jawaban diambil verbatim dari metadata terverifikasi (grounded), lengkap dengan sitasi (dokumen+bagian).
Keluaran: data/seed_qa.json dan data/seed_qa.csv  .
Pakai:  python -m scripts.generate_seed_qa"""
from __future__ import annotations
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kb.config import S  # noqa: E402
from kb.metadata import identity_text, load_docs  # noqa: E402


def richness(d):
    return len(d["steps"]) * 2 + len(d["refs"]) + len(d["partners"]) + bool(d["description"]) * 2 + bool(d["benefit"]) * 2


def qa_for(d):
    t, did, out = d["title"], d["doc_id"], []
    add = lambda cat, q, a, sec, item=None: out.append({"category": cat, "question": q, "answer": a, "cites": [{"doc_id": did, "section": sec, "item": item}]})
    if d["description"]:
        add("deskripsi", f'Apa deskripsi dokumen "{t}"?', d["description"], "deskripsi")
    if d["benefit"]:
        add("manfaat", f'Apa manfaat dokumen "{t}"?', d["benefit"], "manfaat")
    add("identitas", f'Siapa penyusun, tahun, dan jenis dokumen "{t}"?', identity_text(d), "identitas")
    if d["steps"]:
        add("proses", f'Bagaimana tahapan proses bisnis penyusunan "{t}"?', " ".join(f"{i}. {s}" for i, s in enumerate(d["steps"], 1)), "proses_bisnis")
        for i, s in enumerate(d["steps"][:6], 1):
            add("proses", f'Apa langkah ke-{i} dalam penyusunan "{t}"?', f"Langkah {i}: {s}", "proses_bisnis", i)
    regs = [r for r in d["refs"] if r["ref_type"] == "Regulasi"]
    sec = [r for r in d["refs"] if r["ref_type"] != "Regulasi"]
    if regs:
        add("regulasi", f'Regulasi apa saja yang menjadi landasan "{t}"?', "; ".join(r["title"] for r in regs[:12]), "regulasi")
    if sec:
        add("sumber", f'Sumber data apa yang digunakan "{t}"?', "; ".join(r["title"] for r in sec[:12]), "data_sekunder")
    if d["partners"]:
        add("mitra", f'Siapa saja mitra dalam penyusunan "{t}"?', "; ".join(f'{p["name"]} ({p["label"]})' for p in d["partners"][:15]), "mitra")
    if d["tags"]:
        add("tag", f'Apa kata kunci dokumen "{t}"?', ", ".join(d["tags"]), "tag")
    return out


def main():
    docs, seen, uniq = load_docs(S.metadata_json), set(), []
    for d in sorted(docs, key=richness, reverse=True):
        if d["title"] not in seen:
            seen.add(d["title"]); uniq.append(d)
    chosen, items = [], []
    for d in uniq:
        if len(chosen) >= 5 or len(items) >= 100:
            break
        qa = qa_for(d)
        if len(items) + len(qa) > 100:
            qa = qa[:100 - len(items)]
        chosen.append(d); items += qa
        if len(chosen) >= 3 and len(items) >= 50:
            break
    # pertanyaan lintas-dokumen: dokumen per unit kerja
    by_unit = defaultdict(list)
    for d in docs:
        by_unit[d["unit_kerja"]].append(d)
    for u, ds in by_unit.items():
        if u and len(ds) >= 2 and len(items) < 100:
            ds = ds[:6]
            items.append({"category": "lintas_dokumen", "question": f"Dokumen apa saja yang disusun oleh {u}?",
                          "answer": "; ".join(x["title"] for x in ds), "cites": [{"doc_id": x["doc_id"], "section": "identitas", "item": None} for x in ds]})
    for i, it in enumerate(items, 1):
        it.update(question_id=f"Q{i:03d}", status="draft", validated_by=None, source="metadata_bappenas")
    assert 50 <= len(items) <= 100, f"jumlah Q&A {len(items)} di luar 50-100"
    S.seed_json.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(S.seed_json.with_suffix(".csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "category", "question", "answer", "doc_id", "section", "status", "validated_by", "catatan_supervisor"])
        for it in items:
            w.writerow([it["question_id"], it["category"], it["question"], it["answer"], ";".join(c["doc_id"] for c in it["cites"]), it["cites"][0]["section"], "draft", "", ""])
    print(f"{len(items)} Q&A dari {len(chosen)} dokumen: {[d['doc_id'] for d in chosen]}")


if __name__ == "__main__":
    main()
