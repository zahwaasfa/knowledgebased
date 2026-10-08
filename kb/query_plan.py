"""Pemahaman pertanyaan (tanpa LLM): intent, bagian dokumen yang diminta, istilah topik, tahun, deteksi pertanyaan lanjutan.

Tujuan: pertanyaan ber-sinonim ("manfaat" / "kegunaan" / "untuk apa") dan pertanyaan pendek ("jabarkan isinya")
dipetakan ke BAGIAN graf yang tepat (Chunk.section) -- bukan ke teks template yang kebetulan mirip.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field

from .text import STOP

# intent -> (regex pada teks ter-normalisasi, daftar Chunk.section yang dibutuhkan)
OVERVIEW_SECTIONS = ["deskripsi", "manfaat", "identitas", "proses_bisnis", "regulasi", "data_sekunder", "mitra", "tag"]
INTENTS: dict[str, tuple[str, list[str]]] = {
    "manfaat": (r"\b(manfaat\w*|kegunaan|berguna|faedah|fungsi|untuk apa|guna)\b", ["manfaat"]),
    "regulasi": (r"\b(regulasi|dasar hukum|landasan( hukum)?|peraturan|undang[- ]undang|perpres|permen|payung hukum|legal\w*)\b", ["regulasi"]),
    "proses": (r"\b(proses( bisnis)?|tahap\w*|langkah\w*|alur|mekanisme|prosedur|cara (menyusun|penyusunan))\b", ["proses_bisnis"]),
    "mitra": (r"\b(mitra|kolaborasi|kerja ?sama|pihak|terlibat|stakeholder|kontributor)\b", ["mitra"]),
    "sumber_data": (r"\b(sumber data|data sekunder|referensi|rujukan|acuan|data (yang )?(digunakan|dipakai))\b", ["data_sekunder", "regulasi"]),
    "tag": (r"\b(kata kunci|keyword|tag|label topik)\b", ["tag"]),
    "identitas": (r"\b(siapa (yang )?(menyusun|membuat|penyusun\w*)|penyusun|disusun|unit kerja|biro|direktorat|kapan|terbit|diterbitkan|publikasi|dipublikasikan|hak akses|jenis (dokumen|output|pengetahuan)|klasifikasi|kategori)\b", ["identitas"]),
    "deskripsi": (r"\b(deskripsi|gambaran umum|tentang apa)\b", ["deskripsi"]),
    "ringkasan": (r"\b(ringkas\w*|rangkum\w*|isi\w*|jabar\w*|uraikan|uraian|rinci\w*|detail\w*|jelaskan|penjelasan|gambaran|overview|membahas|memuat|berisi|pokok|inti|paparkan|ceritakan|lengkap)\b", OVERVIEW_SECTIONS),
    "daftar_dokumen": (r"\b(dokumen apa saja|daftar dokumen|apa saja dokumen|dokumen (apa )?yang (ada|tersedia)|ada dokumen)\b", []),
    "terkait": (r"\b(terkait|serupa|mirip|dokumen lain|rekomendasi dokumen|berhubungan)\b", []),
}
INTENT_ORDER = ["manfaat", "regulasi", "proses", "mitra", "sumber_data", "tag", "identitas", "daftar_dokumen", "terkait", "deskripsi", "ringkasan"]
# kata pembentuk intent/pertanyaan: dibuang dari istilah topik agar pencarian dokumen tidak tercemar
GENERIC = set("""manfaat kegunaan berguna faedah fungsi guna regulasi hukum landasan peraturan perpres permen payung proses tahap tahapan langkah
alur mekanisme prosedur mitra kolaborasi kerjasama kerja sama pihak terlibat stakeholder kontributor sumber data sekunder referensi rujukan acuan
kata kunci keyword tag siapa penyusun disusun terbit diterbitkan publikasi dipublikasikan ringkas ringkasan rangkum rangkuman isi isinya jabarkan
jabaran uraikan uraian rinci rincian detail jelaskan penjelasan gambaran overview deskripsi membahas memuat berisi pokok inti paparkan ceritakan
lengkap terkait serupa mirip berhubungan nya menjadi merupakan tolong mohon berikan sebutkan apa saja dokumen lebih lanjut dong ya lagi""".split())
ANAPHORA = re.compile(r"\b(nya|tersebut|tadi|sebelumnya|di atas|(dokumen|laporan|publikasi|kajian|buku) (ini|itu)|lebih (detail|lanjut|dalam|rinci)|lanjutkan|selengkapnya|jabarkan|uraikan|rinci)\b")
DETAIL = re.compile(r"\b(jabar\w*|uraikan|uraian|rinci\w*|detail\w*|lengkap\w*|selengkapnya|semua|seluruh)\b")
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[/_\-]+", " ", s)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


_PRE = ("meng", "meny", "mem", "men", "peng", "peny", "pem", "pen", "ber", "per", "ter", "me", "pe", "di", "ke")
_SUF = ("kan", "nya", "an", "i")


def stem(t: str) -> str:
    """Stemmer Indonesia sangat ringan (hanya untuk menghitung kecocokan istilah; morfologi berat ditangani analyzer Lucene)."""
    for s in _SUF:
        if t.endswith(s) and len(t) - len(s) >= 4:
            t = t[:-len(s)]
            break
    for p in _PRE:
        if t.startswith(p) and len(t) - len(p) >= 4:
            rest = t[len(p):]
            return "s" + rest if p in ("peny", "meny") else rest
    return t


def terms(text: str, min_len: int = 3) -> list[str]:
    out, seen = [], set()
    for t in fold(text).split():
        if (len(t) >= min_len or t.isdigit()) and t not in STOP and t not in seen:
            seen.add(t); out.append(t)
    return out


def detect_intents(text: str) -> list[str]:
    f = fold(text)
    return [k for k in INTENT_ORDER if re.search(INTENTS[k][0], f)]


def strip_title_mentions(question: str, title: str) -> str:
    """Hapus runtun >=2 kata dari pertanyaan yang juga muncul berurutan di judul (agar 'Peraturan' dalam judul tidak dianggap intent)."""
    q, t = fold(question).split(), " " + fold(title) + " "
    i, out = 0, []
    while i < len(q):
        j = len(q)
        while j - i >= 2 and f" {' '.join(q[i:j])} " not in t:
            j -= 1
        if j - i >= 2:
            i = j
        else:
            out.append(q[i]); i += 1
    return " ".join(out)


@dataclass
class QueryPlan:
    raw: str
    topic: list[str] = field(default_factory=list)       # istilah topik (tanpa kata intent)
    intents: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    year: str | None = None
    detail: bool = False                                  # minta rincian penuh (tanpa pemotongan daftar)
    followup: bool = False                                # tidak menyebut topik sendiri -> pakai konteks percakapan

    @property
    def topic_stems(self) -> set[str]:
        return {stem(t) for t in self.topic}

    def reintent(self, title: str | None) -> "QueryPlan":
        """Hitung ulang intent setelah dokumen teridentifikasi (judul dokumen tidak boleh memicu intent)."""
        text = strip_title_mentions(self.raw, title) if title else self.raw
        self.intents = detect_intents(text) or self.intents
        self.sections = sections_for(self.intents)
        return self


def sections_for(intents: list[str]) -> list[str]:
    secs: list[str] = []
    for i in intents:
        for s in INTENTS[i][1]:
            if s not in secs:
                secs.append(s)
    return secs


def analyze(question: str) -> QueryPlan:
    f = fold(question)
    intents = detect_intents(question)
    # "proses penyusunan X" -> 'penyusunan' hanyalah pola pertanyaan, bukan kata judul
    topic_src = re.sub(r"\b(proses|tahapan|tahap|langkah|cara|alur|mekanisme)( bisnis)? (penyusunan|menyusun|pembuatan|pembuat)\b", " ", f)
    topic = [t for t in terms(topic_src) if t not in GENERIC]
    y = YEAR.search(f)
    followup = (not [t for t in topic if not t.isdigit()]) or (bool(ANAPHORA.search(f)) and len(topic) <= 1)
    return QueryPlan(raw=question, topic=topic, intents=intents, sections=sections_for(intents), year=y.group(0) if y else None, followup=followup, detail=bool(DETAIL.search(f)))
