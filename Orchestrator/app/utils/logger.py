"""
SPM Orchestrator - Logging Setup

Logging strutturato su stdout (per journald) e file opzionale.
"""

import logging
import sys
import os
from pythonjsonlogger import jsonlogger

from app.config import Config


def setup_logging():
    """
    Configura logging dell'applicazione.
    - Stdout: JSON strutturato (per journald/systemd)
    - File: JSON strutturato (opzionale, se LOG_FILE configurato)
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, Config.LOG_LEVEL, logging.INFO))

    # Formato JSON
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Handler stdout (sempre attivo - per journald)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)

    # Handler file (opzionale)
    log_file = Config.LOG_FILE
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                file_handler = logging.FileHandler(log_file)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
            except PermissionError:
                root_logger.warning(
                    f"Cannot create log directory {log_dir}, logging to stdout only"
                )

    # Silenzia log verbosi di librerie esterne
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    return root_logger
