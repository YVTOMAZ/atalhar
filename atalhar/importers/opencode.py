"""Adaptador de log do OpenCode (formato events.jsonl)."""

import json
from pathlib import Path

from ..fingerprint import fingerprint, normalize, sanitize_url
from ..ledger import log_execucao


def _get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _extract_tokens(obj: dict) -> dict:
    t = {"tokens_entrada": 0, "tokens_saida": 0, "tokens_cache": 0}
    # nested tokens
    tok = _get(obj, "tokens", "token", "usage", "tokensUsage")
    if isinstance(tok, dict):
        t["tokens_entrada"] = int(tok.get("input") or tok.get("prompt") or tok.get("input_tokens") or 0)
        t["tokens_saida"] = int(tok.get("output") or tok.get("completion") or tok.get("output_tokens") or 0)
        cache = tok.get("cache")
        if isinstance(cache, dict):
            t["tokens_cache"] = int(cache.get("read") or cache.get("cached") or 0) + int(cache.get("write") or 0)
        else:
            t["tokens_cache"] = int(tok.get("cache_read") or tok.get("cached") or 0)
    # top-level
    if "tokens_entrada" in obj:
        t["tokens_entrada"] = int(obj.get("tokens_entrada") or 0)
    if "tokens_saida" in obj:
        t["tokens_saida"] = int(obj.get("tokens_saida") or 0)
    if "tokens_cache" in obj:
        t["tokens_cache"] = int(obj.get("tokens_cache") or 0)
    if "tokens_input" in obj:
        t["tokens_entrada"] = int(obj.get("tokens_input") or 0)
    if "tokens_output" in obj:
        t["tokens_saida"] = int(obj.get("tokens_output") or 0)
    return t


def _infer_tipo(tool: str, inp: dict) -> str:
    name = (tool or "").lower()
    if any(x in name for x in ("shell", "bash", "command", "exec")):
        return "comando"
    if any(x in name for x in ("webfetch", "navigate", "browser", "playwright")):
        return "navegar"
    if any(x in name for x in ("scrape", "crawl")):
        return "raspar"
    if any(x in name for x in ("api", "gh", "http")):
        return "api"
    return "consultar"


def _extract_tool(obj: dict):
    # returns (tool_name, input_dict) or None
    for key in ("tool", "name", "tool_name", "toolName"):
        v = obj.get(key)
        if isinstance(v, str):
            inp = obj.get("input") or obj.get("args") or obj.get("arguments") or {}
            if not isinstance(inp, dict):
                inp = {"value": inp}
            return v, inp
    # nested part
    part = obj.get("part")
    if isinstance(part, dict):
        t = part.get("tool") or part.get("name")
        if isinstance(t, str):
            inp = part.get("input") or part.get("args") or {}
            if not isinstance(inp, dict):
                inp = {"value": inp}
            return t, inp
    tu = obj.get("tool_use") or obj.get("toolUse")
    if isinstance(tu, dict):
        t = tu.get("name") or tu.get("tool")
        if isinstance(t, str):
            inp = tu.get("input") or tu.get("args") or {}
            if not isinstance(inp, dict):
                inp = {"value": inp}
            return t, inp
    return None


def _target_from_input(inp: dict, tool: str) -> str:
    if not isinstance(inp, dict):
        return tool
    for key in ("url", "uri", "endpoint"):
        v = inp.get(key)
        if v:
            return sanitize_url(str(v))
    for key in ("command", "cmd", "script"):
        v = inp.get(key)
        if v:
            # use first token-ish as target host/tool, keep full for fingerprint via forma
            return tool
    return tool


def _forma_from_input(inp: dict) -> str:
    if not isinstance(inp, dict):
        return str(inp)
    for key in ("command", "cmd", "script", "path", "file"):
        v = inp.get(key)
        if v:
            return str(v)
    return json.dumps(inp, sort_keys=True, ensure_ascii=False)


def import_opencode(path, db_path=None) -> dict:
    imported = 0
    ignored = 0
    pending_tokens = None
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                ignored += 1
                continue
            if not isinstance(obj, dict):
                ignored += 1
                continue

            toks = _extract_tokens(obj)
            has_tokens = any(toks[k] for k in toks)
            tool_info = _extract_tool(obj)

            if tool_info is None:
                # step-finish style: store tokens for next tool
                if has_tokens:
                    pending_tokens = toks
                else:
                    ignored += 1
                continue

            tool, inp = tool_info
            if has_tokens:
                use_toks = toks
                pending_tokens = None
            elif pending_tokens is not None:
                use_toks = pending_tokens
                pending_tokens = None
            else:
                use_toks = {"tokens_entrada": 0, "tokens_saida": 0, "tokens_cache": 0}

            tipo = _infer_tipo(tool, inp)
            target = _target_from_input(inp, tool)
            forma = _forma_from_input(inp)
            fp = fingerprint(tipo, target, forma)

            ts = _get(obj, "ts", "timestamp", "time", "created_at")
            agente = _get(obj, "agente", "agent") or "opencode"
            modelo = _get(obj, "modelo", "model")

            ok = True
            # infer ok from result/exit_code
            res = _get(obj, "result", "res", "response")
            if isinstance(res, dict):
                if "success" in res:
                    ok = bool(res.get("success"))
                elif "exit_code" in res:
                    ok = int(res.get("exit_code") or 0) == 0
            if "exit_code" in obj:
                ok = int(obj.get("exit_code") or 0) == 0
            if "ok" in obj:
                ok = bool(obj.get("ok"))

            row = {
                "ts": ts,
                "agente": agente,
                "modelo": modelo,
                "tipo": tipo,
                "alvo": target,
                "impressao_digital": fp,
                "tokens_entrada": use_toks["tokens_entrada"],
                "tokens_saida": use_toks["tokens_saida"],
                "tokens_cache": use_toks["tokens_cache"],
                "duracao_ms": _get(obj, "duracao_ms", "duration_ms", "duration"),
                "ok": ok,
                "origem": "ia",
                "nota": _get(obj, "nota", "note", "description") or "",
            }
            log_execucao(row, path=db_path)
            imported += 1

    return {"imported": imported, "ignored": ignored}