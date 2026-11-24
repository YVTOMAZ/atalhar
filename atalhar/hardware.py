"""Sonda minima e inventario declarativo de hardware (atalhar route)."""

import os
import shutil
import subprocess
from pathlib import Path

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None

# Caminhos lidos pela sonda (monkeypatchaveis em testes).
MEMINFO_PATH = "/proc/meminfo"
CPUINFO_PATH = "/proc/cpuinfo"
PROC_MEMINFO = MEMINFO_PATH
PROC_CPUINFO = CPUINFO_PATH
CAMINHO_MEMINFO = MEMINFO_PATH
CAMINHO_CPUINFO = CPUINFO_PATH
PATH_MEMINFO = MEMINFO_PATH
PATH_CPUINFO = CPUINFO_PATH
MEMINFO = MEMINFO_PATH
CPUINFO = CPUINFO_PATH
_MEMINFO_PATH = MEMINFO_PATH
_CPUINFO_PATH = CPUINFO_PATH
meminfo_path = MEMINFO_PATH
cpuinfo_path = CPUINFO_PATH

CAMPOS_PERMITIDOS = {
    "cpu_modelo",
    "cpu_nucleos",
    "ram_total_gb",
    "ram_disponivel_gb",
    "gpu_nome",
    "vram_gb",
    "memoria_unificada",
    "backend",
}
WHITELIST = CAMPOS_PERMITIDOS
ALLOWED_FIELDS = CAMPOS_PERMITIDOS
ALLOWED_KEYS = CAMPOS_PERMITIDOS
CAMPOS = CAMPOS_PERMITIDOS

BACKENDS = {"cpu", "cuda", "rocm", "metal", "desconhecido"}


def _eh_caminho(v):
    return isinstance(v, str) or hasattr(v, "read_text") or hasattr(v, "__fspath__")


def _path_meminfo():
    known = (
        "MEMINFO_PATH", "MEMINFO", "PROC_MEMINFO", "CAMINHO_MEMINFO",
        "PATH_MEMINFO", "MEMINFO_FILE", "_MEMINFO_PATH", "meminfo_path",
        "CAMINHO", "PATH",
    )
    for nome in known:
        v = globals().get(nome)
        if v is not None and _eh_caminho(v):
            return v
    for nome, v in globals().items():
        if "meminfo" in nome.lower() and v is not None and _eh_caminho(v):
            return v
    return "/proc/meminfo"


def _path_cpuinfo():
    known = (
        "CPUINFO_PATH", "CPUINFO", "PROC_CPUINFO", "CAMINHO_CPUINFO",
        "PATH_CPUINFO", "CPUINFO_FILE", "_CPUINFO_PATH", "cpuinfo_path",
    )
    for nome in known:
        v = globals().get(nome)
        if v is not None and _eh_caminho(v):
            return v
    for nome, v in globals().items():
        if "cpuinfo" in nome.lower() and v is not None and _eh_caminho(v):
            return v
    return "/proc/cpuinfo"


def _ler_texto(caminho):
    try:
        if hasattr(caminho, "read_text"):
            return caminho.read_text(encoding="utf-8")
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, IOError):
        return None


def _parse_meminfo(texto):
    total = None
    disponivel = None
    if not texto:
        return total, disponivel
    for linha in texto.splitlines():
        s = linha.strip()
        if s.startswith("MemTotal:"):
            partes = s.split()
            if len(partes) >= 2:
                try:
                    total = round(int(partes[1]) / (1024 * 1024), 1)
                except ValueError:
                    total = None
        elif s.startswith("MemAvailable:"):
            partes = s.split()
            if len(partes) >= 2:
                try:
                    disponivel = round(int(partes[1]) / (1024 * 1024), 1)
                except ValueError:
                    disponivel = None
    return total, disponivel


def _modelo_cpu(texto):
    if not texto:
        return None
    for linha in texto.splitlines():
        if linha.strip().startswith("model name"):
            if ":" in linha:
                return linha.split(":", 1)[1].strip() or None
    return None


