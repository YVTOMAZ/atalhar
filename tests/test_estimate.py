import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from atalhar.estimate import estimar
from atalhar.ledger import init_db, log_execucao

ROOT = Path(__file__).resolve().parents[1]


def _cand(**kw):
    base = {
        "impressao_digital": "fp1",
        "ocorrencias": 3,
        "tokens_entrada_medio": 1000,
        "tokens_saida_medio": 200,
        "tokens_cache_medio": 0,
    }
    base.update(kw)
    return base


def test_caso_base_tokens():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=100, tokens_criacao=3000)
    assert r["custo_ia_exec"] == 1200
    assert r["execucoes_semana"] == 1.5
    sc = r["cenarios"][0]
    assert sc["economia_exec"] == 1100
    assert sc["economia_semana"] == 1650
    assert sc["retorno_execucoes"] == math.ceil(3000 / 1100)


def test_cenario_quebra():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=100, tokens_criacao=3000,
                tokens_reparo=3000, cenarios=(0.3,))
    q = 0.3
    esperado = (1 - q) * 100 + q * (1200 + 3000)
    sc = r["cenarios"][0]
    assert sc["custo_atalho_exec"] == esperado


def test_nao_compensa():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=1200, tokens_criacao=3000)
    sc = r["cenarios"][0]
    assert sc["retorno_execucoes"] is None
    assert sc["motivo"] == "nao_compensa"


def test_sem_tokens_criacao():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=100)
    sc = r["cenarios"][0]
    assert sc["economia_exec"] == 1100
    assert sc["retorno_execucoes"] is None


def test_sem_precos_e_precos_zero():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=100)
    sc = r["cenarios"][0]
    assert sc["dinheiro"] is None
    assert r["preco"] is None
    # precos todos zero
    r2 = estimar(c, dias=14, tokens_atalho=100,
                 precos_modelo={"entrada": 0, "saida": 0, "cache": 0,
                                "consultado_em": "AAAA-MM-DD", "moeda": "USD"})
    assert r2["metrica_principal"] == "tokens"


def test_com_precos_sinteticos():
    c = _cand()
    pm = {"entrada": 1.0, "saida": 2.0, "cache": 0.5}
    r = estimar(c, dias=14, tokens_atalho=100, precos_modelo=pm)
    sc = r["cenarios"][0]
    esperado = 1000 * 1.0 / 1e6 + 200 * 2.0 / 1e6 + 0 * 0.5 / 1e6
    assert sc["dinheiro"]["custo_ia_exec"] == pytest.approx(esperado)


def test_cota():
    c = _cand()
    r = estimar(c, dias=14, tokens_atalho=100, cota_semanal_tokens=100000)
    sc = r["cenarios"][0]
    assert sc["pct_cota"]["ia"] == pytest.approx(1200 * 1.5 / 100000 * 100)
    r2 = estimar(c, dias=14, tokens_atalho=100, cota_semanal_tokens=0)
    assert r2["cenarios"][0]["pct_cota"] is None


def test_incluir_cache():
    c = _cand(tokens_cache_medio=50)
    r_off = estimar(c, dias=14, tokens_atalho=100, incluir_cache=False)
    r_on = estimar(c, dias=14, tokens_atalho=100, incluir_cache=True)
    assert r_off["custo_ia_exec"] == 1200
    assert r_on["custo_ia_exec"] == 1250


def test_validacao_cli(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    # tokens_atalho negativo
    proc = subprocess.run([sys.executable, "-m", "atalhar", "estimate", "fp",
                           "--tokens-atalho", "-1"], capture_output=True, text=True, env=env)
    assert proc.returncode == 2
    # cenarios invalido
    proc2 = subprocess.run([sys.executable, "-m", "atalhar", "estimate", "fp",
                            "--tokens-atalho", "10", "--cenarios", "1"],
                           capture_output=True, text=True, env=env)
    assert proc2.returncode == 2


def test_cli_ponta_a_ponta(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    db = home / "atalhar.db"
    from atalhar.ledger import init_db, log_execucao
    init_db(db)
    fp = "fp1"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 1000, "tokens_saida": 200, "tokens_cache": 0,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    # fixar --ate
    proc = subprocess.run([sys.executable, "-m", "atalhar", "estimate", fp,
                           "--tokens-atalho", "100", "--dias", "14",
                           "--ate", "2026-11-16T12:00:00Z", "--json"],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    obj = json.loads(proc.stdout)
    expected_keys = {"impressao_digital", "entradas", "metrica_principal",
                     "custo_ia_exec", "execucoes_semana", "cenarios", "preco", "avisos"}
    assert set(obj.keys()) == expected_keys
    sc = obj["cenarios"][0]
    assert set(sc.keys()) == {"q", "custo_atalho_exec", "economia_exec",
                             "economia_semana", "retorno_execucoes", "motivo",
                             "dinheiro", "pct_cota"}


def test_fp_inexistente_code2(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    db = home / "atalhar.db"
    from atalhar.ledger import init_db, log_execucao
    init_db(db)
    fp = "fp1"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    proc = subprocess.run([sys.executable, "-m", "atalhar", "estimate", "nope",
                           "--tokens-atalho", "100", "--ate", "2026-11-16T12:00:00Z"],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 2


def test_stdin_mesmo_resultado(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    db = home / "atalhar.db"
    from atalhar.ledger import init_db, log_execucao
    init_db(db)
    fp = "fp1"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 1000, "tokens_saida": 200, "tokens_cache": 0,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    proc = subprocess.run([sys.executable, "-m", "atalhar", "detect", "--json",
                           "--ate", "2026-11-16T12:00:00Z"],
                          capture_output=True, text=True, env=env)
    det = json.loads(proc.stdout)
    cand = det["candidatos"][0]
    import json as _j
    p2 = subprocess.run([sys.executable, "-m", "atalhar", "estimate", "--stdin",
                         "--tokens-atalho", "100", "--dias", "14",
                         "--ate", "2026-11-16T12:00:00Z", "--json"],
                        input=_j.dumps(cand), capture_output=True, text=True, env=env)
    assert p2.returncode == 0, p2.stderr
    # compare custo
    obj = json.loads(p2.stdout)
    assert obj["custo_ia_exec"] == 1200


def test_somente_leitura_hash(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    db = home / "atalhar.db"
    from atalhar.ledger import init_db, log_execucao
    init_db(db)
    fp = "fp1"
    for i in range(3):
        log_execucao({"tipo": "consultar", "alvo": "https://x", "impressao_digital": fp,
                      "tokens_entrada": 10, "tokens_saida": 5,
                      "ts": f"2026-11-16T10:00:0{i}Z", "origem": "ia"}, path=db)
    import hashlib
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    env = {**os.environ, "ATALHAR_HOME": str(home)}
    subprocess.run([sys.executable, "-m", "atalhar", "estimate", fp,
                    "--tokens-atalho", "100", "--ate", "2026-11-16T12:00:00Z"],
                   capture_output=True, text=True, env=env)
    after = hashlib.sha256(db.read_bytes()).hexdigest()
    assert before == after


def test_help_code0():
    import subprocess, sys
    r = subprocess.run([sys.executable, "-m", "atalhar", "estimate", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0