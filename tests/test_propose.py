import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from atalhar.propose import propor, decidir, pode_criar, texto_proposta, id_de
from atalhar.ledger import init_db, log_execucao

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "propose"


def _cand():
    return json.loads((FIX / "candidato.json").read_text())


def test_id_estavel():
    fp = "fp1"
    assert id_de(fp) == "p-" + hashlib.sha256(fp.encode()).hexdigest()[:12]


def test_propor_basico(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    est = None
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    assert res["estado"] == "pendente"
    assert res["id"].startswith("p-")
    assert "pergunta_ao_usuario" in res
    assert res["opcoes"] == ["sim", "nao", "depois", "nunca"]
    assert pode_criar(res["id"]) is False


def test_idempotencia(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    r1 = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    r2 = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    assert r1["id"] == r2["id"]
    # uma linha
    import sqlite3

    conn = sqlite3.connect(str(home / "atalhar.db"))
    n = conn.execute("SELECT COUNT(*) FROM propostas").fetchone()[0]
    assert n == 1
    conn.close()


def test_decide_sim(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    d = decidir(pid, "sim", agora="2026-11-27T13:00:00Z")
    assert d["estado"] == "aprovada"
    assert d["mudou"] is True
    assert pode_criar(pid) is True
    # repetir
    d2 = decidir(pid, "sim", agora="2026-11-27T13:00:00Z")
    assert d2["mudou"] is False


def test_nunca_bloqueia(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "nunca", agora="2026-11-27T13:00:00Z")
    # another candidate same alvo
    cand2 = dict(cand)
    cand2["impressao_digital"] = "fp2"
    r2 = propor(cand2, estimativa=est, agora="2026-11-27T13:00:00Z")
    assert r2["estado"] == "bloqueado_nunca"


def test_revogar_nunca(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "nunca", agora="2026-11-27T13:00:00Z")
    # sim without flag
    try:
        decidir(pid, "sim", agora="2026-11-27T13:00:00Z")
    except Exception:
        pass
    # with flag
    d = decidir(pid, "sim", agora="2026-11-27T13:00:00Z", revogar_nunca=True)
    assert d["estado"] == "aprovada"
    assert d["mudou"] is True


def test_nao_prazo(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "nao", agora="2026-11-27T13:00:00Z")
    # repropor before 30 days
    r = propor(cand, estimativa=est, agora="2026-11-28T13:00:00Z")
    assert r["estado"] == "recusada"
    # with repropor
    r2 = propor(cand, estimativa=est, agora="2026-11-28T13:00:00Z", repropor=True)
    assert r2["estado"] == "pendente"


def test_depois_prazo(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "depois", agora="2026-11-27T13:00:00Z")
    # before 7 days
    r = propor(cand, estimativa=est, agora="2026-11-28T13:00:00Z")
    assert r["estado"] == "adiada"
    # after 7 days
    r2 = propor(cand, estimativa=est, agora="2026-12-10T13:00:00Z")
    assert r2["estado"] == "pendente"


def test_sem_tokens_atalho(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=None, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    assert res["estado"] == "pendente"
    va = res["vantagem_estimada"]
    assert va["economia_semana_tokens"] == "sem medição"


def test_check_sem_caminho(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    check = json.loads((FIX / "check_gerar_script.json").read_text())
    res = propor(cand, estimativa=est, check=check, agora="2026-11-27T13:00:00Z")
    assert res["estado"] == "pendente"
    assert res["caminho"] == "script novo"
    # ia degrau
    check2 = {"degrau": "ia", "motivo": "sem caminho", "robots": {"permitido": True}}
    r2 = propor(cand, estimativa=est, check=check2, agora="2026-11-27T13:00:00Z", repropor=True)
    # cand already pendente? Actually first propose inserted. Use new fp
    cand2 = dict(cand)
    cand2["impressao_digital"] = "fp9"
    r3 = propor(cand2, estimativa=est, check=check2, agora="2026-11-27T13:00:00Z")
    assert r3["estado"] == "sem_caminho"


def test_privacidade(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    cand = _cand()
    cand["alvo"] = "https://api.exemplo.test/itens?token=abc"
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "nao", nota="api_key=XYZ", agora="2026-11-27T13:00:00Z")
    # check db
    import sqlite3

    conn = sqlite3.connect(str(home / "atalhar.db"))
    rows = conn.execute("SELECT alvo, nota FROM propostas JOIN decisoes ON propostas.id=decisoes.proposta_id").fetchall()
    for r in rows:
        for v in r:
            if v:
                assert "token=abc" not in str(v)
                assert "api_key=XYZ" not in str(v)
    # sanitize_url removes query
    assert "?" not in res["alvo"]
    conn.close()


def test_sem_rede_socket(monkeypatch, tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")

    def boom(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(socket, "socket", boom)
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    assert res["estado"] == "pendente"


def test_cli_ponta_a_ponta(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    db = home / "atalhar.db"
    init_db(db)
    fp = "fp1"
    for i in range(5):
        log_execucao({"tipo": "consultar", "alvo": "https://api.exemplo.test/itens", "impressao_digital": fp,
                      "tokens_entrada": 1200, "tokens_saida": 40, "tokens_cache": 0,
                      "ts": f"2026-11-13T10:00:0{i}Z", "origem": "ia"}, path=db)
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    # detect
    proc = subprocess.run([sys.executable, "-m", "atalhar", "detect", "--json", "--ate", "2026-11-17T12:00:00Z"],
                          capture_output=True, text=True, env=env)
    det = json.loads(proc.stdout)
    cand = det["candidatos"][0]
    import json as _j

    p = subprocess.run([sys.executable, "-m", "atalhar", "propose", "--stdin",
                        "--tokens-atalho", "150", "--tokens-criacao", "4000",
                        "--ate", "2026-11-17T12:00:00Z", "--json"],
                       input=_j.dumps(cand), capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    obj = json.loads(p.stdout)
    assert set(["id", "estado", "pergunta_ao_usuario", "opcoes", "comando_decisao", "vantagem_estimada"]).issubset(obj.keys())
    assert obj["vantagem_estimada"].get("origem") is not None
    pid = obj["id"]
    # decide nunca
    d = subprocess.run([sys.executable, "-m", "atalhar", "decide", pid, "nunca", "--json"],
                       capture_output=True, text=True, env=env)
    assert d.returncode == 0
    # repropose -> 1
    p2 = subprocess.run([sys.executable, "-m", "atalhar", "propose", "--stdin",
                         "--tokens-atalho", "150", "--ate", "2026-11-17T12:00:00Z", "--json"],
                        input=_j.dumps(cand), capture_output=True, text=True, env=env)
    assert p2.returncode == 1


def test_execucoes_inalterada(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    os.environ["ATALHAR_HOME"] = str(home)
    init_db(home / "atalhar.db")
    # schema snapshot
    import sqlite3

    conn = sqlite3.connect(str(home / "atalhar.db"))
    before = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='execucoes'").fetchone()
    conn.close()
    cand = _cand()
    from atalhar.estimate import estimar

    est = estimar(cand, dias=14, tokens_atalho=150, tokens_criacao=4000)
    res = propor(cand, estimativa=est, agora="2026-11-27T13:00:00Z")
    pid = res["id"]
    decidir(pid, "sim", agora="2026-11-27T13:00:00Z")
    conn = sqlite3.connect(str(home / "atalhar.db"))
    after = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='execucoes'").fetchone()
    count = conn.execute("SELECT COUNT(*) FROM execucoes").fetchone()[0]
    conn.close()
    assert before == after
    assert count == 0


def test_help_code0():
    r = subprocess.run([sys.executable, "-m", "atalhar", "propose", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    r2 = subprocess.run([sys.executable, "-m", "atalhar", "decide", "--help"],
                        capture_output=True, text=True)
    assert r2.returncode == 0