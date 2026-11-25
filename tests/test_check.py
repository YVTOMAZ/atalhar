import json
import os
import shutil
from pathlib import Path

import pytest

from atalhar import __version__
from atalhar.check import check

ROOT = Path(__file__).resolve().parents[1]


def _robots_disallow():
    return lambda url, headers: (
        (404, {}, b"") if url.endswith("/robots.txt") else (200, {"Content-Type": "text/html"}, b"<html></html>")
    )


def test_ferramenta_instalada(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gh")
    r = check("gh", buscador=lambda u, h: (200, {}, b""))
    assert r["degrau"] == "ferramenta"
    assert r["ferramenta"]["instalada"] is True
    assert r["ferramenta"]["doc"] == "https://cli.github.com/manual/"
    # buscador nao chamado
    calls = {"n": 0}

    def buscador(u, h):
        calls["n"] += 1
        return (200, {}, b"")

    check("gh", buscador=buscador)
    assert calls["n"] == 0


def test_url_casa_ferramenta_por_host(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/gh")
    calls = {"n": 0}

    def buscador(u, h):
        calls["n"] += 1
        return (200, {}, b"")

    r = check("https://api.github.com/repos/x/y", buscador=buscador)
    assert r["degrau"] == "ferramenta"
    assert calls["n"] == 0


def test_ferramenta_nao_instalada(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda x: None)
    r = check("gh")
    assert r["degrau"] == "ferramenta"
    assert r["ferramenta"]["instalada"] is False


def test_sinal_rss():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head></html>')

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["sinais"] == [{"tipo": "rss", "url": "https://exemplo.test/feed.xml"}]


def test_sinal_json_ld():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b'<html><head><script type="application/ld+json">{}</script></head></html>')

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert any(s["tipo"] == "json_ld" for s in r["sinais"])


def test_sinal_sitemap():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (200, {}, b"User-agent: *\nDisallow:\nSitemap: https://exemplo.test/sitemap.xml\n")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["sinais"] == [{"tipo": "sitemap", "url": "https://exemplo.test/sitemap.xml"}]


def test_sinal_sitemap_relativo():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (200, {}, b"User-agent: *\nDisallow:\nSitemap: /sitemap.xml\n")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["sinais"] == [{"tipo": "sitemap", "url": "https://exemplo.test/sitemap.xml"}]


def test_sinal_sitemap_protocol_relative():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (200, {}, b"User-agent: *\nDisallow:\nSitemap: //cdn.exemplo.test/sitemap.xml\n")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["sinais"] == [{"tipo": "sitemap", "url": "https://cdn.exemplo.test/sitemap.xml"}]


def test_robots_disallow_ia():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (200, {}, b"User-agent: *\nDisallow: /produtos\n")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["degrau"] == "ia"
    assert r["robots"]["permitido"] is False
    assert r["degrau"] != "gerar_script"


def test_robots_404_gerar_script():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["robots"]["permitido"] is True
    assert r["degrau"] == "gerar_script"


def test_robots_503_ia():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (503, {}, b"")
        return (200, {}, b"")

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["robots"]["permitido"] is False
    assert r["degrau"] == "ia"
    assert r["motivo"]


def test_sem_rede():
    calls = {"n": 0}

    def buscador(url, headers):
        calls["n"] += 1
        return (200, {}, b"")

    r = check("https://exemplo.test/produtos", buscador=buscador, sem_rede=True)
    assert r["degrau"] == "ia"
    assert calls["n"] == 0


def test_ua():
    seen = []

    def buscador(url, headers):
        seen.append(dict(headers))
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    check("https://exemplo.test/produtos", buscador=buscador)
    assert seen[0]["User-Agent"] == f"atalhar/{__version__} (+https://github.com/YVTOMAZ/atalhar)"
    assert seen[1]["User-Agent"] == f"atalhar/{__version__} (+https://github.com/YVTOMAZ/atalhar)"


def test_max_duas_requisicoes():
    calls = {"n": 0}

    def buscador(url, headers):
        calls["n"] += 1
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    check("https://exemplo.test/produtos", buscador=buscador)
    assert calls["n"] <= 2


def test_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ATALHAR_HOME", str(tmp_path))
    calls = {"n": 0}

    def buscador(url, headers):
        calls["n"] += 1
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        if calls["n"] == 2:
            return (200, {"ETag": '"abc"', "Content-Type": "text/html"}, b"<html></html>")
        return (304, {}, b"")

    r1 = check("https://exemplo.test/produtos", buscador=buscador)
    r2 = check("https://exemplo.test/produtos", buscador=buscador)
    assert r2["degrau"] == r1["degrau"]
    # segundo envio tem If-None-Match
    # (buscador chamado 4 vezes: 2 por rodada)
    # cache file sem corpo/query
    cache = json.loads((tmp_path / "cache_check.json").read_text())
    assert "https://exemplo.test/produtos" in cache
    assert "corpo" not in json.dumps(cache)
    assert not any("?" in k for k in cache.keys())


def test_url_credenciais():
    with pytest.raises(ValueError):
        check("https://user:senha@exemplo.test/x")
    # cli
    import subprocess, sys
    # ensure no buscador call
    calls = {"n": 0}

    def buscador(u, h):
        calls["n"] += 1
        return (200, {}, b"")

    try:
        check("https://user:senha@exemplo.test/x", buscador=buscador)
    except ValueError:
        pass
    assert calls["n"] == 0


def test_query_string_saida():
    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, b"<html></html>")

    r = check("https://exemplo.test/produtos?token=abc", buscador=buscador)
    out = json.dumps(r)
    assert "token=abc" not in out
    assert r["alvo"] == "https://exemplo.test/produtos"


def test_corpo_grande():
    big = b"<html>" + b"a" * (600 * 1024) + b"</html>"

    def buscador(url, headers):
        if url.endswith("/robots.txt"):
            return (404, {}, b"")
        return (200, {"Content-Type": "text/html"}, big)

    r = check("https://exemplo.test/produtos", buscador=buscador)
    assert r["degrau"] in ("gerar_script", "dado_estruturado")


def test_catalogo_minimal(monkeypatch):
    import atalhar.precos as pr

    monkeypatch.setattr(pr, "tomllib", None)
    import shutil as sh

    monkeypatch.setattr(sh, "which", lambda x: None)
    r = check("gh")
    assert r["ferramenta"]["comando"] == "gh"


def test_cli_json():
    import subprocess, sys
    res = subprocess.run(
        [sys.executable, "-m", "atalhar.cli", "check", "gh", "--json"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert set(data.keys()) >= {"alvo", "degrau", "ferramenta", "sinais", "robots", "requisicoes", "proximo_passo", "motivo", "versao"}