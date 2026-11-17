"""Estimativa pura de economia (sem rede, relogio ou disco)."""

import math


def _as_float(v):
    if v is None:
        return None
    return float(v)


def _validate(cenarios):
    out = []
    for q in cenarios:
        try:
            qf = float(q)
        except (TypeError, ValueError):
            raise ValueError(f"cenario invalido: {q!r}")
        if qf < 0 or qf >= 1:
            raise ValueError(f"cenario fora de [0,1): {qf}")
        out.append(qf)
    if not out:
        raise ValueError("cenarios vazio")
    return tuple(out)


def estimar(candidato, dias, tokens_atalho, tokens_criacao=None,
            tokens_reparo=None, precos_modelo=None, cota_semanal_tokens=None,
            cenarios=(0.0, 0.1, 0.3), incluir_cache=False):
    if not isinstance(candidato, dict):
        raise ValueError("candidato deve ser dict")
    ocorrencias = candidato.get("ocorrencias")
    if ocorrencias is None:
        # aceita alias
        ocorrencias = candidato.get("n") or 0
    ocorrencias = int(ocorrencias)
    dias = int(dias)
    if dias < 1:
        raise ValueError("dias deve ser >= 1")
    te = float(candidato.get("tokens_entrada_medio") or 0)
    ts = float(candidato.get("tokens_saida_medio") or 0)
    tc = float(candidato.get("tokens_cache_medio") or 0)

    if tokens_atalho is not None and float(tokens_atalho) < 0:
        raise ValueError("tokens_atalho deve ser >= 0")
    if tokens_criacao is not None and float(tokens_criacao) < 0:
        raise ValueError("tokens_criacao deve ser >= 0")
    if tokens_reparo is not None and float(tokens_reparo) < 0:
        raise ValueError("tokens_reparo deve ser >= 0")

    if tokens_reparo is None:
        tokens_reparo = tokens_criacao

    cenarios = _validate(cenarios)

    if incluir_cache:
        custo_ia_exec = te + ts + tc
    else:
        custo_ia_exec = te + ts

    execucoes_semana = ocorrencias / dias * 7.0

    # precos
    precos = precos_modelo
    tem_preco = precos is not None
    p_in = p_out = p_cache = 0.0
    if tem_preco:
        p_in = float(precos.get("entrada", 0) or 0)
        p_out = float(precos.get("saida", 0) or 0)
        p_cache = float(precos.get("cache", 0) or 0)
    all_zero = (p_in == 0 and p_out == 0 and p_cache == 0)
    if tem_preco and all_zero:
        metrica_principal = "tokens"
    elif tem_preco:
        metrica_principal = "dinheiro"
    else:
        metrica_principal = "tokens"

    def ia_dinheiro():
        return te * p_in / 1e6 + ts * p_out / 1e6 + tc * p_cache / 1e6

    # blended rate para converter tokens_atalho
    custo_ia_money = ia_dinheiro() if tem_preco else None
    if tem_preco and custo_ia_exec and custo_ia_exec > 0:
        rate = custo_ia_money / custo_ia_exec
    else:
        rate = 0.0

    cota = cota_semanal_tokens
    try:
        cota = float(cota) if cota is not None else 0.0
    except (TypeError, ValueError):
        cota = 0.0
    tem_cota = cota > 0

    # preco info
    if tem_preco:
        preco_info = {
            "modelo": precos.get("modelo", precos.get("nome", precos.get("model"))),
            "consultado_em": precos.get("consultado_em"),
            "moeda": precos.get("moeda"),
        }
    else:
        preco_info = None

    avisos = []

    cenarios_out = []
    for q in cenarios:
        if tokens_atalho is None:
            custo_atalho_exec = None
            economia_exec = None
            economia_semana = None
            retorno = None
            motivo = None
        else:
            ta = float(tokens_atalho)
            if q == 0:
                custo_atalho_exec = ta
            else:
                if tokens_reparo is None:
                    custo_atalho_exec = None
                    economia_exec = None
                    economia_semana = None
                    retorno = None
                    motivo = None
                    # still append with nulls
                    dinheiro = None
                    pct_cota = None
                    cenarios_out.append({
                        "q": q,
                        "custo_atalho_exec": custo_atalho_exec,
                        "economia_exec": economia_exec,
                        "economia_semana": economia_semana,
                        "retorno_execucoes": retorno,
                        "motivo": motivo,
                        "dinheiro": dinheiro,
                        "pct_cota": pct_cota,
                    })
                    continue
                tr = float(tokens_reparo)
                custo_atalho_exec = (1 - q) * ta + q * (custo_ia_exec + tr)
            if custo_atalho_exec is None:
                economia_exec = None
                economia_semana = None
                retorno = None
                motivo = None
            else:
                economia_exec = custo_ia_exec - custo_atalho_exec
                economia_semana = economia_exec * execucoes_semana
                if economia_exec > 0:
                    if tokens_criacao is None:
                        retorno = None
                        motivo = None
                    else:
                        retorno = math.ceil(float(tokens_criacao) / economia_exec)
                        motivo = None
                else:
                    retorno = None
                    motivo = "nao_compensa"

        # dinheiro
        if tem_preco and custo_atalho_exec is not None:
            dinheiro = {
                "custo_ia_exec": custo_ia_money,
                "custo_atalho_exec": custo_atalho_exec * rate,
                "economia_exec": economia_exec * rate if economia_exec is not None else None,
                "economia_semana": economia_semana * rate if economia_semana is not None else None,
            }
        elif tem_preco and custo_atalho_exec is None:
            dinheiro = None
        else:
            dinheiro = None

        # pct cota
        if tem_cota and custo_atalho_exec is not None:
            pct_ia = custo_ia_exec * execucoes_semana / cota * 100.0
            pct_econ = None
            if economia_exec is not None:
                pct_econ = economia_exec * execucoes_semana / cota * 100.0
            pct_cota = {
                "ia": pct_ia,
                "economia": pct_econ,
            }
        else:
            pct_cota = None

        cenarios_out.append({
            "q": q,
            "custo_atalho_exec": custo_atalho_exec,
            "economia_exec": economia_exec,
            "economia_semana": economia_semana,
            "retorno_execucoes": retorno,
            "motivo": motivo,
            "dinheiro": dinheiro,
            "pct_cota": pct_cota,
        })

    result = {
        "impressao_digital": candidato.get("impressao_digital"),
        "entradas": ocorrencias,
        "metrica_principal": metrica_principal,
        "custo_ia_exec": custo_ia_exec,
        "execucoes_semana": execucoes_semana,
        "cenarios": cenarios_out,
        "preco": preco_info,
        "avisos": avisos,
    }
    return result