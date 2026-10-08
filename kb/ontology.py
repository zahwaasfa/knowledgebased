"""ONTOLOGI GENERIK TERPADU (Unified Generic Schema) - identik untuk domain Bappenas dan Bencana BPBD.

Satu-satunya sumber kebenaran untuk: label node yang boleh, relasi yang boleh, normalisasi label/relasi lama,
adaptor dokumen domain -> struktur generik (`to_generic`), penjaga Cypher (`check`), dan prompt untuk extractor LLM
(`EXTRACTOR_SYSTEM_PROMPT` + `sanitize`). Jangan menambah label/relasi domain di sini; domain hanya mengubah NILAI properti.
"""
from __future__ import annotations
import re

ALLOWED_LABELS = ("Document", "Chunk", "Category", "SubCategory", "Tag", "Organization", "Location", "ProcessStep", "Question", "Answer", "Reference")
ALLOWED_RELS = ("CONTAINS_CHUNK", "SUB_CHUNK_OF", "IN_CATEGORY", "SUBCATEGORY_OF", "TAGGED_WITH", "BELONGS_TO_ORG", "LOCATED_IN",
                "REFERENCES_CHUNK", "CONTAINS_STEP", "ASKED_ABOUT", "ANSWERED_BY")

# arah relasi yang sah: tipe -> [(asal, tujuan)]
REL_SIGNATURES = {
    "CONTAINS_CHUNK": [("Document", "Chunk")], "SUB_CHUNK_OF": [("Chunk", "Chunk")], "REFERENCES_CHUNK": [("Chunk", "Chunk")],
    "IN_CATEGORY": [("Document", "Category"), ("Document", "SubCategory")], "SUBCATEGORY_OF": [("SubCategory", "Category")],
    "TAGGED_WITH": [("Document", "Tag"), ("Chunk", "Tag"), ("Document", "Reference")],
    "BELONGS_TO_ORG": [("Document", "Organization"), ("Organization", "Organization")],
    "LOCATED_IN": [("Document", "Location"), ("Chunk", "Location"), ("Location", "Location")],
    "CONTAINS_STEP": [("Document", "ProcessStep")], "ASKED_ABOUT": [("Question", "Document"), ("Question", "Chunk")],
    "ANSWERED_BY": [("Question", "Answer")],
}

# Label lama/domain -> label generik (None = bukan node; jadikan PROPERTI)
LABEL_MAP = {
    "UnitKerja": "Organization", "UKE": "Organization", "UKEInternal": "Organization", "UKEEksternal": "Organization", "Unit": "Organization",
    "Kedeputian": "Organization", "Deputi": "Organization", "Direktorat": "Organization", "Biro": "Organization", "Instansi": "Organization", "Mitra": "Organization",
    "DisasterType": "SubCategory", "DisasterEvent": "SubCategory", "Bencana": "Category", "JenisBencana": "SubCategory",
    "DamageReport": "Tag", "Infrastructure": "Tag", "Dampak": "Tag", "KategoriData": "Category", "BidangKategori": "Category", "SubKategori": "SubCategory",
    "Topik": "Tag", "Entitas": "Tag", "Wilayah": "Location", "Regulasi": "Reference", "Regulation": "Reference",
    "Dokumen": "Document", "Potongan": "Chunk", "Bagian": "Chunk", "SubPotongan": "Chunk", "Pertanyaan": "Question", "Jawaban": "Answer",
    "Year": None, "Tahun": None, "MeasureUnit": None, "Satuan": None, "JenisFile": None, "JenisPengetahuan": None, "JenisOutput": None,
}
# Relasi lama -> relasi generik (None = buang; informasi dipindah ke properti)
REL_MAP = {
    "PUBLISHED_BY": "BELONGS_TO_ORG", "PRODUCED_BY": "BELONGS_TO_ORG", "UNDER_DIVISION": "BELONGS_TO_ORG", "HAS_PARTNER": "BELONGS_TO_ORG",
    "PART_OF": "BELONGS_TO_ORG", "DITERBITKAN_OLEH": "BELONGS_TO_ORG", "BERADA_DALAM_UKE": "BELONGS_TO_ORG",
    "USES_REFERENCE": "TAGGED_WITH", "COVERS_DISASTER": "IN_CATEGORY", "AFFECTS_INFRASTRUCTURE": "TAGGED_WITH",
    "IN_SUB_CATEGORY": "IN_CATEGORY", "BERKATEGORI": "IN_CATEGORY", "MEMILIKI_SUB_KATEGORI": "IN_CATEGORY", "MENCAKUP_SUBKATEGORI": "SUBCATEGORY_OF",
    "PART_OF_LOCATION": "LOCATED_IN", "ABOUT_LOCATION": "LOCATED_IN", "MENCAKUP_WILAYAH": "LOCATED_IN", "BAGIAN_DARI": "CONTAINS_CHUNK",
    "DIJAWAB_OLEH": "ANSWERED_BY",
    "NEXT_CHUNK": None, "CITES": None, "FOR_YEAR": None, "MEASURED_IN": None, "TAHUN_DATA": None, "TERKAIT_DENGAN": None,
}

