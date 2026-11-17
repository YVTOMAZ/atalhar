"""Leitura da tabela de precos (TOML) com fallback para Python 3.10."""

import os

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover - ausente no 3.10
    tomllib = None


def _parse_value(raw, lineno):
    raw = raw.strip()
    if not raw:
        raise ValueError(f"linha {lineno}: valor vazio")
    # comentario apos valor
    # (tratado antes: remover comentario fora de string)
    if raw.startswith('"') or raw.startswith("'"):
        # string simples (sem multilinha)
        if raw.startswith('"""') or raw.startswith("'''"):
            raise ValueError(f"linha {lineno}: string multilinha nao suportada")
        quote = raw[0]
        # encontra fechamento
        i = 1
        while i < len(raw):
            if raw[i] == "\\":
                i += 2
                continue
            if raw[i] == quote:
                break
            i += 1
        if i >= len(raw):
            raise ValueError(f"linha {lineno}: string nao fechada")
        val = raw[1:i]
        rest = raw[i + 1:].strip()
        if rest and not rest.startswith("#"):
            raise ValueError(f"linha {lineno}: sintaxe invalida apos string")
        return val
    if raw.startswith("[") or raw.startswith("{"):
        raise ValueError(f"linha {lineno}: arrays/tabelas inline nao suportados")
    if raw.lower() in ("true", "false"):
        # pode ter comentario
        token = raw.split("#", 1)[0].strip().lower()
        if token == "true":
            return True
        if token == "false":
            return False
    # numero
    num_part = raw.split("#", 1)[0].strip()
    try:
        if "." in num_part or "e" in num_part.lower():
            return float(num_part)
        return int(num_part)
    except ValueError:
        raise ValueError(f"linha {lineno}: valor invalido: {raw!r}")


def _minimal_load(text):
    result = {}
    current = result
    path = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            header = s[1:-1].strip()
            # suporta [geral] e [modelos."nome"] / [modelos.nome]
            if header == "geral":
                path = ["geral"]
            elif header.startswith("modelos."):
                rest = header[len("modelos."):].strip()
                if rest.startswith('"') and rest.endswith('"'):
                    name = rest[1:-1]
                elif rest.startswith("'") and rest.endswith("'"):
                    name = rest[1:-1]
                else:
                    name = rest
                path = ["modelos", name]
            else:
                # tabela generica de um nivel
                path = [header]
            # cria aninhamento
            cur = result
            for key in path:
                if key not in cur or not isinstance(cur[key], dict):
                    cur[key] = {}
                cur = cur[key]
            current = cur
            # registra caminho atual (nao usado diretamente)
            _ = path
            continue
        if "=" not in s:
            raise ValueError(f"linha {idx}: sintaxe invalida (esperado chave = valor)")
        key, _, val = s.partition("=")
        key = key.strip()
        # remove comentario do valor de forma segura (strings tratadas em _parse_value)
        # _parse_value ja lida com comentario simples
        value = _parse_value(val, idx)
        if not key:
            raise ValueError(f"linha {idx}: chave vazia")
        # chave pode ser quoted
        if key.startswith('"') and key.endswith('"'):
            key = key[1:-1]
        elif key.startswith("'") and key.endswith("'"):
            key = key[1:-1]
        current[key] = value
    return result


def carregar_precos(caminho):
    p = caminho
    if hasattr(p, "read_text"):
        text = p.read_text(encoding="utf-8")
    else:
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
    if tomllib is not None:
        try:
            import io
            return tomllib.loads(text)
        except Exception as e:
            # fallback: se tomllib falhar, tenta minimo
            try:
                return _minimal_load(text)
            except ValueError:
                raise ValueError(str(e))
    return _minimal_load(text)


# manter compatibilidade com uso por caminho de arquivo
def load(caminho):
    return carregar_precos(caminho)