"""Pembungkus driver resmi Neo4j: tunggu siap, transaksi baca/tulis, eksekusi skrip Cypher idempoten."""
from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Iterable
from neo4j import GraphDatabase
from .config import S


def split_statements(raw: str) -> list[str]:
    lines = [l for l in raw.splitlines() if not l.strip().startswith("//")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


class DB:
    def __init__(self, uri=None, user=None, password=None, database=None):
        self.driver = GraphDatabase.driver(uri or S.neo4j_uri, auth=(user or S.neo4j_user, password or S.neo4j_password))
        self.database = database or S.neo4j_database

    def close(self) -> None:
        self.driver.close()

    def wait_ready(self, timeout: int = 180) -> None:
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            try:
                self.driver.verify_connectivity()
                self.read("RETURN 1 AS ok")
                return
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(3)
        raise RuntimeError(f"Neo4j tidak siap dalam {timeout}s: {last}")

    def read(self, query: str, **params: Any) -> list[dict]:
        with self.driver.session(database=self.database) as s:
            return s.execute_read(lambda tx: [r.data() for r in tx.run(query, **params)])

    def write(self, query: str, **params: Any) -> list[dict]:
        with self.driver.session(database=self.database) as s:
            return s.execute_write(lambda tx: [r.data() for r in tx.run(query, **params)])

    def write_many(self, stmts: Iterable[tuple[str, dict]]) -> None:
        """Beberapa statement dalam SATU transaksi (atomik)."""
        stmts = list(stmts)

        def work(tx):
            for q, p in stmts:
                tx.run(q, **p).consume()
        with self.driver.session(database=self.database) as s:
            s.execute_write(work)

    def run_script(self, path: Path) -> int:
        n = 0
        for stmt in split_statements(path.read_text(encoding="utf-8")):
            self.write(stmt); n += 1
        return n
