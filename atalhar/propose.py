"""Proposta e decisao de consentimento (pedir 'sim' antes de criar)."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from . import __version__
from .ledger import connect as _ledger_connect, now_iso, redact_nota, sanitize_url

PRAZO_NAO_DIAS = 30
PRAZO_DEPOIS_DIAS = 7

SCHEMA_PROPOSTAS = """
CREATE TABLE IF NOT EXISTS propostas (
    id TEXT PRIMARY KEY,
    impressao_digital TEXT NOT NULL UNIQUE,
    tipo TEXT,
    alvo TEXT NOT NULL,
    estado TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    dados_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisoes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    proposta_id TEXT NOT NULL,
    decisao TEXT NOT NULL,
    decidido_em TEXT NOT NULL,
    nota TEXT
);
CREATE TABLE IF NOT EXISTS nunca (
    alvo TEXT PRIMARY KEY,
    proposta_id TEXT,
    decidido_em TEXT NOT NULL
);
"""


def _conn(conn):
    if conn is None:
        conn = _ledger_connect()
    conn.executescript(SCHEMA_PROPOSTAS)
    conn.commit()
    return conn


def _parse_agora(agora):
    if agora is None:
        return datetime.now(timezone.utc)
    if isinstance(agora, datetime):
        return agora.astimezone(timezone.utc) if agora.tzinfo else agora.replace(tzinfo=timezone.utc)
    # string
    from .detect import parse_ts

    dt = parse_ts(agora)
    if dt is None:
        return datetime.now(timezone.utc)
    return dt


def _days_between(a, b):
    # a,b datetime or iso strings
    if isinstance(a, str):
        from .detect import parse_ts

        a = parse_ts(a) or datetime.now(timezone.utc)
    if isinstance(b, str):
        from .detect import parse_ts

        b = parse_ts(b) or datetime.now(timezone.utc)
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).total_seconds() / 86400.0


def id_de(fp):
    return "p-" + hashlib.sha256(fp.encode("utf-8")).hexdigest()[:12]


def texto_proposta(dados):
    if not isinstance(dados, dict):
        return ""
    if dados.get("pergunta_ao_usuario"):
        return dados["pergunta_ao_usuario"]

    ocorrencias = dados.get("ocorrencias")
    if ocorrencias is None:
        ocorrencias = dados.get("entradas")
    if ocorrencias is None:
        ocorrencias = 0
    try:
        ocorrencias = int(ocorrencias)
    except (TypeError, ValueError):
        ocorrencias = 0

    dias = dados.get("dias")
    if dias is None:
        dias = 14
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        dias = 14

    tipo = dados.get("tipo") or "tarefa"
    alvo = dados.get("alvo") or ""
    resumo = f"{tipo} em {alvo}"

    tokens_medios = dados.get("tokens_medios")
    if tokens_medios is None:
        tokens_medios = dados.get("custo_ia_exec")
    try:
        tokens_medios_txt = str(int(round(float(tokens_medios)))) if tokens_medios is not None else "sem medição"
    except (TypeError, ValueError):
        tokens_medios_txt = "sem medição"

    # pct cota
    pct_cota = dados.get("pct_cota")
    if pct_cota is None:
        # try from vantagem_estimada
        va = dados.get("vantagem_estimada")
        if isinstance(va, dict):
            pct_cota = va.get("pct_cota")
    pct_txt = ""
    pct_val = None
    if isinstance(pct_cota, dict):
        pct_val = pct_cota.get("ia")
    elif pct_cota is not None:
        pct_val = pct_cota
    if pct_val is not None:
        try:
            pct_txt = f", {pct_val}% da sua cota semanal"
        except (TypeError, ValueError):
            pct_txt = ""

    caminho = dados.get("caminho")
    if caminho is None:
        caminho = "sem medição"

    # economia semana
    va = dados.get("vantagem_estimada") if isinstance(dados.get("vantagem_estimada"), dict) else {}
    economia_semana = dados.get("economia_semana_tokens")
    if economia_semana is None and isinstance(va, dict):
        economia_semana = va.get("economia_semana_tokens")
    if economia_semana is None:
        economia_txt = "sem medição"
    else:
        try:
            economia_txt = str(int(round(float(economia_semana))))
        except (TypeError, ValueError):
            economia_txt = "sem medição"

    # cenarios
    cenarios_list = dados.get("cenarios")
    if cenarios_list is None and isinstance(va, dict):
        cenarios_list = va.get("cenarios")
    scen_parts = []
    if isinstance(cenarios_list, list):
        for sc in cenarios_list:
            if not isinstance(sc, dict):
                continue
            q = sc.get("q")
            try:
                qtxt = f"{int(round(float(q) * 100))}%"
            except (TypeError, ValueError):
                qtxt = str(q)
            val = sc.get("economia_semana")
            if val is None:
                val_txt = "sem medição"
            else:
                try:
                    val_txt = str(int(round(float(val))))
                except (TypeError, ValueError):
                    val_txt = "sem medição"
            scen_parts.append(f"{qtxt}: {val_txt}")
    cenarios_txt = ", ".join(scen_parts) if scen_parts else "sem medição"

    custo_criacao = dados.get("tokens_criacao")
    if custo_criacao is None:
        custo_criacao = dados.get("custo_criacao")
    if custo_criacao is None:
        custo_txt = "sem medição"
    else:
        try:
            custo_txt = str(int(round(float(custo_criacao))))
        except (TypeError, ValueError):
            custo_txt = "sem medição"

    retorno = dados.get("retorno_execucoes")
    if retorno is None and isinstance(va, dict):
        retorno = va.get("retorno_execucoes")
    if retorno is None:
        retorno_txt = "sem medição"
    else:
        try:
            retorno_txt = str(int(round(float(retorno))))
        except (TypeError, ValueError):
            retorno_txt = "sem medição"

    robots = dados.get("robots")
    if not isinstance(robots, dict):
        robots = {}
    status = robots.get("permitido")
    if status is True:
        status_txt = "permitido"
    elif status is False:
        status_txt = "não permitido"
    elif status is None:
        status_txt = "sem medição"
    else:
        status_txt = str(status)

    k = min(ocorrencias, 3)

    lines = [
        f"Percebi que repeti esta ação {ocorrencias} vezes em {dias} dias: {resumo}.",
        f"Cada vez a IA gasta cerca de {tokens_medios_txt} tokens{pct_txt}.",
        f"Caminho mais barato: {caminho}.",
        f"Economia estimada: ~{economia_txt} tokens por semana (cenários de quebra: {cenarios_txt}).",
        f"Custo único para criar: ~{custo_txt} tokens. Retorno em ~{retorno_txt} execuções.",
        f"Riscos: o site pode mudar; robots.txt: {status_txt}; vou comparar com {k} resultados que a IA já entregou.",
        "Posso seguir? (sim / não / depois / nunca para este alvo)",
    ]
    return "\n".join(lines)


def _build_result_base(pid, fp, tipo, alvo, agora, estado, caminho, robots, est, check, cand, dias, tokens_atalho, tokens_criacao, extra=None):
    agora_iso = agora.isoformat() if isinstance(agora, datetime) else str(agora)
    ocorrencias = cand.get("ocorrencias") if isinstance(cand, dict) else None
    if ocorrencias is None and isinstance(cand, dict):
        ocorrencias = cand.get("entradas")
    if ocorrencias is None:
        ocorrencias = 0
    try:
        ocorrencias = int(ocorrencias)
    except (TypeError, ValueError):
        ocorrencias = 0

    custo_ia_exec = None
    if isinstance(est, dict):
        custo_ia_exec = est.get("custo_ia_exec")
    try:
        tokens_medios = int(round(float(custo_ia_exec))) if custo_ia_exec is not None else "sem medição"
    except (TypeError, ValueError):
        tokens_medios = "sem medição"

    # cenarios
    cenarios_out = []
    if isinstance(est, dict):
        for sc in est.get("cenarios") or []:
            if not isinstance(sc, dict):
                continue
            q = sc.get("q")
            econ = sc.get("economia_semana")
            if econ is None:
                econ_out = "sem medição"
            else:
                try:
                    econ_out = int(round(float(econ)))
                except (TypeError, ValueError):
                    econ_out = "sem medição"
            try:
                q_out = float(q)
            except (TypeError, ValueError):
                q_out = 0.0
            cenarios_out.append({"q": q_out, "economia_semana": (int(round(float(econ))) if econ is not None else "sem medição")})

    # pct_cota
    pct_cota = None
    if isinstance(est, dict):
        scs = est.get("cenarios") or []
        if scs and isinstance(scs[0], dict):
            pct_cota = scs[0].get("pct_cota")

    economia_semana_tokens = None
    retorno_execucoes = None
    if isinstance(est, dict):
        scs = est.get("cenarios") or []
        if scs and isinstance(scs[0], dict):
            economia_semana_tokens = scs[0].get("economia_semana")
            retorno_execucoes = scs[0].get("retorno_execucoes")
    if economia_semana_tokens is None:
        economia_semana_tokens_out = "sem medição"
    else:
        try:
            economia_semana_tokens_out = int(round(float(economia_semana_tokens)))
        except (TypeError, ValueError):
            economia_semana_tokens_out = "sem medição"
    if retorno_execucoes is None:
        retorno_out = "sem medição"
    else:
        try:
            retorno_out = int(round(float(retorno_execucoes)))
        except (TypeError, ValueError):
            retorno_out = "sem medição"

    # origem precos
    preco_info = None
    if isinstance(est, dict):
        preco_info = est.get("preco")
    if not isinstance(preco_info, dict):
        preco_info = {}
    consulted = preco_info.get("consultado_em")

    check_arquivo = None
    if isinstance(check, dict):
        check_arquivo = check.get("arquivo")

    origem = {
        "fonte": "atalhar estimate sobre o livro-caixa local",
        "execucoes": ocorrencias,
        "janela": {
            "inicio": (cand.get("primeira") if isinstance(cand, dict) else None),
            "fim": (cand.get("ultima") if isinstance(cand, dict) else None),
        },
        "tokens_atalho": ("informado pelo usuário (--tokens-atalho)" if tokens_atalho is not None else "sem medição"),
        "precos": {"arquivo": None, "consultado_em": consulted},
        "check": {"arquivo": check_arquivo, "degrau": (check.get("degrau") if isinstance(check, dict) else None)},
        "rotulo": "estimativa, não medição; cenários ilustrativos",
    }

    # cenarios for vantagem: keep numbers or "sem medição"
    cenarios_va = []
    if isinstance(est, dict):
        for sc in est.get("cenarios") or []:
            if not isinstance(sc, dict):
                continue
            q = sc.get("q")
            econ = sc.get("economia_semana")
            cenarios_va.append({
                "q": (float(q) if q is not None else 0.0),
                "economia_semana": (int(round(float(econ))) if econ is not None else "sem medição"),
            })

    vantagem = {
        "economia_semana_tokens": economia_semana_tokens_out,
        "retorno_execucoes": (int(round(float(retorno_execucoes))) if retorno_execucoes is not None else "sem medição"),
        "pct_cota": pct_cota,
        "cenarios": cenarios_va,
        "origem": origem,
    }

    # store tokens_medios as number? keep int or string. dados uses int
    dados = {
        "id": pid,
        "estado": estado,
        "impressao_digital": fp,
        "tipo": tipo,
        "alvo": alvo,
        "caminho": caminho,
        "robots": robots,
        "dias": dias,
        "ocorrencias": ocorrencias,
        "tokens_medios": (int(round(float(custo_ia_exec))) if custo_ia_exec is not None else "sem medição"),
        "custo_ia_exec": custo_ia_exec,
        "tokens_criacao": tokens_criacao,
        "economia_semana_tokens": economia_semana_tokens_out,
        "retorno_execucoes": (int(round(float(retorno_execucoes))) if retorno_execucoes is not None else "sem medição"),
        "pct_cota": pct_cota,
        "cenarios": cenarios_va,
        "check_arquivo": check_arquivo,
    }

    criado = agora_iso
    # if existing, keep criado? We'll set criado_em from db when loading; here for new.

    result = {
        "id": pid,
        "estado": estado,
        "impressao_digital": fp,
        "tipo": tipo,
        "alvo": alvo,
        "caminho": caminho,
        "pergunta_ao_usuario": None,  # filled below
        "opcoes": ["sim", "nao", "depois", "nunca"],
        "comando_decisao": f"atalhar decide {pid} <sim|nao|depois|nunca>",
        "vantagem_estimada": vantagem,
        "robots": robots,
        "criado_em": criado,
        "atualizado_em": criado,
        "versao": __version__,
        "dias": dias,
        "ocorrencias": ocorrencias,
        "tokens_medios": (int(round(float(custo_ia_exec))) if custo_ia_exec is not None else "sem medição"),
        "tokens_criacao": tokens_criacao,
        "economia_semana_tokens": economia_semana_tokens_out,
        "retorno_execucoes": (int(round(float(retorno_execucoes))) if retorno_execucoes is not None else "sem medição"),
        "pct_cota": pct_cota,
        "cenarios": cenarios_va,
    }
    # generate text
    text = texto_proposta(result)
    result["pergunta_ao_usuario"] = text
    # also store dados_json
    result["_dados"] = dados
    if extra:
        result.update(extra)
    return result


def propor(candidato, *, estimativa=None, check=None, agora=None, repropor=False, conn=None):
    if not isinstance(candidato, dict):
        raise ValueError("candidato deve ser dict")
    agora_dt = _parse_agora(agora)

    fp = candidato.get("impressao_digital")
    if not fp:
        raise ValueError("candidato sem impressao_digital")
    tipo = candidato.get("tipo")
    alvo = sanitize_url(candidato.get("alvo") or "")

    # tokens
    tokens_atalho = None
    if isinstance(candidato, dict):
        tokens_atalho = candidato.get("tokens_atalho")
    # prefer estimativa? no

    # dias: try candidate or default 14
    dias = 14
    if isinstance(candidato, dict) and candidato.get("dias") is not None:
        try:
            dias = int(candidato.get("dias"))
        except (TypeError, ValueError):
            dias = 14

    if estimativa is None:
        from .estimate import estimar

        try:
            estimativa = estimar(candidato, dias=dias, tokens_atalho=tokens_atalho)
        except Exception:
            estimativa = None

    tokens_criacao = None
    if isinstance(candidato, dict):
        tokens_criacao = candidato.get("tokens_criacao")
    # allow override from estimativa? no

    # check normalize
    if isinstance(check, dict):
        if "arquivo" not in check:
            check = dict(check)

    pid = id_de(fp)

    conn = _conn(conn)
    own = False
    # track ownership: if conn was None originally, close at end
    # We created conn via _conn (may be new). Need know if we should close.
    # _conn returns same conn passed or new. We'll close only if not provided by caller.
    close_at_end = conn is not None and False
    # simpler: caller passes conn; if None we opened. Track:
    opened_here = False
    # _conn doesn't tell; restructure:
    pass

    # We'll handle connection ownership by checking a flag set before
    # Re-open logic: redo cleanly
    pass

    # Actually redo: 
    return _propor_impl(candidato, estimativa, check, agora_dt, repropor, fp, tipo, alvo, dias, tokens_atalho, tokens_criacao, pid, conn)


def _propor_impl(candidato, estimativa, check, agora_dt, repropor, fp, tipo, alvo, dias, tokens_atalho, tokens_criacao, pid, conn):
    # never list
    row_n = conn.execute("SELECT * FROM nunca WHERE alvo=?", (alvo,)).fetchone()
    if row_n is not None:
        decidido_em = row_n["decidido_em"]
        msg = f"Você pediu para nunca propor atalho para {alvo} (decidido em {decidido_em})"
        result = {
            "id": pid,
            "estado": "bloqueado_nunca",
            "impressao_digital": fp,
            "tipo": tipo,
            "alvo": alvo,
            "motivo": msg,
            "pergunta_ao_usuario": msg,
            "opcoes": ["sim", "nao", "depois", "nunca"],
            "comando_decisao": f"atalhar decide {pid} <sim|nao|depois|nunca>",
            "vantagem_estimada": {
                "economia_semana_tokens": "sem medição",
                "retorno_execucoes": "sem medição",
                "pct_cota": None,
                "cenarios": [],
                "origem": {},
            },
            "robots": {"permitido": "sem medição"} if not isinstance(check, dict) else {"permitido": (check.get("robots", {}) or {}).get("permitido")},
            "criado_em": agora_dt.isoformat(),
            "atualizado_em": agora_dt.isoformat(),
            "versao": __version__,
        }
        return result

    # caminho / robots / sem_caminho
    caminho = "sem medição"
    robots = {"permitido": "sem medição"}
    sem_caminho = False
    motivo_sc = None
    degrau = None
    permitido = None
    if isinstance(check, dict):
        degrau = check.get("degrau")
        if degrau == "ferramenta":
            f = check.get("ferramenta") or {}
            caminho = f"ferramenta existente: {f.get('comando')}"
        elif degrau == "dado_estruturado":
            sinais = check.get("sinais") or []
            tipo_s = sinais[0].get("tipo") if sinais and isinstance(sinais[0], dict) else "desconhecido"
            caminho = f"dado estruturado: {tipo_s}"
        elif degrau == "gerar_script":
            caminho = "script novo"
        r = check.get("robots")
        if isinstance(r, dict):
            permitido = r.get("permitido")
            robots = {"permitido": permitido}
        if degrau == "ia" or permitido is False:
            sem_caminho = True
            motivo_sc = check.get("motivo") or "sem caminho mais barato"

    # existing proposal
    row_p = conn.execute("SELECT * FROM propostas WHERE impressao_digital=?", (fp,)).fetchone()
    if row_p is not None:
        estado_atual = row_p["estado"]
        # latest decision
        last_dec = conn.execute(
            "SELECT * FROM decisoes WHERE proposta_id=? ORDER BY seq DESC LIMIT 1", (pid,)
        ).fetchone()
        last_data = last_dec["decidido_em"] if last_dec else row_p["atualizado_em"]
        last_decisao = last_dec["decisao"] if last_dec else None

        # approved
        if estado_atual == "aprovada":
            # load stored
            try:
                stored = json.loads(row_p["dados_json"])
            except Exception:
                stored = {}
            stored["estado"] = "aprovada"
            stored.setdefault("id", pid)
            # ensure pergunta
            if not stored.get("pergunta_ao_usuario"):
                stored["pergunta_ao_usuario"] = texto_proposta(stored)
            return stored

        # recusada
        if estado_atual == "recusada":
            if not repropor and _days_between(last_data, agora_dt) < PRAZO_NAO_DIAS:
                try:
                    stored = json.loads(row_p["dados_json"])
                except Exception:
                    stored = {}
                stored["estado"] = "recusada"
                stored.setdefault("id", pid)
                if not stored.get("pergunta_ao_usuario"):
                    stored["pergunta_ao_usuario"] = texto_proposta(stored)
                return stored
            # else allow regenerate

        # adiada
        if estado_atual == "adiada":
            if _days_between(last_data, agora_dt) < PRAZO_DEPOIS_DIAS:
                try:
                    stored = json.loads(row_p["dados_json"])
                except Exception:
                    stored = {}
                stored["estado"] = "adiada"
                # add reabertura date
                try:
                    from datetime import timedelta

                    dt = _parse_agora(last_data) if isinstance(last_data, str) else last_data
                    reopen = dt + timedelta(days=PRAZO_DEPOIS_DIAS)
                    stored["reabre_em"] = reopen.isoformat()
                except Exception:
                    pass
                stored.setdefault("id", pid)
                if not stored.get("pergunta_ao_usuario"):
                    stored["pergunta_ao_usuario"] = texto_proposta(stored)
                return stored
            # else allow

        # nunca estado (should have been caught by nunca table, but handle)
        if estado_atual == "nunca":
            # blocked
            msg = f"Você pediu para nunca propor atalho para {alvo} (decidido em {last_data})"
            return {
                "id": pid,
                "estado": "bloqueado_nunca",
                "impressao_digital": fp,
                "tipo": tipo,
                "alvo": alvo,
                "motivo": msg,
                "pergunta_ao_usuario": msg,
                "opcoes": ["sim", "nao", "depois", "nunca"],
                "comando_decisao": f"atalhar decide {pid} <sim|nao|depois|nunca>",
                "vantagem_estimada": {"economia_semana_tokens": "sem medição", "retorno_execucoes": "sem medição", "pct_cota": None, "cenarios": [], "origem": {}},
                "robots": robots,
                "criado_em": row_p["criado_em"],
                "atualizado_em": row_p["atualizado_em"],
                "versao": __version__,
            }

    # sem_caminho overrides: still maybe generate? spec: estado sem_caminho, code1, nada oferecido.
    # We'll generate result with estado sem_caminho and skip upsert? It says nada oferecido; probably no proposal created.
    # But idempotency? We'll not write if sem_caminho? Spec: "o propose não oferece script: estado fica sem_caminho, saída código 1". Could still record? "Efeitos colaterais permitidos: somente gravar/atualizar linhas nas tabelas novas". I think no need to store. Return without db write.
    if sem_caminho:
        result = _build_result_base(
            pid, fp, tipo, alvo, agora_dt, "sem_caminho", caminho, robots, estimativa, check, candidato, dias, tokens_atalho, tokens_criacao
        )
        result["motivo"] = motivo_sc
        result["pergunta_ao_usuario"] = motivo_sc
        return result

    # generate result pendente
    result = _build_result_base(
        pid, fp, tipo, alvo, agora_dt, "pendente", caminho, robots, estimativa, check, candidato, dias, tokens_atalho, tokens_criacao
    )

    # upsert db
    dados_json = json.dumps(result.get("_dados", {}), ensure_ascii=False)
    # remove _dados from result
    result.pop("_dados", None)
    criado_iso = agora_dt.isoformat()
    existing = conn.execute("SELECT criado_em FROM propostas WHERE impressao_digital=?", (fp,)).fetchone()
    if existing is not None:
        criado_iso = existing["criado_em"]
    conn.execute(
        """INSERT INTO propostas (id, impressao_digital, tipo, alvo, estado, criado_em, atualizado_em, dados_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(impressao_digital) DO UPDATE SET
             id=excluded.id, tipo=excluded.tipo, alvo=excluded.alvo, estado=excluded.estado,
             atualizado_em=excluded.atualizado_em, dados_json=excluded.dados_json""",
        (pid, fp, tipo, alvo, "pendente", criado_iso, agora_dt.isoformat(), dados_json),
    )
    conn.commit()
    result["criado_em"] = criado_iso
    result["atualizado_em"] = agora_dt.isoformat()
    return result


# Fix propor to delegate to impl and manage connection ownership
def propor(candidato, *, estimativa=None, check=None, agora=None, repropor=False, conn=None):
    if not isinstance(candidato, dict):
        raise ValueError("candidato deve ser dict")
    # resolve dias/tokens before
    fp = candidato.get("impressao_digital")
    if not fp:
        raise ValueError("candidato sem impressao_digital")
    agora_dt = _parse_agora(agora)

    tipo = candidato.get("tipo")
    alvo = sanitize_url(candidato.get("alvo") or "")

    tokens_atalho = candidato.get("tokens_atalho")
    dias = 14
    if candidato.get("dias") is not None:
        try:
            dias = int(candidato.get("dias"))
        except (TypeError, ValueError):
            dias = 14

    if estimativa is None:
        from .estimate import estimar

        try:
            estimativa = estimar(candidato, dias=dias, tokens_atalho=tokens_atalho)
        except Exception:
            estimativa = None

    tokens_criacao = candidato.get("tokens_criacao")

    if isinstance(check, dict) and "arquivo" not in check:
        check = dict(check)

    pid = id_de(fp)

    opened_here = conn is None
    if opened_here:
        conn = _ledger_connect()
    conn.executescript(SCHEMA_PROPOSTAS)
    conn.commit()

    try:
        return _propor_impl(
            candidato, estimativa, check, agora_dt, repropor, fp, tipo, alvo, dias,
            tokens_atalho, tokens_criacao, pid, conn,
        )
    finally:
        if opened_here:
            conn.close()


# patch _build_result_base to store _dados already? It stores result["_dados"]=dados. Good.
# But early approved/recusada returns stored (no _dados). Fine.


def decidir(id, decisao, *, nota=None, agora=None, revogar_nunca=False, conn=None):
    if not isinstance(id, str) or not id:
        raise ValueError("id invalido")
    d = str(decisao).strip().lower()
    if d == "não":
        d = "nao"
    if d not in ("sim", "nao", "depois", "nunca"):
        raise ValueError("decisao invalida")

    agora_dt = _parse_agora(agora)
    opened_here = conn is None
    if opened_here:
        conn = _ledger_connect()
    conn.executescript(SCHEMA_PROPOSTAS)
    conn.commit()
    try:
        row = conn.execute("SELECT * FROM propostas WHERE id=?", (id,)).fetchone()
        if row is None:
            raise ValueError(f"proposta nao encontrada: {id}")

        fp = row["impressao_digital"]
        alvo = row["alvo"]
        estado_atual = row["estado"]
        pid = row["id"]

        # revogar check
        if d == "sim":
            nrow = conn.execute("SELECT 1 FROM nunca WHERE alvo=?", (alvo,)).fetchone()
            if (estado_atual == "nunca" or nrow is not None) and not revogar_nunca:
                # return without change
                return {
                    "id": pid,
                    "decisao": d,
                    "estado": "nunca",
                    "mudou": False,
                    "decidido_em": agora_dt.isoformat(),
                    "proximo_passo": "continuar com a IA",
                    "motivo": "para decidir sim apos nunca, use --revogar-nunca",
                }

        estado_novo = {"sim": "aprovada", "nao": "recusada", "depois": "adiada", "nunca": "nunca"}[d]

        # idempotent?
        if estado_atual == estado_novo:
            # same state; but if revoking? handled. no new row
            return {
                "id": pid,
                "decisao": d,
                "estado": estado_novo,
                "mudou": False,
                "decidido_em": agora_dt.isoformat(),
                "proximo_passo": ("atalhar scaffold " + pid) if d == "sim" else "continuar com a IA",
            }

        # insert decision
        conn.execute(
            "INSERT INTO decisoes (proposta_id, decisao, decidido_em, nota) VALUES (?,?,?,?)",
            (pid, d, agora_dt.isoformat(), redact_nota(nota or "")),
        )
        conn.execute(
            "UPDATE propostas SET estado=?, atualizado_em=? WHERE id=?",
            (estado_novo, agora_dt.isoformat(), pid),
        )
        if d == "nunca":
            conn.execute(
                "INSERT INTO nunca (alvo, proposta_id, decidido_em) VALUES (?,?,?) ON CONFLICT(alvo) DO NOTHING",
                (alvo, pid, agora_dt.isoformat()),
            )
        if d == "sim" and revogar_nunca:
            conn.execute("DELETE FROM nunca WHERE alvo=?", (alvo,))
        conn.commit()

        return {
            "id": pid,
            "decisao": d,
            "estado": estado_novo,
            "mudou": True,
            "decidido_em": agora_dt.isoformat(),
            "proximo_passo": ("atalhar scaffold " + pid) if d == "sim" else "continuar com a IA",
        }
    finally:
        if opened_here:
            conn.close()


def pode_criar(id, *, conn=None):
    opened_here = conn is None
    if opened_here:
        conn = _ledger_connect()
    conn.executescript(SCHEMA_PROPOSTAS)
    conn.commit()
    try:
        row = conn.execute("SELECT estado FROM propostas WHERE id=?", (id,)).fetchone()
        return bool(row and row["estado"] == "aprovada")
    finally:
        if opened_here:
            conn.close()
