"""
SPM Orchestrator - Prometheus Client

Client per raccogliere metriche dai sistemi di test via Prometheus HTTP API.
Usato dal Test Engine per:
  - Baseline metriche pre-patch (CPU, memoria)
  - Snapshot metriche post-patch
  - Calcolo delta e valutazione vs threshold

Graceful degradation: se Prometheus non è raggiungibile o non configurato,
tutti i metodi ritornano None/valori vuoti senza sollevare eccezioni.
Il Test Engine considera la validazione metriche "skipped" in questo caso.

Prerequisiti infrastruttura (non ancora configurati — nota futura):
  - node_exporter installato sui sistemi test (porta :9100)
  - Prometheus configurato per scrape i sistemi test
  - PROMETHEUS_URL punta all'istanza Prometheus

Metriche usate (node_exporter standard):
  - CPU:    node_cpu_seconds_total{mode="idle"}
  - Memoria: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
"""

import logging
from typing import Optional

import requests
import urllib3

from app.config import Config

logger = logging.getLogger(__name__)

# Sopprime warning SSL (Prometheus di solito è HTTP, ma per sicurezza)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_TIMEOUT = Config.PROMETHEUS_TIMEOUT

# Porta standard node_exporter
_NODE_EXPORTER_PORT = 9100

# Range di lookback per le metriche rate() — 5 minuti
_RATE_WINDOW = "5m"


# ─────────────────────────────────────────────
# PromQL queries
# ─────────────────────────────────────────────

def _cpu_query(instance: str) -> str:
    """Percentuale CPU usata (100 - idle)."""
    return (
        f'100 - (avg by(instance) ('
        f'rate(node_cpu_seconds_total{{mode="idle",instance="{instance}"}}[{_RATE_WINDOW}])'
        f') * 100)'
    )


def _memory_query(instance: str) -> str:
    """Percentuale memoria usata."""
    return (
        f'100 * (1 - '
        f'node_memory_MemAvailable_bytes{{instance="{instance}"}} '
        f'/ node_memory_MemTotal_bytes{{instance="{instance}"}})'
    )


# ─────────────────────────────────────────────
# PrometheusClient
# ─────────────────────────────────────────────