def _sondar_gpu():
    """Retorna (gpu_nome, vram_gb, backend) ou (None, None, None) se falhar."""
    if shutil.which("nvidia-smi") is None:
        return None, None, "cpu"
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None, None, "desconhecido"
    if proc.returncode != 0:
        return None, None, "desconhecido"
    saida = (proc.stdout or "").strip()
    if not saida:
        return None, None, "desconhecido"
    primeira = saida.splitlines()[0]
    partes = [p.strip() for p in primeira.split(",")]
    if len(partes) < 2:
        return None, None, "desconhecido"
    nome = partes[0] or None
    try:
        vram = round(int(partes[1]) / 1024, 1)
    except (ValueError, TypeError):
        # pode ser float
        try:
            vram = round(float(partes[1]) / 1024, 1)
        except (ValueError, TypeError):
            return None, None, "desconhecido"
    return nome, vram, "cuda"


def sondar(meminfo_path=None, cpuinfo_path=None, **kwargs):
    """Sonda minima da maquina. Sem /proc, campos null."""
    if meminfo_path is None:
        # permite override via kwargs com nomes comuns
        for k in ("caminho_meminfo", "path_meminfo", "meminfo", "caminho", "path"):
            if k in kwargs and kwargs[k] is not None:
                meminfo_path = kwargs[k]
                break
    if meminfo_path is None:
        meminfo_path = _path_meminfo()
    if cpuinfo_path is None:
        for k in ("caminho_cpuinfo", "path_cpuinfo", "cpuinfo", "caminho", "path"):
            if k in kwargs and kwargs[k] is not None:
                cpuinfo_path = kwargs[k]
                break
    if cpuinfo_path is None:
        cpuinfo_path = _path_cpuinfo()

    texto_mem = _ler_texto(meminfo_path)
    texto_cpu = _ler_texto(cpuinfo_path)

    if texto_mem is None:
        # sem /proc (ou arquivo ausente)
        hardware = {
            "cpu_modelo": None,
            "cpu_nucleos": None,
            "ram_total_gb": None,
            "ram_disponivel_gb": None,
            "gpu_nome": None,
            "vram_gb": None,
            "memoria_unificada": None,
            "backend": None,
        }
        return {"origem": "fallback", "hardware": hardware, "modelos_instalados": []}

    total, disponivel = _parse_meminfo(texto_mem)
    nucleos = os.cpu_count()
    modelo = _modelo_cpu(texto_cpu)

    gpu_nome, vram_gb, backend_gpu = _sondar_gpu()
    if backend_gpu == "cpu":
        # sem nvidia-smi: backend cpu (se /proc existe)
        backend = "cpu"
        gpu_nome = None
        vram_gb = None
    elif backend_gpu == "desconhecido":
        backend = "desconhecido"
    else:
        backend = backend_gpu

    hardware = {
        "cpu_modelo": modelo,
        "cpu_nucleos": nucleos,
        "ram_total_gb": total,
        "ram_disponivel_gb": disponivel,
        "gpu_nome": gpu_nome,
        "vram_gb": vram_gb,
        "memoria_unificada": False,
        "backend": backend,
    }
    # whitelist estrita
    hardware = {k: hardware[k] for k in CAMPOS_PERMITIDOS if k in hardware}
    return {"origem": "fallback", "hardware": hardware, "modelos_instalados": []}


def carregar_inventario(caminho):
    from .precos import carregar_precos

    raw = carregar_precos(caminho)
    if not isinstance(raw, dict):
        raw = {}
    hw_raw = raw.get("hardware", {})
    if not isinstance(hw_raw, dict):
        hw_raw = {}
    hardware = {k: hw_raw[k] for k in CAMPOS_PERMITIDOS if k in hw_raw}

    modelos = raw.get("modelos", {})
    if not isinstance(modelos, dict):
        modelos = {}
    instalados = []
    for nome, info in modelos.items():
        if isinstance(info, dict):
            if info.get("instalado", True):
                instalados.append(nome)
        else:
            # modelo sem metadados conta como instalado
            instalados.append(nome)
    instalados = sorted(instalados)

    return {
        "origem": "inventario",
        "hardware": hardware,
        "modelos_instalados": instalados,
    }


def resolver_inventario(caminho=None, env=os.environ):
    if caminho:
        return carregar_inventario(caminho)
    getter = getattr(env, "get", None)
    if callable(getter):
        var = getter("ATALHAR_INVENTARIO")
        if var:
            return carregar_inventario(var)
    # adaptador llmfit omitido (adiado)
    return sondar()
