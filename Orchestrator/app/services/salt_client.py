"""
SPM Orchestrator - Salt API Client

Client per interagire con il Salt Master via Salt API REST (:9080).
Usato dal Test Engine per:
  - Applicare patch (pkg.install) sui sistemi di test
  - Verificare servizi critici post-patch (service.status)
  - Eseguire reboot controllato (system.reboot)
  - Attendere che il minion torni online dopo il reboot (test.ping)

Pattern: SaltSession come context manager (1 login/logout per operazione).
SSL: rispetta Config.UYUNI_VERIFY_SSL (stessa CA del UYUNI server).
"""

import logging
import time
from typing import Optional

import requests
import urllib3

from app.config import Config

logger = logging.getLogger(__name__)

# Sopprime warning SSL se verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Timeout default per chiamate Salt API
_DEFAULT_TIMEOUT = 30  # secondi


# ─────────────────────────────────────────────
# SaltSession — context manager con token auth
# ─────────────────────────────────────────────

class SaltSession:
    """
    Sessione Salt API con login/logout automatico.

    Uso:
        with SaltSession() as salt:
            salt.apply_packages("test-ubuntu-01", ["openssl", "libssl3"])
            salt.get_failed_services("test-ubuntu-01", ["nginx", "ssh"])

    Autenticazione: POST /login con eauth='pam'.
    Il token ottenuto viene usato in X-Auth-Token per le chiamate successive.
    """

    def __init__(self):
        self._base_url = Config.SALT_API_URL.rstrip("/")
        self._verify_ssl = Config.UYUNI_VERIFY_SSL
        self._token: Optional[str] = None
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def __enter__(self) -> "SaltSession":
        self._login()
        return self

    def __exit__(self, *_) -> None:
        self._logout()

    # ── Autenticazione ───────────────────────

    def _login(self) -> None:
        """Autentica contro Salt API e salva il token."""
        resp = self._session.post(
            f"{self._base_url}/login",
            json={
                "username": Config.SALT_API_USER,
                "password": Config.SALT_API_PASSWORD,
                "eauth":    "pam",
            },
            verify=self._verify_ssl,
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["return"][0]["token"]
        self._session.headers["X-Auth-Token"] = self._token
        logger.debug("Salt API: login OK")

    def _logout(self) -> None:
        """Invalida il token Salt API."""
        if not self._token:
            return
        try:
            self._session.post(
                f"{self._base_url}/logout",
                verify=self._verify_ssl,
                timeout=_DEFAULT_TIMEOUT,
            )
            logger.debug("Salt API: logout OK")
        except Exception:
            pass
        finally:
            self._token = None
            self._session.headers.pop("X-Auth-Token", None)

    # ── Esecuzione comandi Salt ──────────────

    def _run(self, minion_id: str, fun: str, arg: list = None, kwarg: dict = None) -> dict:
        """
        Esegue un comando Salt via client 'local' (sincrono).
        Ritorna il risultato per il minion, oppure {} in caso di errore.
        """
        payload = {
            "client": "local",
            "tgt":    minion_id,
            "fun":    fun,
        }
        if arg:
            payload["arg"] = arg
        if kwarg:
            payload["kwarg"] = kwarg

        resp = self._session.post(
            f"{self._base_url}/",
            json=[payload],
            verify=self._verify_ssl,
            timeout=_DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        # Salt API ritorna {"return": [{minion_id: result}]}
        return result.get("return", [{}])[0].get(minion_id, {})

    # ── API pubblica ─────────────────────────

    def ping(self, minion_id: str) -> bool:
        """
        Verifica che il minion sia raggiungibile (test.ping).
        Ritorna True se risponde, False altrimenti.
        """
        try:
            result = self._run(minion_id, "test.ping")
            return result is True
        except Exception as e:
            logger.warning(f"Salt ping({minion_id!r}) failed: {e}")
            return False

    def apply_packages(self, minion_id: str, packages: list) -> dict:
        """
        Installa/aggiorna i pacchetti specificati sul minion (pkg.install).

        packages: lista di nomi pacchetto ['openssl', 'libssl3', ...]
        Ritorna il dict Salt con i pacchetti installati/aggiornati,
        oppure {} in caso di errore.

        Esempio risposta Salt:
          {'openssl': {'old': '3.0.2', 'new': '3.0.2-1ubuntu1.1'}, ...}
        """
        if not packages:
            logger.warning(f"Salt apply_packages({minion_id!r}): no packages provided")
            return {}
        try:
            result = self._run(
                minion_id,
                "pkg.install",
                kwarg={"pkgs": packages, "refresh": True},
            )
            logger.info(
                f"Salt: {minion_id!r} — {len(result)} packages installed/updated"
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"Salt apply_packages({minion_id!r}) failed: {e}")
            raise

    def get_failed_services(self, minion_id: str, services: list) -> list:
        """
        Verifica lo stato dei servizi specificati.
        Ritorna lista dei servizi che risultano DOWN (non attivi).

        services: lista di nomi servizio ['nginx', 'ssh', 'postgresql']
        """
        if not services:
            return []

        failed = []
        for svc in services:
            try:
                result = self._run(minion_id, "service.status", arg=[svc])
                # Salt ritorna True se attivo, False se non attivo
                if result is not True:
                    failed.append(svc)
                    logger.warning(
                        f"Salt: service {svc!r} is DOWN on {minion_id!r}"
                    )
            except Exception as e:
                logger.warning(
                    f"Salt service.status({svc!r}, {minion_id!r}) failed: {e}"
                )
                # In caso di errore, conservativo: considera il servizio failed
                failed.append(svc)

        logger.info(
            f"Salt: {minion_id!r} — "
            f"{len(services) - len(failed)}/{len(services)} services OK, "
            f"{len(failed)} DOWN: {failed}"
        )
        return failed

    def reboot(self, minion_id: str, wait_seconds: int = 5) -> bool:
        """
        Avvia il reboot del minion (system.reboot).
        wait_seconds: ritardo prima del reboot (secondi, default 5)
        Ritorna True se il comando è stato accettato.
        """
        try:
            self._run(
                minion_id,
                "system.reboot",
                kwarg={"at_time": wait_seconds},
            )
            logger.info(f"Salt: reboot scheduled on {minion_id!r} in {wait_seconds}s")
            return True
        except Exception as e:
            logger.error(f"Salt reboot({minion_id!r}) failed: {e}")
            return False

    def wait_online(
        self,
        minion_id: str,
        timeout: int = None,
        poll_interval: int = 10,
    ) -> bool:
        """
        Attende che il minion torni online dopo un reboot (polling test.ping).

        timeout:       secondi massimi di attesa (default: Config.TEST_WAIT_AFTER_REBOOT)
        poll_interval: secondi tra ogni tentativo (default: 10)
        Ritorna True se il minion torna online, False se timeout scaduto.
        """
        if timeout is None:
            timeout = Config.TEST_WAIT_AFTER_REBOOT

        deadline = time.monotonic() + timeout
        attempt = 0

        logger.info(
            f"Salt: waiting for {minion_id!r} to come back online "
            f"(timeout={timeout}s, poll={poll_interval}s)"
        )

        while time.monotonic() < deadline:
            attempt += 1
            # Pausa iniziale: il minion deve prima avviarsi il reboot
            time.sleep(poll_interval)

            if self.ping(minion_id):
                elapsed = round(time.monotonic() - (deadline - timeout), 1)
                logger.info(
                    f"Salt: {minion_id!r} is back online "
                    f"(attempt {attempt}, elapsed ~{elapsed}s)"
                )
                return True

            logger.debug(
                f"Salt: {minion_id!r} not yet online (attempt {attempt})"
            )

        logger.error(
            f"Salt: {minion_id!r} did NOT come back online within {timeout}s"
        )
        return False


# ─────────────────────────────────────────────
# Helper: carica servizi critici da orchestrator_config
# ─────────────────────────────────────────────

def get_critical_services(target_os: str) -> list:
    """
    Ritorna la lista dei servizi critici da monitorare per il target_os.
    Carica da orchestrator_config (key='critical_services'), fallback su defaults.

    target_os: 'ubuntu' | 'rhel'
    """
    defaults = {
        "ubuntu": ["ssh", "cron", "rsyslog", "systemd-journald"],
        "rhel":   ["sshd", "crond", "rsyslog", "systemd-journald"],
    }
    try:
        from app.services.db import get_db
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT value FROM orchestrator_config"
                " WHERE key = 'critical_services'"
            )
            row = cur.fetchone()
            if row and row["value"]:
                cfg = row["value"]
                if target_os in cfg:
                    return cfg[target_os]
    except Exception as e:
        logger.warning(f"Could not load critical_services from DB: {e}")

    return defaults.get(target_os, defaults["ubuntu"])
