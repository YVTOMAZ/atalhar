"""Livro-caixa local em SQLite."""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_NAME = "atalhar.db"

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|secret)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),
]


def data_dir() -> Path:
    env = os.environ.get("ATALHAR_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".atalhar"


def db_path() -> Path:
    return data_dir() / DB_NAME


SCHEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agente TEXT,
    modelo TEXT,
    tipo TEXT NOT NULL,
    alvo TEXT NOT NULL,
    impressao_digital TEXT NOT NULL,
    tokens_entrada INTEGER DEFAULT 0,
    tokens_saida INTEGER DEFAULT 0,
    tokens_cache INTEGER DEFAULT 0,
    duracao_ms INTEGER,
    ok INTEGER DEFAULT 1,
    origem TEXT NOT NULL,
    nota TEXT
);
"""


def init_db(path=None) -> Path:
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return p


def connect(path=None):
    p = Path(path) if path else db_path()
    if not p.exists():
        init_db(p)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_nota(text: str) -> str:
    if text is None:
        return ""
    s = text
    for pat in SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    if len(s) > 200:
        s = s[:200]
    return s


def sanitize_url(url: str) -> str:
    # reuso do fingerprint.sanitize_url
    from .fingerprint import sanitize_url as _su

    return _su(url)


def insert_execucao(conn, row: dict) -> int:
    cur = conn.execute(
        """INSERT INTO execucoes
        (ts, agente, modelo, tipo, alvo, impressao_digital, tokens_entrada,
         tokens_saida, tokens_cache, duracao_ms, ok, origem, nota)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            row.get("ts") or now_iso(),
            row.get("agente"),
            row.get("modelo"),
            row["tipo"],
            sanitize_url(row["alvo"]),
            row["impressao_digital"],
            int(row.get("tokens_entrada") or 0),
            int(row.get("tokens_saida") or 0),
            int(row.get("tokens_cache") or 0),
            row.get("duracao_ms"),
            1 if row.get("ok", True) else 0,
            row.get("origem") or "ia",
            redact_nota(row.get("nota") or ""),
        ),
    )
    conn.commit()
    return cur.lastrowid


def log_execucao(row: dict, path=None) -> int:
    conn = connect(path)
    try:
        return insert_execucao(conn, row)
    finally:
        conn.close()