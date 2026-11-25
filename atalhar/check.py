"""Escada `atalhar check`: existe caminho mais barato antes de gastar?"""

import html.parser
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

from . import __version__
from .fingerprint import sanitize_url

try:
    import atalhar.precos as _precos_mod
except Exception:  # pragma: no cover
    _precos_mod = None

try:
    from atalhar.precos import _minimal_load as _minimal_load_precos
except Exception:  # pragma: no cover
    _minimal_load_precos = None


def _tomllib_atual():
    if _precos_mod is not None and hasattr(_precos_mod, "tomllib"):
        return _precos_mod.tomllib
    try:
        import tomllib

        return tomllib
    except Exception:
        return None


def _parse_toml(text):
    tl = _tomllib_atual()
    if tl is not None:
        try:
            import io

            return tl.loads(text)
        except Exception as e:
            if _minimal_load_precos is not None:
                try:
                    return _minimal_load_precos(text)
                except ValueError:
                    pass
            raise ValueError(str(e))
    if _minimal_load_precos is not None:
        return _minimal_load_precos(text)
    raise ValueError("tomllib indisponivel")


def _ler_catalogo_padrao():
    try:
        from importlib.resources import files

        return files("atalhar").joinpath("dados/ferramentas.toml").read_text(encoding="utf-8")
    except Exception:
        base = Path(__file__).resolve().parent
        return (base / "dados" / "ferramentas.toml").read_text(encoding="utf-8")


def _carregar_catalogo(catalogo):
    if catalogo is None:
        text = _ler_catalogo_padrao()
        data = _parse_toml(text)
    elif isinstance(catalogo, dict):
        data = catalogo
    elif isinstance(catalogo, (str, Path, os.PathLike)):
        p = Path(catalogo)
        if not p.exists():
            raise ValueError(f"catalogo nao encontrado: {catalogo}")
        data = _parse_toml(p.read_text(encoding="utf-8"))
    else:
        if hasattr(catalogo, "read"):
            data = _parse_toml(catalogo.read())
        else:
            raise ValueError("catalogo invalido")
    if not isinstance(data, dict):
        raise ValueError("catalogo invalido")
    return data


def _entradas_catalogo(data):
    out = {}
    order = []
    if not isinstance(data, dict):
        return out, order
    ferr = data.get("ferramenta")
    if isinstance(ferr, dict):
        for k, v in ferr.items():
            if isinstance(v, dict) and "comando" in v:
                if k not in out:
                    out[k] = v
                    order.append(k)
    for k, v in data.items():
        if isinstance(v, dict) and "comando" in v:
            name = str(k).split(".")[-1]
            if name not in out:
                out[name] = v
                order.append(name)
    return out, order


def _match_ferramenta(alvo_str, tipo, data):
    entries, order = _entradas_catalogo(data)
    is_url = "://" in alvo_str
    if is_url:
        host = urllib.parse.urlsplit(alvo_str).hostname
        if not host:
            return None
        for name in order:
            info = entries[name]
            if tipo:
                tipos = [t.strip() for t in str(info.get("tipos", "")).split(",") if t.strip()]
                if tipo not in tipos:
                    continue
            hosts = [h.strip() for h in str(info.get("hosts", "")).split(",") if h.strip()]
            if host in hosts:
                return name, info
    else:
        for name in order:
            info = entries[name]
            if tipo:
                tipos = [t.strip() for t in str(info.get("tipos", "")).split(",") if t.strip()]
                if tipo not in tipos:
                    continue
            if str(info.get("comando", "")).strip() == alvo_str:
                return name, info
    return None


