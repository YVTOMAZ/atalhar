import json
import os
import tempfile

from atalhar.ledger import connect, init_db
from atalhar.importers.opencode import import_opencode


def _write_events(lines):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "events.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    return p, d


def test_import_opencode_fills_tokens_and_tools():
    events = [
        json.dumps({"tool": "bash", "input": {"command": "gh pr checks 12"}, "tokens": {"input": 100, "output": 20, "cache": {"read": 5}}, "ts": "2026-11-16T00:00:00Z", "model": "m"}),
        json.dumps({"tool": "webfetch", "input": {"url": "https://example.com/page?x=1"}, "tokens_input": 50, "tokens_output": 10}),
        "not json at all",
        json.dumps({"step": "finish", "tokens": {"input": 999, "output": 1}}),
        json.dumps({"tool": "bash", "input": {"command": "gh pr checks 15"}, "ts": "2026-11-16T00:00:01Z"}),
    ]
    p, d = _write_events(events)
    db = os.path.join(d, "t.db")
    init_db(db)
    res = import_opencode(p, db_path=db)
    assert res["imported"] == 3
    assert res["ignored"] == 1
    conn = connect(db)
    rows = conn.execute("SELECT tipo, alvo, tokens_entrada, tokens_saida, tokens_cache FROM execucoes ORDER BY id").fetchall()
    conn.close()
    assert len(rows) == 3
    # first row tokens from same line
    assert rows[0]["tokens_entrada"] == 100
    assert rows[0]["tokens_saida"] == 20
    assert rows[0]["tokens_cache"] == 5
    # second row url sanitized
    assert rows[1]["alvo"] == "https://example.com/page"
    # third row consumed pending tokens from step-finish
    assert rows[2]["tokens_entrada"] == 999


def test_import_opencode_same_fingerprint_for_different_ids():
    events = [
        json.dumps({"tool": "bash", "input": {"command": "gh pr checks 12"}, "tokens": {"input": 1, "output": 1}}),
        json.dumps({"tool": "bash", "input": {"command": "gh pr checks 99"}, "tokens": {"input": 1, "output": 1}}),
    ]
    p, d = _write_events(events)
    db = os.path.join(d, "t.db")
    init_db(db)
    import_opencode(p, db_path=db)
    conn = connect(db)
    fps = [r[0] for r in conn.execute("SELECT impressao_digital FROM execucoes").fetchall()]
    conn.close()
    assert len(set(fps)) == 1