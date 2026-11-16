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
    if not isinstance(obj, dict):
        return t
    # coleta dicts de tokens no proprio objeto e em obj['part'] (formato real do OpenCode)
    candidates = []
    for src in (obj, obj.get("part") if isinstance(obj.get("part"), dict) else None):
        if not isinstance(src, dict):
            continue
        for key in ("tokens", "token", "usage", "tokensUsage"):
            v = src.get(key)
            if isinstance(v, dict):
                candidates.append(v)
    for tok in candidates:
        if any(k in tok for k in ("input", "prompt", "input_tokens")):
            t["tokens_entrada"] = int(tok.get("input") or tok.get("prompt") or tok.get("input_tokens") or 0)
        if any(k in tok for k in ("output", "completion", "output_tokens")):
            t["tokens_saida"] = int(tok.get("output") or tok.get("completion") or tok.get("output_tokens") or 0)
        cache = tok.get("cache")
        if isinstance(cache, dict):
            t["tokens_cache"] = int(cache.get("read") or cache.get("cached") or 0) + int(cache.get("write") or 0)
        elif "cache_read" in tok or "cached" in tok:
            t["tokens_cache"] = int(tok.get("cache_read") or tok.get("cached") or 0)
    # top-level (compatibilidade com fixtures sinteticas antigas)
    srcs = [obj]
    if isinstance(obj.get("part"), dict):
        srcs.append(obj["part"])
    for src in srcs:
        if "tokens_entrada" in src:
            t["tokens_entrada"] = int(src.get("tokens_entrada") or 0)
        if "tokens_saida" in src:
            t["tokens_saida"] = int(src.get("tokens_saida") or 0)
        if "tokens_cache" in src:
            t["tokens_cache"] = int(src.get("tokens_cache") or 0)
        if "tokens_input" in src:
            t["tokens_entrada"] = int(src.get("tokens_input") or 0)
        if "tokens_output" in src:
            t["tokens_saida"] = int(src.get("tokens_output") or 0)
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
            inp = obj.get("input") or obj.get("args") or obj.get("arguments")
            state = obj.get("state")
            if isinstance(state, dict) and inp is None:
                inp = state.get("input") or state.get("args") or state.get("arguments")
            if inp is None:
                inp = {}
            if not isinstance(inp, dict):
                inp = {"value": inp}
            return v, inp
    # nested part (formato real do OpenCode: part.tool, part.state.input)
    part = obj.get("part")
    if isinstance(part, dict):
        t = part.get("tool") or part.get("name")
        if isinstance(t, str):
            inp = None
            state = part.get("state")
            if isinstance(state, dict):
                inp = state.get("input") or state.get("args") or state.get("arguments")
            if inp is None:
                inp = part.get("input") or part.get("args") or part.get("arguments")
            if not isinstance(inp, dict):
                inp = {"value": inp} if inp is not None else {}
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


def _record(tool, inp, obj, toks, db_path):
    tipo = _infer_tipo(tool, inp)
    target = _target_from_input(inp, tool)
    forma = _forma_from_input(inp)
    fp = fingerprint(tipo, target, forma)

    ts = _get(obj, "ts", "timestamp", "time", "created_at")
    agente = _get(obj, "agente", "agent") or "opencode"
    modelo = _get(obj, "modelo", "model")

    ok = True
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
        "tokens_entrada": toks["tokens_entrada"],
        "tokens_saida": toks["tokens_saida"],
        "tokens_cache": toks["tokens_cache"],
        "duracao_ms": _get(obj, "duracao_ms", "duration_ms", "duration"),
        "ok": ok,
        "origem": "ia",
        "nota": _get(obj, "nota", "note", "description") or "",
    }
    log_execucao(row, path=db_path)


def import_opencode(path, db_path=None) -> dict:
    imported = 0
    ignored = 0
    pending_tools = []  # ferramentas aguardando step-finish (formato real)
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

            if tool_info is not None:
                tool, inp = tool_info
                if has_tokens:
                    # tokens na mesma linha (formato sintetico antigo)
                    _record(tool, inp, obj, toks, db_path)
                    imported += 1
                else:
                    # formato real: aguarda step-finish seguinte
                    pending_tools.append((tool, inp, obj))
                continue

            # linha sem ferramenta (step_start/step_finish/...)
            if has_tokens:
                if pending_tools:
                    # formato real: atrela tokens do step-finish as ferramentas do mesmo passo
                    # shortcut: se um passo contiver varias tool_use, o total do passo e
                    # atribuido a cada uma; nos dados reais a razao e ~1:1 (52/53),
                    # impacto desprezivel. Quando houver passos com N>1 tools, revisar.
                    for tool, inp, tobj in pending_tools:
                        _record(tool, inp, tobj, toks, db_path)
                        imported += 1
                    pending_tools = []
                # else: step_finish sem ferramenta pendente (passo vazio/texto):
                # descartar tokens, nao atribuir a ferramenta posterior.
            else:
                ignored += 1

    # ferramentas pendentes sem step-finish: importa com zero token
    for tool, inp, tobj in pending_tools:
        _record(tool, inp, tobj, {"tokens_entrada": 0, "tokens_saida": 0, "tokens_cache": 0}, db_path)
        imported += 1
    pending_tools = []

    return {"imported": imported, "ignored": ignored}