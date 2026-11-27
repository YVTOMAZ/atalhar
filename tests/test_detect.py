import json
import os
import sqlite3
import subprocess
import sys
import tempfile

from atalhar.detect import detectar, parse_ts
from atalhar.ledger import connect, init_db, log_execucao


def _db(tmp_path):
    db = tmp_path / "atalhar.db"
    init_db(db)
    return db


def _rows(db):
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM execucoes").fetchall()
    conn.close()
    return rows


def test_three_same_fp_one_candidate_two_none(tmp_path):
    db = _db(tmp_path)
    fp = "abc123"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res = detectar(_rows(db), agora, n=3, dias=14)
    assert len(res["candidatos"]) == 1
    # agora 2 execucoes
    db2 = tmp_path / "two.db"
    init_db(db2)
    for i in range(2):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db2)
    res2 = detectar(_rows(db2), agora, n=3, dias=14)
    assert len(res2["candidatos"]) == 0


def test_out_of_window_not_counted(tmp_path):
    db = _db(tmp_path)
    fp = "fpw"
    # one inside, two old
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 10, "tokens_saida": 5,
                  "ts": "2026-11-16T10:00:00Z", "origem": "ia"}, path=db)
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 10, "tokens_saida": 5,
                  "ts": "2026-10-01T10:00:00Z", "origem": "ia"}, path=db)
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 10, "tokens_saida": 5,
                  "ts": "2026-10-02T10:00:00Z", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res = detectar(_rows(db), agora, n=3, dias=14)
    assert len(res["candidatos"]) == 0
    assert res["total_execucoes_janela"] == 1


def test_custo_min_filters_cheap(tmp_path):
    db = _db(tmp_path)
    fp = "fpc"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 1, "tokens_saida": 1,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res = detectar(_rows(db), agora, n=3, dias=14, custo_min=100)
    assert len(res["candidatos"]) == 0
    res2 = detectar(_rows(db), agora, n=3, dias=14, custo_min=0)
    assert len(res2["candidatos"]) == 1


def test_cache_excluded_by_default_included_with_flag(tmp_path):
    db = _db(tmp_path)
    fp = "fph"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5, "tokens_cache": 100,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res_off = detectar(_rows(db), agora, n=3, dias=14, incluir_cache=False)
    c = res_off["candidatos"][0]
    assert c["custo_medio_tokens"] == 15.0
    assert c["custo_total_tokens"] == 45
    res_on = detectar(_rows(db), agora, n=3, dias=14, incluir_cache=True)
    c2 = res_on["candidatos"][0]
    assert c2["custo_medio_tokens"] == 115.0
    assert c2["custo_total_tokens"] == 345


def test_deterministic_order_including_tie(tmp_path):
    db = _db(tmp_path)
    agora = parse_ts("2026-11-16T12:00:00Z")
    # two groups with same custo_total to test tie-break by ocorrencias then fp
    for fp, te in (("bbb", 10), ("aaa", 10)):
        for i in range(3):
            log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                          "tokens_entrada": te, "tokens_saida": 0,
                          "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    # make aaa have more occurrences -> higher? keep same 3; add tie-break by fp
    res = detectar(_rows(db), agora, n=3, dias=14)
    fps = [c["impressao_digital"] for c in res["candidatos"]]
    # same custo_total and ocorrencias -> impressao_digital asc
    assert fps == sorted(fps)


def test_mixed_ts_and_invalid(tmp_path):
    db = _db(tmp_path)
    fp = "fpm"
    # ISO Z
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 1, "tokens_saida": 1,
                  "ts": "2026-11-16T10:00:00Z", "origem": "ia"}, path=db)
    # ISO with offset
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 1, "tokens_saida": 1,
                  "ts": "2026-11-16T07:00:00-03:00", "origem": "ia"}, path=db)
    # epoch seconds
    import calendar, datetime as dt
    sec = calendar.timegm(dt.datetime(2026, 11, 16, 10, 0, 2, tzinfo=dt.timezone.utc).timetuple())
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 1, "tokens_saida": 1,
                  "ts": sec, "origem": "ia"}, path=db)
    # epoch ms
    ms = calendar.timegm(dt.datetime(2026, 11, 16, 10, 0, 3, tzinfo=dt.timezone.utc).timetuple()) * 1000
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 1, "tokens_saida": 1,
                  "ts": ms, "origem": "ia"}, path=db)
    # invalid ts
    log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                  "tokens_entrada": 1, "tokens_saida": 1,
                  "ts": "not-a-date", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res = detectar(_rows(db), agora, n=3, dias=14)
    assert res["ignorados_ts_invalido"] == 1
    # 4 valid -> candidate
    c = [x for x in res["candidatos"] if x["impressao_digital"] == fp][0]
    assert c["ocorrencias"] == 4


