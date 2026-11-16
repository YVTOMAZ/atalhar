"""CLI do atalhar."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone

from . import __version__
from .detect import detectar, parse_ts
from .fingerprint import fingerprint, sanitize_url
from .ledger import db_path, init_db, log_execucao, redact_nota
from .importers.opencode import import_opencode


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

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())