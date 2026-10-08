"""Normalisasi metadata katalog Bappenas (JSON) -> dokumen terstruktur + blok teks hierarkis."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

MONTHS = {"januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
          "september": 9, "oktober": 10, "november": 11, "desember": 12}
KNOWN_EXT = {"pdf", "xlsx", "xls", "csv", "docx", "doc", "pptx", "ppt", "txt", "md", "json"}
REG_RE = re.compile(r"^(Undang-Undang|Peraturan|Keputusan|Instruksi|Surat Edaran|UU\b|Perpres|Permen|Perda)", re.I)
UKE_PREFIX = r"(?:Direktorat|Deputi|Biro|Pusat|Sekretariat|Inspektorat|Menteri|Kepala|Staf|Kementerian|Badan|Bagian|Subdirektorat)"
ORG_PREFIX = r"(?:Kementerian|Badan|Bank|Lembaga|Dinas|Pemerintah|Provinsi|Kabupaten|Kota|Universitas|Institut|PT|World|Asian|GIZ|OECD|IMF|BPS|Bappeda|Otoritas|Dewan|Komisi|Kantor)"
BAPPENAS_RE = re.compile(r"^(kementerian\s+)?ppn\s*/?\s*bappenas$|^bappenas$", re.I)


def clean(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("_x000D_", "").replace("\t", " ").strip().strip('"').strip()
    return "" if s in {"-", "–", "nan", "None"} else s


def hid(prefix: str, s: str) -> str:
    return f"{prefix}_{hashlib.sha1(s.lower().strip().encode()).hexdigest()[:8]}"


def parse_date(s) -> str | None:
    s = clean(s)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if m and m[2].lower() in MONTHS:
        return f"{m[3]}-{MONTHS[m[2].lower()]:02d}-{int(m[1]):02d}"
    return None


def eselon(name: str) -> str:
    n = name.lower()
    if re.match(r"^(deputi\b|sekretariat kementerian|sekretariat utama|inspektorat utama)", n):
        return "UKE_1"
    if re.match(r"^(subdirektorat|sub direktorat|bagian|subbagian)", n):
        return "UKE_3"
    return "UKE_2"


def org_type(name: str) -> str:
    n = name.lower()
    if re.search(r"\b(un|unesco|unescap|undp|world bank|bank dunia|adb|oecd|imf|giz|jica|usaid|unicef|who|ilo|fao|irena)\b", n):
        return "Organisasi Internasional"
    if re.search(r"pemerintah (provinsi|kabupaten|kota|daerah)|^(provinsi|kabupaten|kota|pemda|dinas|bappeda)", n):
        return "Pemerintah Daerah"
    if re.search(r"kementerian|^kemen|badan|bappenas|\bbps\b|bank indonesia|lembaga|otoritas|dewan|komisi|kantor|lapan", n):
        return "Kementerian/Lembaga"
    return "Mitra Swasta"


def split_names(s: str, prefix: str) -> list[str]:
    """Pisah daftar nama pada koma/titik koma di luar tanda kurung; 'serta/dan' di awal dibuang."""
    parts, depth, cur = [], 0, ""
    for ch in s:
        depth += (ch == "(") - (ch == ")")
        if ch in ",;\n" and depth <= 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    if prefix == UKE_PREFIX:  # nama unit bisa memuat koma ("Deputi Bidang Politik, Hukum, ... dan Keamanan"): sambung pecahan yang bukan awal nama unit baru
        head = re.compile(rf"^(?:(?:serta|dan|and)\s+)?{prefix}\b", re.I)
        merged: list[str] = []
        for p in parts:
            if merged and p.strip() and not head.match(p.strip(" .\"")):
                merged[-1] += "," + p
            else:
                merged.append(p)
        parts = merged
    out = []
    for p in parts:
        p = re.sub(r"^(serta|dan|and)\s+", "", p.strip(" .\""), flags=re.I).strip()
        p = re.sub(r"\(([^)]*)$", r"\1", p).strip()
        if 2 <= len(p) <= 110:
            out.append(p)
    return out


def ref_info(title: str) -> dict:
    m = re.search(r"Nomor\s+(\d+)\s+Tahun\s+(\d{4})", title, re.I)
    if REG_RE.match(title) and m:
        head = re.split(r"\s+Nomor\b", title, flags=re.I)[0].strip()
        abbr = {"undang-undang": "UU", "peraturan pemerintah": "PP", "peraturan presiden": "PERPRES"}.get(head.lower(), "PERATURAN")
        key = re.split(r"\s+tentang\s+", title, flags=re.I)[0]
        return {"ref_id": f"{abbr}-{m[1]}-{m[2]}-{hashlib.sha1(key.lower().encode()).hexdigest()[:4]}", "title": title, "ref_type": "Regulasi"}
    return {"ref_id": hid("SRC", title), "title": title, "ref_type": "Regulasi" if REG_RE.match(title) else "Data Sekunder"}


def parse_refs(raw: str) -> list[dict]:
    out, seen = [], set()
    for r in re.split(r";|\n", clean(raw)):
        r = r.strip(" .")
        if not r:
            continue
        items = [r] if REG_RE.match(r) else [x.strip(" .") for x in re.split(r",|\bserta\b", r) if len(x.strip(" .")) > 1]
        for it in items:
            info = ref_info(it)
            if info["ref_id"] not in seen:
                seen.add(info["ref_id"]); out.append(info)
    return out


def parse_partners(raw: str) -> list[dict]:
    out = []
    for line in clean(raw).split("\n"):
        if ":" not in line:
            continue
        label, rest = line.split(":", 1)
        label, rest = label.strip(), clean(rest)
        if not rest:
            continue
        unit = label.lower().startswith(("internal", "uke"))
        for name in split_names(rest, UKE_PREFIX if unit else ORG_PREFIX):
            if BAPPENAS_RE.match(name):
                out.append({"kind": "org", "label": label, "name": "Kementerian PPN/Bappenas", "org_id": "BAPPENAS"})
            elif unit:
                out.append({"kind": "unit", "label": label, "name": name, "unit_id": hid("UK", name)})
            else:
                out.append({"kind": "org", "label": label, "name": name, "org_id": hid("ORG", name)})
    return out


def split_tags(s) -> list[str]:
    seen, out = set(), []
    for t in re.split(r"[,;\n]", clean(s)):
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


def detect_locations(text: str) -> list[str]:
    locs = {m.group(0).strip() for m in re.finditer(r"\b(?:Kota|Kabupaten|Provinsi)\s+[A-Z]\w+(?:\s+[A-Z]\w+){0,2}", text)}
    return sorted(locs) or ["Nasional"]


def normalise(row: dict, idx: int) -> dict:
    title, fname = clean(row.get("Judul")), clean(row.get("Nama File"))
    m = re.search(r"\.([A-Za-z0-9]{2,4})$", fname)
    ext = m.group(1).lower() if m and m.group(1).lower() in KNOWN_EXT else ""
    out_type = clean(row.get("Jenis Output")) or "Lainnya"
    ftype = ext.upper() if ext else ("Infografis" if out_type == "Infografis" else "Tidak diketahui")
    url, unit, cat = clean(row.get("Dokumen Pengetahuan")), clean(row.get("Unit Kerja")), clean(row.get("Bidang Kategori"))
    steps = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip() for l in clean(row.get("Bisnis Proses")).split("\n")]
    desc, ben = clean(row.get("Deskripsi")), clean(row.get("Manfaat"))
    return {
        "doc_id": f"DOC-{idx:03d}", "title": title, "file_name": fname, "file_type": ftype, "output_type": out_type,
        "knowledge_type": clean(row.get("Jenis Pengetahuan")), "description": desc, "benefit": ben,
        "classification": clean(row.get("Klasifikasi")), "access_rights": clean(row.get("Hak Akses Dokumen")),
        "document_url": url if url.startswith("http") else "", "publish_date": parse_date(row.get("Tanggal Publikasi")),
        "year": re.sub(r"\D", "", clean(row.get("Tahun Penyusunan")))[:4], "domain": "bappenas",
        "category": cat, "unit_kerja": unit,
        "unit": {"unit_id": hid("UK", unit), "name": unit, "eselon_level": eselon(unit)} if unit else None,
        "division": {"unit_id": hid("UK", cat), "name": cat, "eselon_level": eselon(cat)} if cat else None,
        "subcategory": re.sub(r"^(Direktorat|Biro|Pusat|Sekretariat|Subdirektorat|Bagian)\s+", "", unit) if unit else "",
        "tags": split_tags(row.get("Tag")), "refs": parse_refs(row.get("Referensi yang Digunakan")),
        "steps": [s for s in steps if s], "partners": parse_partners(row.get("Mitra (Unit Kerja/Instansi Lain)")),
        "locations": detect_locations(f"{title} {desc}"),
    }


def load_docs(path: Path) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = _find_rows(raw)
    return [normalise(r, i) for i, r in enumerate(rows, 1) if clean(r.get("Judul"))]


def _find_rows(node) -> list[dict]:
    """Cari daftar baris ber-kolom 'Judul' pada bentuk JSON apa pun: [..], {"sheet":[..]}, {"x":[{"Sheet1":[..]}]} (ekspor Excel bersarang)."""
    if isinstance(node, list):
        if any(isinstance(r, dict) and "Judul" in r for r in node):
            return [r for r in node if isinstance(r, dict)]
        for r in node:
            found = _find_rows(r)
            if found:
                return found
    elif isinstance(node, dict):
        if "Judul" in node:
            return [node]
        for v in node.values():
            found = _find_rows(v)
            if found:
                return found
    return []


# ---- blok teks hierarkis dari metadata ----
def H(level: int, text: str) -> dict:
    return {"kind": "h", "level": level, "text": text, "page": None}


def P(text: str, section: str, item: int | None = None) -> dict:
    return {"kind": "p", "text": text, "page": None, "atomic": True, "section": section, "item": item}


def identity_text(d: dict) -> str:
    s = (f'Dokumen "{d["title"]}" berjenis {d["output_type"]} ({d["knowledge_type"] or "jenis pengetahuan tidak dicatat"}), '
         f'disusun oleh {d["unit_kerja"] or "unit kerja tidak dicatat"} pada tahun {d["year"] or "tidak dicatat"}, '
         f'termasuk dalam {d["category"] or "kategori tidak dicatat"}. Hak akses: {d["access_rights"] or "tidak dicatat"}.')
    return s + (f' Dipublikasikan pada {d["publish_date"]}.' if d["publish_date"] else "")


def metadata_blocks(d: dict) -> list[dict]:
    t, b = d["title"], [H(1, "Ringkasan Dokumen"), P(identity_text(d), "identitas")]
    if d["description"]:
        b.append(P(f'Deskripsi dokumen "{t}": {d["description"]}', "deskripsi"))
    if d["benefit"]:
        b += [H(1, "Manfaat Dokumen"), P(f'Manfaat dokumen "{t}": {d["benefit"]}', "manfaat")]
    if d["steps"]:
        b.append(H(1, "Proses Bisnis Penyusunan"))
        b += [P(f'Langkah {i} proses bisnis penyusunan "{t}": {s}', "proses_bisnis", i) for i, s in enumerate(d["steps"], 1)]
    regs = [r for r in d["refs"] if r["ref_type"] == "Regulasi"]
    sec = [r for r in d["refs"] if r["ref_type"] != "Regulasi"]
    if regs or sec:
        b.append(H(1, "Dasar Hukum dan Sumber Data"))
        if regs:
            b.append(H(2, "Landasan Hukum (Regulasi)"))
            b += [P(f'Dokumen "{t}" berlandaskan regulasi: {r["title"]}', "regulasi", i) for i, r in enumerate(regs, 1)]
        if sec:
            b.append(H(2, "Data Sekunder dan Sumber Rujukan"))
            b += [P(f'Dokumen "{t}" menggunakan sumber data: {r["title"]}', "data_sekunder", i) for i, r in enumerate(sec, 1)]
    if d["partners"]:
        b.append(H(1, "Mitra dan Kolaborasi"))
        n = 0
        for lab in dict.fromkeys(p["label"] for p in d["partners"]):
            b.append(H(2, f"Mitra: {lab}"))
            for p in [p for p in d["partners"] if p["label"] == lab]:
                n += 1
                b.append(P(f'Mitra ({lab}) dalam penyusunan "{t}": {p["name"]}', "mitra", n))
    if d["tags"]:
        b += [H(1, "Kata Kunci"), P(f'Kata kunci dokumen "{t}": {", ".join(d["tags"])}', "tag")]
    return b