class PrometheusClient:
    """
    Client Prometheus HTTP API (stateless — nessun login richiesto).

    Tutti i metodi hanno fallback graceful: ritornano None o dict vuoto
    se Prometheus non è disponibile, senza sollevare eccezioni.
    Il Test Engine usa is_available() per decidere se saltare la validazione.

    Uso:
        prom = PrometheusClient()
        if prom.is_available():
            baseline = prom.get_snapshot(system_ip)
            # ... applica patch ...
            post = prom.get_snapshot(system_ip)
            evaluation = prom.evaluate_delta(baseline, post)
    """

    def __init__(self):
        self._base_url = Config.PROMETHEUS_URL.rstrip("/")
        self._timeout = _DEFAULT_TIMEOUT

    def _instance_label(self, system_ip: str) -> str:
        """Costruisce l'instance label Prometheus: IP:9100."""
        return f"{system_ip}:{_NODE_EXPORTER_PORT}"

    def _query(self, promql: str) -> Optional[float]:
        """
        Esegue una query PromQL istantanea (instant query).
        Ritorna il valore float del primo risultato, None se errore o assente.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/query",
                params={"query": promql},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "success":
                logger.warning(f"Prometheus query failed: {data.get('error', 'unknown')}")
                return None

            results = data.get("data", {}).get("result", [])
            if not results:
                return None

            # Ritorna il valore del primo risultato (vettore istantaneo)
            value = results[0].get("value", [None, None])[1]
            return round(float(value), 2) if value is not None else None

        except requests.exceptions.ConnectionError:
            logger.debug("Prometheus not reachable (ConnectionError)")
            return None
        except requests.exceptions.Timeout:
            logger.warning("Prometheus query timed out")
            return None
        except Exception as e:
            logger.warning(f"Prometheus query error: {e}")
            return None

    # ── API pubblica ─────────────────────────

    def is_available(self) -> bool:
        """
        Verifica che Prometheus sia raggiungibile (GET /api/v1/status/runtimeinfo).
        Ritorna False silenziosamente se non disponibile.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/status/runtimeinfo",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_cpu_usage(self, system_ip: str) -> Optional[float]:
        """
        Percentuale CPU usata dal sistema (media su tutti i core, ultimi 5 min).
        Ritorna float (es. 23.4) oppure None se non disponibile.
        """
        instance = self._instance_label(system_ip)
        value = self._query(_cpu_query(instance))
        if value is not None:
            logger.debug(f"Prometheus CPU {system_ip}: {value}%")
        return value

    def get_memory_usage(self, system_ip: str) -> Optional[float]:
        """
        Percentuale memoria usata dal sistema.
        Ritorna float (es. 67.8) oppure None se non disponibile.
        """
        instance = self._instance_label(system_ip)
        value = self._query(_memory_query(instance))
        if value is not None:
            logger.debug(f"Prometheus MEM {system_ip}: {value}%")
        return value

    def get_snapshot(self, system_ip: str) -> dict:
        """
        Snapshot completo delle metriche di un sistema.
        Ritorna dict con cpu_percent e memory_percent.
        I valori sono None se Prometheus non è disponibile.

        Usato per raccogliere baseline pre-patch e post-patch.
        """
        cpu = self.get_cpu_usage(system_ip)
        mem = self.get_memory_usage(system_ip)

        snapshot = {
            "cpu_percent":    cpu,
            "memory_percent": mem,
            "available":      cpu is not None or mem is not None,
        }

        logger.info(
            f"Prometheus snapshot {system_ip}: "
            f"CPU={cpu}% MEM={mem}%"
        )
        return snapshot

    def evaluate_delta(self, baseline: dict, post_patch: dict) -> dict:
        """
        Calcola delta tra baseline e post-patch e valuta vs threshold.

        Ritorna:
          {
            "cpu_delta":    float | None,   # post - baseline (positivo = peggiorato)
            "memory_delta": float | None,
            "cpu_ok":       bool | None,    # None se dati non disponibili
            "memory_ok":    bool | None,
            "passed":       bool,           # True se tutti i check disponibili passano
            "skipped":      bool,           # True se Prometheus non disponibile
          }
        """
        cpu_base = baseline.get("cpu_percent")
        cpu_post = post_patch.get("cpu_percent")
        mem_base = baseline.get("memory_percent")
        mem_post = post_patch.get("memory_percent")

        # Se nessun dato disponibile → skip validazione
        if cpu_base is None and mem_base is None:
            logger.warning(
                "Prometheus metrics not available — skipping metric validation"
            )
            return {
                "cpu_delta":    None,
                "memory_delta": None,
                "cpu_ok":       None,
                "memory_ok":    None,
                "passed":       True,   # conservativo: non blocca il test
                "skipped":      True,
            }

        cpu_delta = None
        cpu_ok = None
        if cpu_base is not None and cpu_post is not None:
            cpu_delta = round(cpu_post - cpu_base, 2)
            cpu_ok = cpu_delta <= Config.TEST_CPU_DELTA

        mem_delta = None
        mem_ok = None
        if mem_base is not None and mem_post is not None:
            mem_delta = round(mem_post - mem_base, 2)
            mem_ok = mem_delta <= Config.TEST_MEMORY_DELTA

        # passed = True solo se tutti i check disponibili sono OK
        checks = [v for v in [cpu_ok, mem_ok] if v is not None]
        passed = all(checks) if checks else True

        if not passed:
            logger.warning(
                f"Prometheus delta check FAILED: "
                f"CPU Δ={cpu_delta}% (limit={Config.TEST_CPU_DELTA}%), "
                f"MEM Δ={mem_delta}% (limit={Config.TEST_MEMORY_DELTA}%)"
            )
        else:
            logger.info(
                f"Prometheus delta check OK: "
                f"CPU Δ={cpu_delta}% MEM Δ={mem_delta}%"
            )

        return {
            "cpu_delta":    cpu_delta,
            "memory_delta": mem_delta,
            "cpu_ok":       cpu_ok,
            "memory_ok":    mem_ok,
            "passed":       passed,
            "skipped":      False,
        }
