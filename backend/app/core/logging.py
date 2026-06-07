"""core/logging.py — 结构化日志 + 审计事件"""
from __future__ import annotations

import logging
import sys

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def audit(event: str, **fields) -> None:
    """关键审计事件(接入仓库/改授权/吊销 Key/扫描)。M5 可落表。"""
    log = get_logger("audit")
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    log.info("AUDIT %s %s", event, detail)
