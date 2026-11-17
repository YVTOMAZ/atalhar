"""CLI do atalhar."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from . import __version__
from .detect import detectar, parse_ts
from .estimate import estimar
from .fingerprint import fingerprint, sanitize_url
from .ledger import db_path, init_db, log_execucao, redact_nota
from .importers.opencode import import_opencode
from .precos import carregar_precos


def cmd_version(args):
    print(__version__)
    return 0


def cmd_init(args):
    p = init_db()
    print(f"banco inicializado em {p}")
    return 0


def cmd_log(args):
    # read stdin json if no args? Support both.
    data = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                data = json.loads(raw)
        except json.JSONDecodeError:
            print("erro: stdin nao e JSON valido", file=sys.stderr)
            return 2

    tipo = args.tipo or data.get("tipo") or data.get("type")
    alvo = args.alvo or data.get("alvo") or data.get("target")
    if not tipo or not alvo:
        print("erro: --tipo e --alvo obrigatorios", file=sys.stderr)
        return 2

    alvo = sanitize_url(alvo)
    fp = args.fingerprint or data.get("impressao_digital") or fingerprint(tipo, alvo, data.get("forma", ""))
    row = {
        "ts": args.ts or data.get("ts"),
        "agente": args.agente or data.get("agente") or data.get("agent"),
        "modelo": args.modelo or data.get("modelo") or data.get("model"),
        "tipo": tipo,
        "alvo": alvo,
        "impressao_digital": fp,
        "tokens_entrada": args.tokens_entrada if args.tokens_entrada is not None else data.get("tokens_entrada", data.get("tokens_input", 0)),
        "tokens_saida": args.tokens_saida if args.tokens_saida is not None else data.get("tokens_saida", data.get("tokens_output", 0)),
        "tokens_cache": args.tokens_cache if args.tokens_cache is not None else data.get("tokens_cache", 0),
        "duracao_ms": args.duracao_ms if args.duracao_ms is not None else data.get("duracao_ms"),
        "ok": True if (args.ok is None and "ok" not in data) else (args.ok if args.ok is not None else bool(data.get("ok", True))),
        "origem": args.origem or data.get("origem") or data.get("origin") or "ia",
        "nota": redact_nota(args.nota if args.nota is not None else data.get("nota", data.get("note", ""))),
    }
    rid = log_execucao(row)
    if args.json:
        print(json.dumps({"id": rid, "impressao_digital": fp, "alvo": alvo}, ensure_ascii=False))
    else:
        print(f"registrado id={rid} fp={fp}")
    return 0


def cmd_import(args):
    if args.agente != "opencode":
        print("erro: apenas 'opencode' suportado no MVP", file=sys.stderr)
        return 2
    res = import_opencode(args.arquivo, db_path=None)
    print(f"importados: {res['imported']}, ignorados: {res['ignored']}")
    return 0


def cmd_detect(args):
    n = args.min_ocorrencias
    dias = args.dias
    custo_min = args.custo_min
    limite = args.limite
    if n < 1:
        print("erro: --min-ocorrencias deve ser >= 1", file=sys.stderr)
        return 2
    if dias < 1:
        print("erro: --dias deve ser >= 1", file=sys.stderr)
        return 2
    if custo_min < 0:
        print("erro: --custo-min deve ser >= 0", file=sys.stderr)
        return 2
    if limite < 1:
        print("erro: --limite deve ser >= 1", file=sys.stderr)
        return 2
    if args.ate is None:
        agora = datetime.now(timezone.utc)
    else:
        agora = parse_ts(args.ate)
        if agora is None:
            print("erro: --ate invalido (use ISO 8601)", file=sys.stderr)
            return 2

    p = db_path()
    if not p.exists():
        print("livro-caixa vazio: rode 'atalhar import' ou 'atalhar log'")
        return 0
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM execucoes").fetchall()
    finally:
        conn.close()

    res = detectar(rows, agora, n=n, dias=dias, custo_min=custo_min,
                   incluir_cache=args.incluir_cache, origem=args.origem)
    res["candidatos"] = res["candidatos"][:limite]
    res["parametros"]["limite"] = limite

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    cands = res["candidatos"]
    if not cands:
        print("nenhuma repeticao acima dos limites")
        return 0
    print(f"{'impressao':12}  {'tipo':10}  {'alvo':24}  {'n':>3}  {'dias':>4}  {'tokens/exec':>11}  {'total':>8}")
    for c in cands:
        print(f"{str(c['impressao_digital'])[:12]:12}  "
              f"{str(c['tipo'])[:10]:10}  {str(c['alvo'])[:24]:24}  "
              f"{c['ocorrencias']:>3}  {c['dias_distintos']:>4}  "
              f"{c['custo_medio_tokens']:>11.1f}  {c['custo_total_tokens']:>8}")
    return 0


def _resolver_precos(args, home_env=None):
    import os
    caminho = args.precos
    if caminho is None:
        base = os.environ.get("ATALHAR_HOME")
        if base:
            cand = os.path.join(base, "precos.toml")
            if os.path.exists(cand):
                caminho = cand
    if caminho is None:
        return None, None, 0.0
    if not os.path.exists(caminho):
        print(f"erro: arquivo de precos nao encontrado: {caminho}", file=sys.stderr)
        return None, None, None
    try:
        precos = carregar_precos(caminho)
    except Exception as e:
        print(f"erro: precos invalido: {e}", file=sys.stderr)
        return None, None, None
    geral = precos.get("geral", {}) if isinstance(precos, dict) else {}
    moeda = geral.get("moeda") if isinstance(geral, dict) else None
    cota = geral.get("cota_semanal_tokens", 0) if isinstance(geral, dict) else 0
    try:
        cota = float(cota) if cota is not None else 0.0
    except (TypeError, ValueError):
        cota = 0.0
    modelos = precos.get("modelos", {}) if isinstance(precos, dict) else {}
    if args.modelo:
        if not isinstance(modelos, dict) or args.modelo not in modelos:
            print(f"erro: modelo nao encontrado: {args.modelo}", file=sys.stderr)
            return None, None, None
        entrada = modelos[args.modelo]
    elif isinstance(modelos, dict) and len(modelos) == 1:
        nome = next(iter(modelos))
        args.modelo = nome
        entrada = modelos[nome]
    else:
        entrada = None
    if entrada is not None:
        pm = {
            "modelo": args.modelo,
            "consultado_em": entrada.get("consultado_em") if isinstance(entrada, dict) else None,
            "moeda": moeda,
            "entrada": entrada.get("entrada") if isinstance(entrada, dict) else 0,
            "saida": entrada.get("saida") if isinstance(entrada, dict) else 0,
            "cache": entrada.get("cache") if isinstance(entrada, dict) else 0,
        }
    else:
        pm = None
    return pm, moeda, cota


def cmd_estimate(args):
    # cenarios
    try:
        cenarios = [float(x.strip()) for x in str(args.cenarios).split(",") if x.strip() != ""]
    except ValueError:
        print("erro: --cenarios invalido", file=sys.stderr)
        return 2
    for q in cenarios:
        if q < 0 or q >= 1:
            print("erro: cenario deve estar em [0,1)", file=sys.stderr)
            return 2
    if not cenarios:
        print("erro: --cenarios vazio", file=sys.stderr)
        return 2

    if args.dias < 1:
        print("erro: --dias deve ser >= 1", file=sys.stderr)
        return 2

    # resolver candidato
    cand = None
    if args.stdin:
        raw = sys.stdin.read().strip()
        if not raw:
            print("erro: stdin vazio", file=sys.stderr)
            return 2
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("erro: stdin nao e JSON valido", file=sys.stderr)
            return 2
        if isinstance(data, dict) and "candidatos" in data:
            cands = data["candidatos"]
            if args.impressao_digital:
                for c in cands:
                    if c.get("impressao_digital") == args.impressao_digital:
                        cand = c
                        break
            if cand is None and cands:
                cand = cands[0]
        elif isinstance(data, list):
            cand = data[0] if data else None
        elif isinstance(data, dict):
            cand = data
        if cand is None:
            print("erro: candidato nao encontrado no stdin", file=sys.stderr)
            return 2
    else:
        if not args.impressao_digital:
            print("erro: impressao_digital obrigatoria (ou use --stdin)", file=sys.stderr)
            return 2
        if args.ate is None:
            agora = datetime.now(timezone.utc)
        else:
            agora = parse_ts(args.ate)
            if agora is None:
                print("erro: --ate invalido (use ISO 8601)", file=sys.stderr)
                return 2
        p = db_path()
        if not p.exists():
            print("livro-caixa vazio: rode 'atalhar import' ou 'atalhar log'")
            return 2
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM execucoes").fetchall()
        finally:
            conn.close()
        res = detectar(rows, agora, n=1, dias=args.dias,
                       incluir_cache=args.incluir_cache)
        for c in res.get("candidatos", []):
            if c.get("impressao_digital") == args.impressao_digital:
                cand = c
                break
        if cand is None:
            print(f"erro: impressao digital nao encontrada: {args.impressao_digital}", file=sys.stderr)
            return 2

    # tokens
    tokens_atalho = args.tokens_atalho
    if tokens_atalho is None and isinstance(cand, dict):
        tokens_atalho = cand.get("tokens_atalho")
    if tokens_atalho is None:
        print("erro: --tokens-atalho obrigatorio", file=sys.stderr)
        return 2
    try:
        tokens_atalho = int(tokens_atalho)
    except (TypeError, ValueError):
        print("erro: --tokens-atalho invalido", file=sys.stderr)
        return 2
    if tokens_atalho < 0:
        print("erro: --tokens-atalho deve ser >= 0", file=sys.stderr)
        return 2

    tokens_criacao = args.tokens_criacao
    tokens_reparo = args.tokens_reparo
    if tokens_criacao is not None:
        try:
            tokens_criacao = int(tokens_criacao)
        except (TypeError, ValueError):
            print("erro: --tokens-criacao invalido", file=sys.stderr)
            return 2
    if tokens_reparo is not None:
        try:
            tokens_reparo = int(tokens_reparo)
        except (TypeError, ValueError):
            print("erro: --tokens-reparo invalido", file=sys.stderr)
            return 2

    if args.precos is not None and not os.path.exists(args.precos):
        print(f"erro: arquivo de precos nao encontrado: {args.precos}", file=sys.stderr)
        return 2
    pm, moeda, cota = _resolver_precos(args)
    if args.modelo is not None and pm is None and args.precos is not None:
        return 2

    try:
        res = estimar(
            cand,
            dias=args.dias,
            tokens_atalho=tokens_atalho,
            tokens_criacao=tokens_criacao,
            tokens_reparo=tokens_reparo,
            precos_modelo=pm,
            cota_semanal_tokens=cota,
            cenarios=tuple(cenarios),
            incluir_cache=args.incluir_cache,
        )
    except ValueError as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    # texto
    print(f"impressao: {res['impressao_digital']}")
    print(f"metrica principal: {res['metrica_principal']}")
    print(f"custo_ia_exec: {res['custo_ia_exec']} tokens")
    print(f"execucoes_semana: {res['execucoes_semana']}")
    scen_txt = []
    for sc in res["cenarios"]:
        q = int(sc["q"] * 100) if float(sc["q"]).is_integer() else sc["q"]
        val = sc["economia_semana"]
        if val is None:
            val = "sem medição"
        scen_txt.append(f"{q}%: {val}")
    print("Economia estimada: ~{} tokens por semana (cenários de quebra: {})".format(
        res["cenarios"][0].get("economia_semana") if res["cenarios"] and res["cenarios"][0].get("economia_semana") is not None else "sem medição",
        ", ".join(scen_txt),
    ))
    if res.get("preco") is None:
        print("dinheiro: sem medição")
    print("Estimativa, não medição. A economia real é medida pelo report (T9).")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="atalhar", description="Atalhar: a IA para de repetir o caminho caro.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Inicializa o livro-caixa local.")
    p_init.set_defaults(func=cmd_init)

    p_log = sub.add_parser("log", help="Registra uma execucao no livro-caixa.")
    p_log.add_argument("--tipo", dest="tipo")
    p_log.add_argument("--alvo", dest="alvo")
    p_log.add_argument("--agente", dest="agente")
    p_log.add_argument("--modelo", dest="modelo")
    p_log.add_argument("--tokens-entrada", dest="tokens_entrada", type=int, default=None)
    p_log.add_argument("--tokens-saida", dest="tokens_saida", type=int, default=None)
    p_log.add_argument("--tokens-cache", dest="tokens_cache", type=int, default=None)
    p_log.add_argument("--duracao-ms", dest="duracao_ms", type=int, default=None)
    p_log.add_argument("--ok", dest="ok", type=lambda x: x.lower() in ("1", "true", "sim", "yes"), default=None)
    p_log.add_argument("--origem", dest="origem")
    p_log.add_argument("--nota", dest="nota")
    p_log.add_argument("--fingerprint", dest="fingerprint")
    p_log.add_argument("--ts", dest="ts")
    p_log.add_argument("--json", action="store_true")
    p_log.set_defaults(func=cmd_log)

    p_imp = sub.add_parser("import", help="Importa logs de um agente.")
    p_imp.add_argument("agente", choices=["opencode"])
    p_imp.add_argument("arquivo")
    p_imp.set_defaults(func=cmd_import)

    p_det = sub.add_parser("detect", help="Lista tarefas repetidas e caras.")
    p_det.add_argument("--min-ocorrencias", dest="min_ocorrencias", type=int, default=3)
    p_det.add_argument("--dias", dest="dias", type=int, default=14)
    p_det.add_argument("--custo-min", dest="custo_min", type=float, default=0)
    p_det.add_argument("--incluir-cache", dest="incluir_cache", action="store_true")
    p_det.add_argument("--origem", dest="origem", choices=["ia", "atalho", "todas"], default="ia")
    p_det.add_argument("--limite", dest="limite", type=int, default=20)
    p_det.add_argument("--ate", dest="ate", default=None)
    p_det.add_argument("--json", action="store_true")
    p_det.set_defaults(func=cmd_detect)

    p_est = sub.add_parser("estimate", help="Estima economia de um candidato.")
    p_est.add_argument("impressao_digital", nargs="?")
    p_est.add_argument("--stdin", action="store_true")
    p_est.add_argument("--tokens-atalho", dest="tokens_atalho", type=int, default=None)
    p_est.add_argument("--tokens-criacao", dest="tokens_criacao", type=int, default=None)
    p_est.add_argument("--tokens-reparo", dest="tokens_reparo", type=int, default=None)
    p_est.add_argument("--modelo", dest="modelo", default=None)
    p_est.add_argument("--precos", dest="precos", default=None)
    p_est.add_argument("--cenarios", dest="cenarios", default="0,0.1,0.3")
    p_est.add_argument("--dias", dest="dias", type=int, default=14)
    p_est.add_argument("--incluir-cache", dest="incluir_cache", action="store_true")
    p_est.add_argument("--ate", dest="ate", default=None)
    p_est.add_argument("--json", action="store_true")
    p_est.set_defaults(func=cmd_estimate)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())