def test_json_keys(tmp_path):
    db = _db(tmp_path)
    fp = "fpj"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    agora = parse_ts("2026-11-16T12:00:00Z")
    res = detectar(_rows(db), agora, n=3, dias=14)
    # validate json serializable
    s = json.dumps(res, ensure_ascii=False)
    obj = json.loads(s)
    for k in ("parametros", "janela", "total_execucoes_janela", "ignorados_ts_invalido", "candidatos"):
        assert k in obj
    assert "inicio" in obj["janela"] and "fim" in obj["janela"]


def test_read_only_no_db_and_unchanged(tmp_path, monkeypatch):
    # no db
    home = tmp_path / "home1"
    home.mkdir()
    monkeypatch.setenv("ATALHAR_HOME", str(home))
    db_file = home / "atalhar.db"
    assert not db_file.exists()
    proc = subprocess.run([sys.executable, "-m", "atalhar", "detect"],
                          capture_output=True, text=True, env={**os.environ})
    # ensure env has ATALHAR_HOME
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    proc = subprocess.run([sys.executable, "-m", "atalhar", "detect"],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 2
    assert "livro-caixa vazio" in proc.stderr
    assert not db_file.exists()

    # with db, content unchanged
    home2 = tmp_path / "home2"
    home2.mkdir()
    db2 = home2 / "atalhar.db"
    init_db(db2)
    fp = "fpr"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db2)
    conn = sqlite3.connect(str(db2))
    before = conn.execute("SELECT COUNT(*) FROM execucoes").fetchone()[0]
    before_rows = conn.execute("SELECT * FROM execucoes").fetchall()
    conn.close()
    env2 = {**os.environ, "ATALHAR_HOME": str(home2)}
    proc2 = subprocess.run([sys.executable, "-m", "atalhar", "detect", "--json"],
                           capture_output=True, text=True, env=env2)
    assert proc2.returncode == 0
    conn = sqlite3.connect(str(db2))
    after = conn.execute("SELECT COUNT(*) FROM execucoes").fetchone()[0]
    after_rows = conn.execute("SELECT * FROM execucoes").fetchall()
    conn.close()
    assert before == after
    assert before_rows == after_rows


def test_invalid_args_code_2(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    cases = [
        ["detect", "--min-ocorrencias", "0"],
        ["detect", "--dias", "0"],
        ["detect", "--custo-min", "-1"],
        ["detect", "--limite", "0"],
        ["detect", "--ate", "not-a-date"],
    ]
    for c in cases:
        proc = subprocess.run([sys.executable, "-m", "atalhar"] + c,
                              capture_output=True, text=True, env=env)
        assert proc.returncode == 2, (c, proc.stderr)


def test_integration_atalhar_log_groups(tmp_path):
    home = tmp_path / "hint"
    home.mkdir()
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    # init db
    subprocess.run([sys.executable, "-m", "atalhar", "init"], capture_output=True, text=True, env=env)
    # two logs with targets differing by number + third
    for n in (12, 15, 99):
        # need same fingerprint: fingerprint normalizes numbers, so type+alvo normalizados equal
        subprocess.run([sys.executable, "-m", "atalhar", "log",
                        "--tipo", "consultar", "--alvo", f"https://x/pulls/{n}",
                        "--tokens-entrada", "10", "--tokens-saida", "5",
                        "--ts", "2026-11-16T10:00:00Z"],
                       capture_output=True, text=True, env=env)
    proc = subprocess.run([sys.executable, "-m", "atalhar", "detect", "--json"],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert len(obj["candidatos"]) == 1
    assert obj["candidatos"][0]["ocorrencias"] == 3
    assert obj["total_execucoes_janela"] == 3