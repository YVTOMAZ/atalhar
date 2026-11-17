import os
import sys
import tempfile
from pathlib import Path

import pytest

from atalhar.precos import carregar_precos

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "precos.example.toml"


def test_example_no_real_prices():
    data = carregar_precos(EXAMPLE)
    modelos = data.get("modelos", {})
    for m, info in modelos.items():
        assert info.get("entrada", 0) == 0
        assert info.get("saida", 0) == 0
        assert info.get("cache", 0) == 0
        assert info.get("consultado_em") == "AAAA-MM-DD"


def test_minimal_equals_tomllib():
    try:
        import tomllib
    except Exception:
        pytest.skip("tomllib indisponivel")
    # usa leitor minimo forcando
    from atalhar import precos
    text = EXAMPLE.read_text(encoding="utf-8")
    # chama _minimal_load diretamente
    got = precos._minimal_load(text)
    expected = tomllib.loads(text)
    assert got == expected


def test_minimal_invalid_syntax_line():
    from atalhar import precos
    # array
    with pytest.raises(ValueError) as e:
        precos._minimal_load('a = [1, 2]\n')
    assert "linha" in str(e.value)
    # inline table
    with pytest.raises(ValueError) as e:
        precos._minimal_load('a = {b = 1}\n')
    assert "linha" in str(e.value)
    # multiline string
    with pytest.raises(ValueError) as e:
        precos._minimal_load('a = """x"""\n')
    assert "linha" in str(e.value)


def test_carregar_precos_basic(tmp_path):
    p = tmp_path / "precos.toml"
    p.write_text('[geral]\nmoeda = "BRL"\n\n[modelos."m"]\nconsultado_em = "2026-01-01"\nentrada = 1.5\nsaida = 2\n cache = 0.5\n', encoding="utf-8")
    data = carregar_precos(p)
    assert data["geral"]["moeda"] == "BRL"
    assert data["modelos"]["m"]["entrada"] == 1.5
    assert data["modelos"]["m"]["saida"] == 2


def test_carregar_precos_310_fallback(monkeypatch):
    # forca tomllib None
    import atalhar.precos as pr
    monkeypatch.setattr(pr, "tomllib", None)
    data = pr.carregar_precos(EXAMPLE)
    assert "modelos" in data