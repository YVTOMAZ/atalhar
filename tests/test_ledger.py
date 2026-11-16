import os
import tempfile

from atalhar.ledger import init_db, log_execucao, connect, redact_nota, sanitize_url


def test_log_sanitizes_url_and_redacts_secret():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    init_db(db)
    rid = log_execucao({
        "tipo": "consultar",
        "alvo": "https://user:pass@example.com/path?token=secret",
        "impressao_digital": "fp1",
        "nota": "api_key=abc123 token=xyz",
        "origem": "ia",
    }, path=db)
    assert rid >= 1
    conn = connect(db)
    row = conn.execute("SELECT alvo, nota FROM execucoes WHERE id=?", (rid,)).fetchone()
    conn.close()
    assert row["alvo"] == "https://example.com/path"
    assert "abc123" not in row["nota"]
    assert "xyz" not in row["nota"]
    assert "[REDACTED]" in row["nota"]


def test_redact_nota_truncates_200():
    s = ("abc " * 80).strip()
    assert len(s) > 200
    assert len(redact_nota(s)) == 200


def test_sanitize_url_helper():
    assert sanitize_url("https://u:p@h.com/p?q=1") == "https://h.com/p"