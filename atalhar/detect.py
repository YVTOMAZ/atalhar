"""Deteccao de tarefas repetidas e caras no livro-caixa (funcoes puras)."""

from datetime import datetime, timedelta, timezone

_COLUMNS = [
    "id", "ts", "agente", "modelo", "tipo", "alvo", "impressao_digital",
    "tokens_entrada", "tokens_saida", "tokens_cache", "duracao_ms", "ok",
    "origem", "nota",
]


def _to_dict(row):
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        if isinstance(row, (tuple, list)):
            return dict(zip(_COLUMNS, row))
        return row


def _epoch_to_dt(num):
    try:
        num = float(num)
    except (TypeError, ValueError):
        return None
    try:
        if num > 1e12:
            num = num / 1000.0
        return datetime.fromtimestamp(num, tz=timezone.utc)
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def parse_ts(valor):
    """Interpreta ts (ISO 8601 ou epoch s/ms) como datetime UTC, ou None."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return _epoch_to_dt(valor)
    if isinstance(valor, str):
        s = valor.strip()
        if not s:
            return None
        # tenta numerico primeiro (epoch em s ou ms)
        if _looks_numeric(s):
            try:
                return _epoch_to_dt(float(s))
            except ValueError:
                pass
        # ISO 8601
        txt = s
        if txt[-1:] in ("Z", "z"):
            txt = txt[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            # ultima tentativa: talvez seja epoch com texto
            try:
                return _epoch_to_dt(float(s))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _looks_numeric(s):
    s = s.strip()
    if not s:
        return False
    if s[0] in "+-":
        s = s[1:]
    if not s or s.count(".") > 1:
        return False
    return all(c.isdigit() or c == "." for c in s) and any(c.isdigit() for c in s)


def _fmt(dt):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def detectar(linhas, agora, n=3, dias=14, custo_min=0, incluir_cache=False,
             origem="ia"):
    if not isinstance(agora, datetime):
        agora = parse_ts(agora)
    if agora is None:
        agora = datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    else:
        agora = agora.astimezone(timezone.utc)

    inicio = agora - timedelta(days=dias)
    fim = agora

    ignorados = 0
    validas = []  # list of (dict, datetime, idx)
    idx = 0
    for row in (linhas or []):
        r = _to_dict(row)
        row_origem = r.get("origem")
        if origem not in (None, "", "todas") and row_origem != origem:
            continue
        dt = parse_ts(r.get("ts"))
        if dt is None:
            ignorados += 1
            continue
        if dt <= inicio or dt > fim:
            continue
        validas.append((r, dt, idx))
        idx += 1

    total_execucoes_janela = len(validas)

    grupos = {}
    for r, dt, i in validas:
        fp = r.get("impressao_digital")
        grupos.setdefault(fp, []).append((r, dt, i))

    candidatos = []
    for fp, items in grupos.items():
        ocorrencias = len(items)
        dias_distintos = len({dt.date() for _, dt, _ in items})
        dts = [dt for _, dt, _ in items]
        primeira = min(dts)
        ultima = max(dts)

        most_recent = max(items, key=lambda x: (x[1], x[2]))
        r_recent = most_recent[0]

        nota_exemplo = ""
        for r, dt, i in sorted(items, key=lambda x: (x[1], x[2])):
            val = r.get("nota")
            if val:
                nota_exemplo = val

        tes = [int(r.get("tokens_entrada") or 0) for r, _, _ in items]
        tss = [int(r.get("tokens_saida") or 0) for r, _, _ in items]
        tcs = [int(r.get("tokens_cache") or 0) for r, _, _ in items]
        media_te = sum(tes) / ocorrencias
        media_ts = sum(tss) / ocorrencias
        media_tc = sum(tcs) / ocorrencias
        if incluir_cache:
            custo_medio = media_te + media_ts + media_tc
            custo_total = sum(tes) + sum(tss) + sum(tcs)
        else:
            custo_medio = media_te + media_ts
            custo_total = sum(tes) + sum(tss)

        ok_count = sum(1 for r, _, _ in items if r.get("ok"))
        taxa_ok = ok_count / ocorrencias

        if ocorrencias >= n and custo_medio >= custo_min:
            candidatos.append({
                "impressao_digital": fp,
                "tipo": r_recent.get("tipo"),
                "alvo": r_recent.get("alvo"),
                "ocorrencias": ocorrencias,
                "dias_distintos": dias_distintos,
                "primeira": _fmt(primeira),
                "ultima": _fmt(ultima),
                "tokens_entrada_medio": media_te,
                "tokens_saida_medio": media_ts,
                "tokens_cache_medio": media_tc,
                "custo_medio_tokens": custo_medio,
                "custo_total_tokens": custo_total,
                "taxa_ok": taxa_ok,
                "nota_exemplo": nota_exemplo,
            })

    candidatos.sort(key=lambda c: (-c["custo_total_tokens"],
                                  -c["ocorrencias"],
                                  c["impressao_digital"] or ""))

    return {
        "parametros": {
            "min_ocorrencias": n,
            "dias": dias,
            "custo_min": custo_min,
            "incluir_cache": bool(incluir_cache),
            "origem": origem,
        },
        "janela": {
            "inicio": _fmt(inicio),
            "fim": _fmt(fim),
        },
        "total_execucoes_janela": total_execucoes_janela,
        "ignorados_ts_invalido": ignorados,
        "candidatos": candidatos,
    }