EXTRACTOR_SYSTEM_PROMPT = f"""Anda adalah ekstraktor graf pengetahuan. Ekstrak entitas dan relasi dari teks dokumen HANYA dengan skema berikut.

LABEL NODE YANG BOLEH (tidak boleh ada label lain):
- Document: dokumen sumber.   - Chunk: potongan teks.
- Category: kategori utama topik/bencana/program (contoh: Data Kejadian, Data Dampak, Banjir, Kebakaran, Deputi Bidang Infrastruktur).
- SubCategory: sub-kategori topik/jenis bencana (contoh: Banjir, Pohon Tumbang, Kerusakan & Kerugian).
- Tag: kata kunci / entitas spesifik, termasuk infrastruktur atau aset terdampak dan dampak (contoh: jembatan, rumah rusak berat).
- Organization: lembaga, instansi, unit kerja, kedeputian, direktorat, biro (SEMUA jenis unit/lembaga memakai label ini; properti `level`: instansi|UKE_1|UKE_2|UKE_3|mitra).
- Location: wilayah geografis (properti `level`: provinsi|kota|kabupaten|kecamatan|kelurahan|nasional).
- ProcessStep: langkah/prosedur/tahapan kegiatan (properti `step_order`).
- Question / Answer: pertanyaan dan jawabannya.
- Reference: acuan, regulasi, dasar hukum, sumber data.

RELASI YANG BOLEH (arah ditetapkan; tidak boleh ada relasi lain):
CONTAINS_CHUNK (Document->Chunk), SUB_CHUNK_OF (Chunk->Chunk induk), IN_CATEGORY (Document->Category|SubCategory),
SUBCATEGORY_OF (SubCategory->Category), TAGGED_WITH (Document|Chunk->Tag; Document->Reference dengan properti role),
BELONGS_TO_ORG (Document->Organization dengan properti role; Organization->Organization untuk hierarki), LOCATED_IN (Document|Chunk|Location->Location),
REFERENCES_CHUNK (Chunk->Chunk), CONTAINS_STEP (Document->ProcessStep), ASKED_ABOUT (Question->Document|Chunk), ANSWERED_BY (Question->Answer).

ATURAN NORMALISASI:
1. Dilarang membuat label: UnitKerja, DisasterType, DisasterEvent, DamageReport, Infrastructure, MeasureUnit, Year, atau label domain lain.
   Unit kerja/kedeputian/direktorat -> Organization. Jenis bencana (Banjir, Longsor) -> Category atau SubCategory.
   Dampak/infrastruktur rusak -> teks Chunk atau Tag.
2. Angka, tahun, satuan, ketinggian genangan, nilai kerugian -> PROPERTI pada Document/Chunk (year, satuan, inundation_cm, loss_value), BUKAN node.
3. Hanya ekstrak fakta yang tertulis eksplisit; jangan mengarang. Nama entitas persis seperti di teks. Kembalikan JSON: {{"nodes":[{{"id","label","properties"}}],"relationships":[{{"source","type","target","properties"}}]}}.
"""

