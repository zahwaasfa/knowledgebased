"""Chunking hierarkis berkedalaman variabel (bergantung struktur dokumen).

Dokumen -> chunk level 0 (bab/ringkasan) -> sub-bagian -> paragraf/baris tabel -> ... sedalam struktur teks.
Bagian dengan anak > fan-out dikelompokkan sehingga level tambahan tumbuh otomatis (tidak ada batas kedalaman).
ID deterministik: DOC-001_c0_c1_c2 (jejak indeks anak dari akar). Kapasitas: bila jumlah chunk melebihi
`max_chunks`, ukuran chunk diperbesar bertahap sampai muat.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    parent_id: str | None
    level: int
    chunk_index: int
    text: str
    breadcrumb: str
    page: int | None
    section: str | None
    item_no: int | None
    is_leaf: bool
    token_count: int
    next_id: str | None = None


@dataclass
class Node:
    heading: str = ""
    text: str = ""
    page: int | None = None
    section: str | None = None
    item: int | None = None
    children: list = field(default_factory=list)


@dataclass
class Sec:
    heading: str
    level: int
    paras: list = field(default_factory=list)
    kids: list = field(default_factory=list)


SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


def lead(text: str, n: int = 350) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[:n]
    m = max(cut.rfind(". "), cut.rfind("; "))
    return cut[:m + 1] if m > n * 0.5 else cut[:max(cut.rfind(" "), 1)] + " …"


def split_text(text: str, mx: int) -> list[str]:
    """Pecah pada batas kalimat; kalimat terlalu panjang dipecah pada batas kata (tidak memotong kata)."""
    if len(text) <= mx:
        return [text]
    out, cur = [], ""
    for s in SENT.split(text):
        while len(s) > mx:
            cut = s.rfind(" ", 0, mx)
            cut = cut if cut > 0 else mx
            if cur:
                out.append(cur); cur = ""
            out.append(s[:cut].strip()); s = s[cut:].lstrip()
        if cur and len(cur) + len(s) + 1 > mx:
            out.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _parse(blocks: list[dict]) -> Sec:
    root = Sec("", 0)
    stack = [root]
    for b in blocks:
        if b["kind"] == "h":
            while stack[-1].level >= b["level"]:
                stack.pop()
            s = Sec(b["text"], b["level"])
            stack[-1].kids.append(s); stack.append(s)
        else:
            if stack[-1] is root:
                s = Sec("Bagian Awal", 1); root.kids.append(s); stack.append(s)
            stack[-1].paras.append(b)
    return root


def _bundle(nodes: list[Node], fan: int, head: str) -> list[Node]:
    while len(nodes) > fan:
        groups = [nodes[i:i + fan] for i in range(0, len(nodes), fan)]
        nodes = [Node(heading=f"{head} (bagian {i}/{len(groups)})", text=f"{head} (bagian {i}/{len(groups)})\n" + lead(g[0].text, 200) + " …",
                      page=g[0].page, children=g) for i, g in enumerate(groups, 1)]
    return nodes


def _to_node(sec: Sec, mx: int, fan: int) -> Node | None:
    own: list[Node] = []
    run: list[dict] = []

    def flush_run():
        if not run:
            return
        units = [u for p in run for u in split_text(p["text"], mx)]
        cur, pg = "", run[0]["page"]
        for u in units:
            if cur and len(cur) + len(u) + 1 > mx:
                own.append(Node(text=cur, page=pg)); cur, pg = u, run[0]["page"]
            else:
                cur = f"{cur}\n{u}".strip()
        if cur:
            own.append(Node(text=cur, page=pg))
        run.clear()
    atomic = False
    for p in sec.paras:
        if p.get("atomic"):
            flush_run(); atomic = True
            own.append(Node(text=p["text"], page=p["page"], section=p.get("section"), item=p.get("item")))
        else:
            run.append(p)
    flush_run()
    kids = [n for n in (_to_node(k, mx, fan) for k in sec.kids) if n]
    if not own and not kids:
        return None
    if not kids and len(own) == 1:
        n = own[0]
        n.heading = sec.heading
        if not n.section and sec.heading:
            n.text = f"{sec.heading}\n{n.text}".strip()
        return n
    node = Node(heading=sec.heading, page=(own or kids)[0].page)
    full = "\n".join(o.text for o in own)
    if own and not atomic and len(full) <= mx:
        node.text, node.children = f"{sec.heading}\n{full}".strip(), kids
    else:
        if own:
            node.text = f"{sec.heading}\n{lead(full, 350)}".strip()
        else:
            node.text = f"{sec.heading}\nBerisi sub-bagian: " + "; ".join(k.heading for k in kids if k.heading)[:300]
        node.children = _bundle(own, fan, sec.heading) + kids
    return node


def _finalize(nodes: list[Node], doc_id: str, title: str) -> list[Chunk]:
    out: list[Chunk] = []

    def walk(n: Node, parent: Chunk | None, idx: int, crumb: str):
        cid = f"{parent.chunk_id if parent else doc_id}_c{idx}"
        bc = f"{crumb} > {n.heading}" if n.heading and not crumb.endswith(n.heading) else crumb
        c = Chunk(cid, doc_id, parent.chunk_id if parent else None, parent.level + 1 if parent else 0, idx,
                  n.text.strip(), bc, n.page, n.section, n.item, not n.children, int(len(re.findall(r"\w+", n.text)) * 1.3))
        out.append(c)
        for i, k in enumerate(n.children):
            walk(k, c, i, bc)
    for i, n in enumerate(nodes):
        walk(n, None, i, title)
    sibs: dict = {}
    for c in out:
        sibs.setdefault(c.parent_id, []).append(c)
    for lst in sibs.values():
        for a, b in zip(lst, lst[1:]):
            a.next_id = b.chunk_id
    return out


def build_chunks(doc_id: str, title: str, blocks: list[dict], max_chars: int = 1200, fanout: int = 8,
                 max_chunks: int = 3000) -> list[Chunk]:
    root, mx, chunks = _parse(blocks), max_chars, []
    for _ in range(8):
        nodes = [n for n in (_to_node(s, mx, fanout) for s in root.kids) if n]
        chunks = _finalize(nodes, doc_id, title)
        if len(chunks) <= max_chunks:
            return chunks
        mx = int(mx * 1.6)
    return chunks[:max_chunks]
