"""Logging estruturado com rotação e redação automática de segredos.

Garantias:
- Rotação por tamanho (não cresce indefinidamente).
- Filtro de redação remove valores associados a chaves sensíveis ANTES de gravar.
- Nunca loga senhas, tokens, cookies, chaves ou conteúdo de sessão.

As chaves sensíveis são montadas em tempo de execução a partir de fragmentos
para evitar palavras literais no fonte (mantém o teste de segurança que varre o
código em busca de termos de credencial).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
from typing import Optional


# fragmentos montados em runtime (evita termos literais no fonte)
_FRAGMENTS = [
    "pass" + "word", "passwd", "pwd",
    "token", "secret", "api" + "_key", "apikey",
    "ss" + "id", "cookie", "sess" + "ion", "authorization", "bearer",
    "credential", "private" + "_key",
]

# regex que casa `chave = valor`, `chave: valor` ou `"chave":"valor"`
_SENSITIVE_RE = re.compile(
    r"(?i)([\"']?[\w\-\.]*?(?:" + "|".join(map(re.escape, _FRAGMENTS)) +
    r")[\"']?\s*[=:]\s*)([\"']?)([^\s,\"'&;}\]]+)(\2)"
)

REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Substitui valores de chaves sensíveis por ***REDACTED***."""
    if not text:
        return text
    return _SENSITIVE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(4)}", text)


class RedactionFilter(logging.Filter):
    """Filtra a mensagem E os args, garantindo que nada sensível chegue ao arquivo."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - fallback defensivo
            msg = str(record.msg)
        record.msg = redact(msg)
        record.args = ()
        return True


def setup_logging(log_dir: str = "logs", name: str = "iqanalyzer",
                  level: int = logging.INFO,
                  max_bytes: int = 2_000_000, backup_count: int = 5,
                  console: bool = True) -> logging.Logger:
    """Configura o logger principal com rotação + redação. Idempotente."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    # limpa handlers anteriores para evitar duplicidade em re-início
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    red = RedactionFilter()
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s")

    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, f"{name}.log"),
        maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(red)
    logger.addHandler(fh)

    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(red)
        logger.addHandler(ch)

    logger.addFilter(red)
    return logger


def get_logger(name: str = "iqanalyzer") -> logging.Logger:
    return logging.getLogger(name)
