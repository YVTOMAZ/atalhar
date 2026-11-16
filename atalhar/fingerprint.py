"""Impressao digital estavel de uma tarefa repetida."""

import hashlib
import re

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER_RE = re.compile(r"\b\d+\b")


def normalize(value: str) -> str:
    """Substitui UUIDs, datas e numeros por placeholders estaveis."""
    if not value:
        return ""
    s = _UUID_RE.sub("{id}", value)
    s = _DATE_RE.sub("{data}", s)
    s = _NUMBER_RE.sub("{n}", s)
    return s


def sanitize_url(url: str) -> str:
    """Remove query string, fragmento e credenciais de uma URL."""
    if not url or "://" not in url:
        return url.strip()
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url.strip())
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def fingerprint(tipo: str, alvo: str, forma: str = "") -> str:
    """Hash estavel de (tipo, alvo normalizado, forma)."""
    base = "|".join([tipo.strip().lower(), normalize(sanitize_url(alvo)), normalize(forma)])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]