class _SinalParser(html.parser.HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base = base_url
        self.sinais = []

    def handle_starttag(self, tag, attrs):
        d = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "link":
            rel = d.get("rel", "")
            typ = d.get("type", "")
            href = d.get("href")
            if href and "alternate" in rel.split():
                if "rss" in typ:
                    self.sinais.append(("rss", urllib.parse.urljoin(self.base, href)))
                elif "atom" in typ:
                    self.sinais.append(("atom", urllib.parse.urljoin(self.base, href)))
                elif "json" in typ:
                    self.sinais.append(("json", urllib.parse.urljoin(self.base, href)))
        if tag == "script":
            typ = d.get("type", "")
            if typ == "application/ld+json":
                self.sinais.append(("json_ld", self.base))


def _fetch(buscador, url, headers):
    res = buscador(url, headers)
    if isinstance(res, (tuple, list)):
        status, hdrs, body = (list(res) + [None, None, None])[:3]
    else:
        status, hdrs, body = None, None, None
    if isinstance(hdrs, (list, tuple)):
        hdrs = {str(k): v for k, v in hdrs}
    if not isinstance(hdrs, dict):
        hdrs = {} if hdrs is None else dict(hdrs)
    if isinstance(body, str):
        body = body.encode("utf-8", errors="replace")
    elif body is None:
        body = b""
    else:
        body = bytes(body)
    if len(body) > 512 * 1024:
        body = body[: 512 * 1024]
    return status, hdrs, body


def _buscador_padrao(url, headers):
    # rejeita credenciais
    parts = urllib.parse.urlsplit(url)
    if parts.username or parts.password:
        raise ValueError("URL com credenciais nao permitida")
    if parts.scheme not in ("http", "https"):
        raise ValueError("esquema invalido")

    class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            count = getattr(req, "_redirect_count", 0) + 1
            if count > 3:
                raise urllib.error.HTTPError(newurl, code, "muitos redirecionamentos", hdrs, None)
            new_req = super().redirect_request(req, fp, code, msg, hdrs, newurl)
            if new_req is not None:
                new_req._redirect_count = count
            return new_req

    opener = urllib.request.build_opener(_LimitedRedirect)
    req = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
    req._redirect_count = 0
    try:
        with opener.open(req, timeout=10) as resp:
            status = resp.getcode()
            hdrs = dict(resp.headers)
            body = resp.read(512 * 1024 + 1)
            if len(body) > 512 * 1024:
                body = body[: 512 * 1024]
            return status, hdrs, body
    except urllib.error.HTTPError as e:
        body = e.read(512 * 1024)
        if len(body) > 512 * 1024:
            body = body[: 512 * 1024]
        return e.code, dict(e.headers or {}), body
    except Exception:
        raise


_rate_state = {}


def _rate_limit(host, crawl_delay):
    interval = 1.0
    if crawl_delay is not None:
        try:
            interval = max(interval, float(crawl_delay))
        except (TypeError, ValueError):
            pass
    now = time.monotonic()
    last = _rate_state.get(host)
    if last is not None:
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
    _rate_state[host] = time.monotonic()


def _cache_path():
    home = os.environ.get("ATALHAR_HOME")
    if not home:
        home = os.path.join(os.path.expanduser("~"), ".atalhar")
    return os.path.join(home, "cache_check.json")


def _carregar_cache():
    p = _cache_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _salvar_cache(cache):
    p = _cache_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def _header_get(headers, name):
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if str(k).lower() == name.lower():
            return v
    return None


def _avaliar_robots(status, body, ua, target_url):
    if status is None:
        return False, None, "erro de rede ao buscar robots.txt"
    if 400 <= status < 500:
        return True, None, None
    if status < 200 or status >= 500:
        return False, None, f"robots.txt retornou {status}"
    # 2xx/3xx
    try:
        text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    except Exception:
        text = ""
    lines = text.splitlines()
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(lines)
    except Exception:
        pass
    try:
        allowed = rp.can_fetch(ua, target_url)
    except Exception:
        allowed = True
    crawl_delay = None
    try:
        crawl_delay = rp.crawl_delay(ua)
    except Exception:
        crawl_delay = None
    if not allowed:
        return False, crawl_delay, "robots.txt nao permite este caminho"
    return True, crawl_delay, None


def _site_maps_from_body(body):
    out = []
    if not body:
        return out
    try:
        text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
    except Exception:
        return out
    lines = text.splitlines()
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(lines)
    except Exception:
        pass
    try:
        for sm in rp.site_maps() or []:
            out.append(sm)
    except Exception:
        pass
    # fallback regex
    if not out:
        for line in lines:
            m = re.match(r"\s*Sitemap:\s*(.+?)\s*$", line, re.IGNORECASE)
            if m:
                out.append(m.group(1).strip())
    return out


def check(alvo, *, buscador=None, catalogo=None, agora=None, sem_rede=False, tipo=None):
    if alvo is None:
        raise ValueError("alvo vazio")
    alvo_str = str(alvo).strip()
    if not alvo_str:
        raise ValueError("alvo vazio")

    is_url = "://" in alvo_str
    if is_url:
        parts = urllib.parse.urlsplit(alvo_str)
        if parts.username or parts.password:
            raise ValueError("URL com credenciais nao permitida")
        if not parts.hostname:
            raise ValueError("URL invalida")

    sem_rede = bool(sem_rede) or os.environ.get("ATALHAR_SEM_REDE") in ("1", "true", "sim", "yes", "True")

    catalogo_data = _carregar_catalogo(catalogo)

    if is_url:
        alvo_out = sanitize_url(alvo_str)
    else:
        alvo_out = alvo_str

    if buscador is None:
        buscador = _buscador_padrao

    ua = f"atalhar/{__version__} (+https://github.com/YVTOMAZ/atalhar)"

    # 1. ferramenta existente
    match = _match_ferramenta(alvo_str, tipo, catalogo_data)
    if match is not None:
        name, info = match
        comando = info.get("comando")
        instalada = shutil.which(comando) is not None
        doc = info.get("doc")
        exemplo = info.get("exemplo")
        return {
            "alvo": alvo_out,
            "degrau": "ferramenta",
            "ferramenta": {
                "nome": name,
                "comando": comando,
                "instalada": instalada,
                "doc": doc,
                "exemplo": exemplo,
            },
            "sinais": [],
            "robots": None,
            "requisicoes": 0,
            "proximo_passo": ("usar a ferramenta instalada" if instalada else f"instalar a ferramenta: {doc}"),
            "motivo": None,
            "versao": __version__,
        }

    # nao-URL, nao-ferramenta
    if not is_url:
        return {
            "alvo": alvo_out,
            "degrau": "ia",
            "ferramenta": None,
            "sinais": [],
            "robots": None,
            "requisicoes": 0,
            "proximo_passo": "continuar com a IA",
            "motivo": "alvo nao e URL nem ferramenta conhecida",
            "versao": __version__,
        }

    # sem rede
    if sem_rede:
        return {
            "alvo": alvo_out,
            "degrau": "ia",
            "ferramenta": None,
            "sinais": [],
            "robots": {"permitido": "desconhecido", "crawl_delay": None, "status_http": None},
            "requisicoes": 0,
            "proximo_passo": "continuar com a IA (sem rede)",
            "motivo": "sem rede (--sem-rede)",
            "versao": __version__,
        }

    # rate limit por execucao
    global _rate_state
    _rate_state = {}

    # rede
    host = parts.hostname
    cache = _carregar_cache()
    cache_key = sanitize_url(alvo_str)
    cached = cache.get(cache_key) if isinstance(cache.get(cache_key), dict) else None

    requisicoes = 0
    headers_base = {"User-Agent": ua}

    # robots.txt
    robots_url = f"{parts.scheme}://{host}"
    if parts.port:
        robots_url += f":{parts.port}"
    robots_url += "/robots.txt"

    _rate_limit(host, None)
    status_r = None
    headers_r = {}
    body_r = b""
    try:
        # conditional for robots? not cached separately; fetch directly
        status_r, headers_r, body_r = _fetch(buscador, robots_url, headers_base)
    except Exception:
        status_r, headers_r, body_r = None, {}, b""
    requisicoes += 1

    permitido, crawl_delay, motivo_robots = _avaliar_robots(status_r, body_r, ua, alvo_str)

    # sinais do robots (sitemap)
    sinais = []
    if body_r:
        for sm in _site_maps_from_body(body_r):
            sinais.append({"tipo": "sitemap", "url": sanitize_url(sm)})

    # se nao permitido, nao busca a pagina
    if not permitido:
        result = {
            "alvo": alvo_out,
            "degrau": "ia",
            "ferramenta": None,
            "sinais": sinais,
            "robots": {
                "permitido": False,
                "crawl_delay": crawl_delay,
                "status_http": status_r,
            },
            "requisicoes": requisicoes,
            "proximo_passo": "continuar com a IA (robots nao permite)",
            "motivo": motivo_robots or "robots.txt nao permite",
            "versao": __version__,
        }
        # cache? store
        _salvar_resultado_cache(cache, cache_key, None, None, result)
        return result

    # busca a pagina
    target_headers = dict(headers_base)
    if cached:
        if cached.get("etag"):
            target_headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            target_headers["If-Modified-Since"] = cached["last_modified"]

    _rate_limit(host, crawl_delay)
    status_t = None
    headers_t = {}
    body_t = b""
    try:
        status_t, headers_t, body_t = _fetch(buscador, alvo_str, target_headers)
    except Exception:
        status_t, headers_t, body_t = None, {}, b""
    requisicoes += 1

    # 304 -> reusa cache
    if status_t == 304 and cached and isinstance(cached.get("resultado"), dict):
        cached_res = dict(cached["resultado"])
        # keep requisicoes? use cached requisicoes maybe; update to current count
        cached_res["requisicoes"] = requisicoes
        return cached_res

    # parse sinais da pagina
    content_type = _header_get(headers_t, "Content-Type") or ""
    if "application/json" in content_type.lower():
        sinais.append({"tipo": "json", "url": alvo_out})
    else:
        try:
            parser = _SinalParser(alvo_str)
            text_body = body_t.decode("utf-8", errors="replace") if isinstance(body_t, (bytes, bytearray)) else str(body_t or "")
            parser.feed(text_body[: 512 * 1024])
            for tipo_s, url_s in parser.sinais:
                sinais.append({"tipo": tipo_s, "url": sanitize_url(url_s)})
        except Exception:
            pass

    # dedup? keep order, remove exact duplicates
    seen = set()
    deduped = []
    for s in sinais:
        key = (s["tipo"], s["url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    sinais = deduped

    etag = _header_get(headers_t, "ETag")
    last_mod = _header_get(headers_t, "Last-Modified")

    if sinais:
        degrau = "dado_estruturado"
        proximo = "usar o dado estruturado em vez de raspar (conferir campos)"
        motivo = None
    else:
        degrau = "gerar_script"
        proximo = "atalhar propose"
        motivo = None

    result = {
        "alvo": alvo_out,
        "degrau": degrau,
        "ferramenta": None,
        "sinais": sinais,
        "robots": {
            "permitido": True,
            "crawl_delay": crawl_delay,
            "status_http": status_r,
        },
        "requisicoes": requisicoes,
        "proximo_passo": proximo,
        "motivo": motivo,
        "versao": __version__,
    }

    # cache
    try:
        cache[cache_key] = {
            "etag": etag,
            "last_modified": last_mod,
            "resultado": result,
        }
        _salvar_cache(cache)
    except Exception:
        pass

    return result


def _salvar_resultado_cache(cache, cache_key, etag, last_mod, result):
    try:
        cache[cache_key] = {
            "etag": etag,
            "last_modified": last_mod,
            "resultado": result,
        }
        _salvar_cache(cache)
    except Exception:
        pass