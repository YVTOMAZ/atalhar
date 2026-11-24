import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from atalhar import hardware
from atalhar.hardware import (
    CAMPOS_PERMITIDOS,
    carregar_inventario,
    resolver_inventario,
    sondar,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "inventario_sintetico.toml"


def test_1_carregar_inventario_basico():
    inv = carregar_inventario(FIXTURE)
    assert inv["origem"] == "inventario"
    hw = inv["hardware"]
    assert hw["ram_total_gb"] == 16
    assert hw["vram_gb"] == 0
    assert hw["backend"] == "cpu"
    assert inv["modelos_instalados"] == ["gemma4", "qwen2.5-coder:7b"]
    assert set(hw.keys()).issubset(CAMPOS_PERMITIDOS)


def test_2_minimal_loader_forcado(monkeypatch):
    import atalhar.precos as pr

    monkeypatch.setattr(pr, "tomllib", None)
    inv = carregar_inventario(FIXTURE)
    assert inv["modelos_instalados"] == ["gemma4", "qwen2.5-coder:7b"]
    assert inv["hardware"]["ram_total_gb"] == 16


def test_3_env_var_e_precedencia(tmp_path, monkeypatch):
    monkeypatch.setenv("ATALHAR_INVENTARIO", str(FIXTURE))
    inv = resolver_inventario()
    assert inv["origem"] == "inventario"
    # argumento explicito vence
    other = tmp_path / "outro.toml"
    other.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    inv2 = resolver_inventario(str(other))
    assert inv2["origem"] == "inventario"


def test_4_sonda_fallback_sem_nvidia(monkeypatch, tmp_path):
    monkeypatch.setattr(hardware.shutil, "which", lambda x: None)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       16777216 kB\nMemAvailable:    8388608 kB\n", encoding="utf-8"
    )
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("model name\t: Test CPU\n", encoding="utf-8")
    monkeypatch.setattr(hardware, "MEMINFO_PATH", str(meminfo))
    monkeypatch.setattr(hardware, "CPUINFO_PATH", str(cpuinfo))
    inv = sondar()
    assert inv["origem"] == "fallback"
    hw = inv["hardware"]
    assert hw["ram_total_gb"] == 16.0
    assert hw["ram_disponivel_gb"] == 8.0
    assert hw["vram_gb"] in (None, 0)


def test_5_sem_proc_meminfo(monkeypatch, tmp_path):
    monkeypatch.setattr(hardware.shutil, "which", lambda x: None)
    missing = tmp_path / "nope-meminfo"
    monkeypatch.setattr(hardware, "MEMINFO_PATH", str(missing))
    inv = sondar()
    assert inv["origem"] == "fallback"
    hw = inv["hardware"]
    assert hw["ram_total_gb"] is None
    assert hw["cpu_nucleos"] is None or hw["cpu_nucleos"] == os.cpu_count()


def test_6_nvidia_smoke(monkeypatch):
    def fake_which(x):
        return "/usr/bin/nvidia-smi" if x == "nvidia-smi" else None

    monkeypatch.setattr(hardware.shutil, "which", fake_which)

    class Proc:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 3060, 12288\n"
        stderr = ""

    monkeypatch.setattr(hardware.subprocess, "run", lambda *a, **k: Proc())
    meminfo = None
    # forcar /proc existente via monkeypatch de _ler_texto? use real /proc
    inv = sondar()
    hw = inv["hardware"]
    assert hw["gpu_nome"] == "NVIDIA GeForce RTX 3060"
    assert hw["vram_gb"] == 12.0
    assert hw["backend"] == "cuda"

    # erro/timeout
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5)

    monkeypatch.setattr(hardware.subprocess, "run", boom)
    inv2 = sondar()
    assert inv2["hardware"]["backend"] == "desconhecido"


def test_7_sem_rede(monkeypatch):
    def fail_socket(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(socket, "socket", fail_socket)
    # nao deve quebrar
    inv = carregar_inventario(FIXTURE)
    assert inv["origem"] == "inventario"


def test_8_json_cli_estavel(tmp_path):
    cmd = [sys.executable, "-m", "atalhar", "route", "inventariar",
           "--inventario", str(FIXTURE), "--json"]
    r1 = subprocess.run(cmd, capture_output=True, text=True)
    r2 = subprocess.run(cmd, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    assert r1.stdout == r2.stdout
    obj = json.loads(r1.stdout)
    assert "aviso" in obj
    assert "recomendacao, nao medicao" in obj["aviso"]
    assert set(obj["hardware"].keys()).issubset(CAMPOS_PERMITIDOS)


def test_9_sem_hostname(tmp_path, monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda x: None)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16777216 kB\nMemAvailable:    8388608 kB\n", encoding="utf-8")
    monkeypatch.setattr(hardware, "MEMINFO_PATH", str(meminfo))
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("model name\t: Test CPU\n", encoding="utf-8")
    monkeypatch.setattr(hardware, "CPUINFO_PATH", str(cpuinfo))
    # roda CLI com sonda
    r = subprocess.run([sys.executable, "-m", "atalhar", "route", "inventariar", "--json"],
                       capture_output=True, text=True)
    # pode falhar por /proc ausente? mas nao deve conter hostname
    host = socket.gethostname()
    home = os.path.expanduser("~")
    assert host not in r.stdout
    assert home not in r.stdout


def test_10_toml_invalido_code2(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("isto nao e toml valido [[[", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "atalhar", "route", "inventariar",
                        "--inventario", str(bad)], capture_output=True, text=True)
    assert r.returncode == 2


def test_11_route_sem_subcomando_code2():
    r = subprocess.run([sys.executable, "-m", "atalhar", "route"], capture_output=True, text=True)
    assert r.returncode == 2


def test_12_antigos_continuam():
    # smoke: importa modulos
    import atalhar.cli  # noqa
    assert True
