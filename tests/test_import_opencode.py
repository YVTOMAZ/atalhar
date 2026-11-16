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


def _tool_use(tool, inp, ts=None):
    part = {"type": "tool", "tool": tool, "state": {"status": "completed", "input": inp}}
    obj = {"type": "tool_use", "part": part}
    if ts is not None:
        obj["timestamp"] = ts
    return json.dumps(obj)


def _step_finish(tokens, ts=None):
    obj = {"type": "step_finish", "part": {"type": "step-finish", "tokens": tokens}}
    if ts is not None:
        obj["timestamp"] = ts
    return json.dumps(obj)


def test_import_opencode_fills_tokens_and_tools():
    events = [
        _tool_use("shell", {"command": "gh pr checks 12"}, 1),
        _step_finish({"input": 100, "output": 20, "cache": {"read": 5, "write": 0}}, 2),
        _tool_use("webfetch", {"url": "https://example.com/page?x=1"}, 3),
        _step_finish({"input": 50, "output": 10}, 4),
        "not json at all",
        _tool_use("shell", {"command": "gh pr checks 15"}, 5),
        _step_finish({"input": 999, "output": 1}, 6),
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
    # first row tokens from following step-finish
    assert rows[0]["tokens_entrada"] == 100
    assert rows[0]["tokens_saida"] == 20
    assert rows[0]["tokens_cache"] == 5
    # second row url sanitized
    assert rows[1]["alvo"] == "https://example.com/page"
    assert rows[1]["tokens_entrada"] == 50
    assert rows[1]["tokens_saida"] == 10
    # third row consumed tokens from its step-finish
    assert rows[2]["tokens_entrada"] == 999


def test_import_opencode_same_fingerprint_for_different_ids():
    events = [
        _tool_use("shell", {"command": "gh pr checks 12"}, 1),
        _step_finish({"input": 1, "output": 1}, 2),
        _tool_use("shell", {"command": "gh pr checks 99"}, 3),
        _step_finish({"input": 1, "output": 1}, 4),
    ]
    p, d = _write_events(events)
    db = os.path.join(d, "t.db")
    init_db(db)
    import_opencode(p, db_path=db)
    conn = connect(db)
    fps = [r[0] for r in conn.execute("SELECT impressao_digital FROM execucoes").fetchall()]
    conn.close()
    assert len(set(fps)) == 1


def test_import_opencode_different_tasks_different_fingerprint():
    events = [
        _tool_use("shell", {"command": "gh pr checks 12"}, 1),
        _step_finish({"input": 1, "output": 1}, 2),
        _tool_use("webfetch", {"url": "https://example.com/users/12"}, 3),
        _step_finish({"input": 1, "output": 1}, 4),
    ]
    p, d = _write_events(events)
    db = os.path.join(d, "t.db")
    init_db(db)
    import_opencode(p, db_path=db)
    conn = connect(db)
    fps = [r[0] for r in conn.execute("SELECT impressao_digital FROM execucoes").fetchall()]
    conn.close()
    assert len(set(fps)) == 2