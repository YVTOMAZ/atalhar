"""CLI do atalhar."""

import argparse
import json
import sys

from . import __version__
from .fingerprint import fingerprint, sanitize_url
from .ledger import connect, data_dir, init_db, insert_execucao, log_execucao, now_iso, redact_nota
from .importers.opencode import import_opencode


def _print(msg):
    print(msg)


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

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())