_LAB = re.compile(r"\(\s*\w*\s*:\s*([A-Za-z][A-Za-z0-9_]*(?:\s*[:|]\s*[A-Za-z][A-Za-z0-9_]*)*)")
_REL = re.compile(r"\[\s*\w*\s*:\s*([A-Za-z_][A-Za-z0-9_]*(?:\s*\|\s*:?[A-Za-z_][A-Za-z0-9_]*)*)")
_SET_LAB = re.compile(r"\bSET\s+\w+\s*:\s*([A-Za-z]\w*)")


def check(cypher: str) -> str:
    """Tolak Cypher yang memakai label/relasi di luar skema terpadu. Mengembalikan cypher bila lolos."""
    for m in _LAB.finditer(cypher):
        for lab in re.split(r"\s*[:|]\s*", m.group(1)):
            if lab and lab not in ALLOWED_LABELS:
                raise ValueError(f"Label di luar skema terpadu: {lab}")
    for m in _SET_LAB.finditer(cypher):
        if m.group(1) not in ALLOWED_LABELS:
            raise ValueError(f"Label di luar skema terpadu: {m.group(1)}")
    for m in _REL.finditer(cypher):
        for rel in re.split(r"\s*\|\s*:?", m.group(1)):
            if rel and rel not in ALLOWED_RELS:
                raise ValueError(f"Relasi di luar skema terpadu: {rel}")
    return cypher


def normalize_label(label: str) -> str | None:
    label = (label or "").strip()
    if label in ALLOWED_LABELS:
        return label
    return LABEL_MAP.get(label, None) if label in LABEL_MAP else None


def normalize_rel(rel: str) -> str | None:
    rel = (rel or "").strip().upper()
    if rel in ALLOWED_RELS:
        return rel
    return REL_MAP.get(rel)


def sanitize(payload: dict) -> dict:
    """Bersihkan keluaran extractor LLM: petakan label/relasi lama, buang yang tidak sah, pindahkan arah/ketidakcocokan."""
    nodes, keep = [], {}
    for n in payload.get("nodes", []):
        lab = normalize_label(n.get("label", ""))
        if lab:
            keep[n["id"]] = lab
            nodes.append({**n, "label": lab})
    rels = []
    for r in payload.get("relationships", []):
        t = normalize_rel(r.get("type", ""))
        a, b = keep.get(r.get("source")), keep.get(r.get("target"))
        if t and a and b and (a, b) in REL_SIGNATURES[t]:
            rels.append({**r, "type": t})
    return {"nodes": nodes, "relationships": rels}


# ------------------------- adaptor dokumen domain -> struktur generik -------------------------
BAPPENAS_ROOT = {"org_id": "BAPPENAS", "name": "Kementerian PPN/Bappenas", "org_type": "Kementerian/Lembaga", "level": "instansi", "scope": "internal", "kontak": ""}


def _unit_level(name: str) -> str:
    n = name.lower()
    if re.match(r"^(deputi\b|sekretariat kementerian|sekretariat utama|inspektorat utama)", n):
        return "UKE_1"
    return "UKE_3" if re.match(r"^(subdirektorat|sub direktorat|bagian|subbagian)", n) else "UKE_2"


def _org_type(name: str) -> str:
    n = name.lower()
    if re.search(r"\b(un|unesco|unescap|undp|world bank|bank dunia|adb|oecd|imf|giz|jica|usaid|unicef|who|ilo|fao|irena)\b", n):
        return "Organisasi Internasional"
    if re.search(r"pemerintah (provinsi|kabupaten|kota|daerah)|^(provinsi|kabupaten|kota|pemda|dinas|bappeda)", n):
        return "Pemerintah Daerah"
    if re.search(r"kementerian|^kemen|badan|bappenas|\bbps\b|bank indonesia|lembaga|otoritas|dewan|komisi|kantor|lapan", n):
        return "Kementerian/Lembaga"
    return "Mitra Swasta"


def _loc(x) -> dict:
    return {"name": x, "level": "wilayah", "code": None, "parent": None} if isinstance(x, str) else {"level": "wilayah", "code": None, "parent": None, **x}


def to_generic(d: dict) -> dict:
    """Ubah dokumen ter-normalisasi domain apa pun (Bappenas/Bencana) ke struktur generik yang HANYA memakai label/relasi sah."""
    root = d.get("org")
    root = ({"org_id": root["org_id"], "name": root["name"], "org_type": root.get("org_type", "Kementerian/Lembaga"), "level": "instansi",
             "scope": "internal", "kontak": root.get("kontak", "")} if root else dict(BAPPENAS_ROOT))
    orgs, doc_orgs, org_orgs = {root["org_id"]: root}, [{"org_id": root["org_id"], "role": "penerbit", "detail": ""}], []
    unit, div = d.get("unit"), d.get("division")
    for u, role in ((unit, "penyusun_utama"), (div, "kedeputian")):
        if u:
            orgs.setdefault(u["unit_id"], {"org_id": u["unit_id"], "name": u["name"], "org_type": "Unit Kerja", "level": u["eselon_level"], "scope": "internal", "kontak": ""})
            doc_orgs.append({"org_id": u["unit_id"], "role": role, "detail": ""})
    if unit and div and unit["unit_id"] != div["unit_id"]:
        org_orgs.append({"child": unit["unit_id"], "parent": div["unit_id"], "role": "struktural", "level_path": f'{unit["eselon_level"]}_to_{div["eselon_level"]}'})
    top = div or unit
    if top:
        org_orgs.append({"child": top["unit_id"], "parent": root["org_id"], "role": "struktural", "level_path": ""})
    for p in d.get("partners", []):
        if p["kind"] == "unit":
            oid = p["unit_id"]
            orgs.setdefault(oid, {"org_id": oid, "name": p["name"], "org_type": "Unit Kerja", "level": _unit_level(p["name"]), "scope": "internal", "kontak": ""})
            org_orgs.append({"child": oid, "parent": root["org_id"], "role": "struktural", "level_path": ""})
            role = "mitra_internal"
        else:
            oid = p["org_id"]
            if oid != root["org_id"]:
                orgs.setdefault(oid, {"org_id": oid, "name": p["name"], "org_type": _org_type(p["name"]), "level": "mitra", "scope": "eksternal", "kontak": ""})
            role = "mitra_internal" if oid == root["org_id"] else "mitra_eksternal"
        doc_orgs.append({"org_id": oid, "role": role, "detail": p.get("label", "")})
    cat, sub = d.get("category") or "", d.get("subcategory") or ""
    subs = [{"name": s, "parent": cat or None} for s in dict.fromkeys([sub, *d.get("disasters", [])]) if s]  # jenis bencana -> SubCategory
    freq_kind = [(t, "kata_kunci") for t in d.get("tags", [])] + [(t, "infrastruktur") for t in d.get("infrastructure", [])]
    refs = [{**r, "role": "landasan_hukum" if r["ref_type"] == "Regulasi" else "data_input"} for r in d.get("refs", [])]
    extra = dict(d.get("extra") or {})
    extra["tags_text"] = " ".join(t for t, _ in freq_kind)
    if d.get("unit_measure") and not extra.get("satuan"):
        extra["satuan"] = d["unit_measure"]  # satuan = properti, bukan node
    return {"orgs": list(orgs.values()), "doc_orgs": doc_orgs, "org_orgs": org_orgs, "category": cat or None, "subcategories": subs,
            "tags": freq_kind, "references": refs, "steps": list(d.get("steps", [])), "locations": [_loc(x) for x in d.get("locations", [])], "extra": extra}
