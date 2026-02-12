"""
SPM Orchestrator - Success Score Calculator

Calcola il Success Score per ogni errata per determinare l'ordine di test.
Score più alto = patch più sicura = testare prima.

Version: 1.0
Date: 2026-02-05
"""

import re
import os
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class ScoreConfig:
    """Configurazione pesi per Success Score (tutti configurabili)"""

    # Penalità base
    KERNEL_PENALTY: int = 30          # Patch kernel/bootloader
    REBOOT_PENALTY: int = 15          # Richiede reboot
    CONFIG_PENALTY: int = 10          # Modifica file config

    # Penalità scalari
    DEPENDENCY_PENALTY_PER: int = 3   # Per ogni dipendenza
    DEPENDENCY_PENALTY_MAX: int = 15  # Cap massimo

    SIZE_PENALTY_PER_MB: int = 2      # Per ogni MB
    SIZE_PENALTY_MAX: int = 10        # Cap massimo

    # Penalità storico
    HISTORY_PENALTY_MAX: int = 20     # Penalità massima per failure rate
    MIN_TESTS_FOR_HISTORY: int = 3    # Minimo test per considerare storico

    # Bonus
    SMALL_PATCH_BONUS: int = 5        # Patch < threshold
    SMALL_PATCH_THRESHOLD_KB: int = 100

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScoreConfig':
        """Crea config da dizionario (es. da database)"""
        return cls(
            KERNEL_PENALTY=data.get('kernel_penalty', 30),
            REBOOT_PENALTY=data.get('reboot_penalty', 15),
            CONFIG_PENALTY=data.get('config_penalty', 10),
            DEPENDENCY_PENALTY_PER=data.get('dependency_penalty_per', 3),
            DEPENDENCY_PENALTY_MAX=data.get('dependency_penalty_max', 15),
            SIZE_PENALTY_PER_MB=data.get('size_penalty_per_mb', 2),
            SIZE_PENALTY_MAX=data.get('size_penalty_max', 10),
            HISTORY_PENALTY_MAX=data.get('history_penalty_max', 20),
            MIN_TESTS_FOR_HISTORY=data.get('min_tests_for_history', 3),
            SMALL_PATCH_BONUS=data.get('small_patch_bonus', 5),
            SMALL_PATCH_THRESHOLD_KB=data.get('small_patch_threshold_kb', 100),
        )

    @classmethod
    def from_env(cls) -> 'ScoreConfig':
        """Crea config da environment variables"""
        return cls(
            KERNEL_PENALTY=int(os.getenv('SCORE_KERNEL_PENALTY', 30)),
            REBOOT_PENALTY=int(os.getenv('SCORE_REBOOT_PENALTY', 15)),
            CONFIG_PENALTY=int(os.getenv('SCORE_CONFIG_PENALTY', 10)),
            DEPENDENCY_PENALTY_PER=int(os.getenv('SCORE_DEP_PENALTY_PER', 3)),
            DEPENDENCY_PENALTY_MAX=int(os.getenv('SCORE_DEP_PENALTY_MAX', 15)),
            SIZE_PENALTY_PER_MB=int(os.getenv('SCORE_SIZE_PENALTY_MB', 2)),
            SIZE_PENALTY_MAX=int(os.getenv('SCORE_SIZE_PENALTY_MAX', 10)),
            HISTORY_PENALTY_MAX=int(os.getenv('SCORE_HISTORY_PENALTY_MAX', 20)),
            MIN_TESTS_FOR_HISTORY=int(os.getenv('SCORE_MIN_TESTS_HISTORY', 3)),
            SMALL_PATCH_BONUS=int(os.getenv('SCORE_SMALL_BONUS', 5)),
            SMALL_PATCH_THRESHOLD_KB=int(os.getenv('SCORE_SMALL_THRESHOLD_KB', 100)),
        )


# ============================================================
# PATTERN RECOGNITION
# ============================================================

# Pattern per identificare pacchetti kernel/boot
KERNEL_PATTERNS = [
    r'^linux-image',
    r'^linux-headers',
    r'^linux-modules',
    r'^linux-generic',
    r'^linux-virtual',
    r'^linux-aws',
    r'^linux-azure',
    r'^linux-gcp',
    r'^kernel-',
    r'^grub',
    r'^grub2',
    r'^shim-signed',
    r'^shim-unsigned',
    r'^systemd-boot',
    r'^dracut',
    r'^initramfs-tools',
    r'^mkinitcpio',
]

# Pattern per pacchetti che tipicamente richiedono reboot
REBOOT_PATTERNS = [
    r'^linux-',
    r'^kernel-',
    r'^glibc',
    r'^libc6',
    r'^libc-',
    r'^systemd$',
    r'^systemd-[0-9]',
    r'^dbus$',
    r'^dbus-[0-9]',
    r'^udev',
    r'^kmod',
]

# Pattern per pacchetti che modificano config
CONFIG_PATTERNS = [
    r'^openssh',
    r'^ssh-',
    r'^nginx',
    r'^apache2?',
    r'^httpd',
    r'^postgresql',
    r'^postgres-',
    r'^mysql',
    r'^mariadb',
    r'^postfix',
    r'^dovecot',
    r'^bind9?',
    r'^named',
    r'^samba',
    r'^nfs-',
    r'^docker',
    r'^containerd',
    r'^kubelet',
    r'^haproxy',
    r'^keepalived',
]


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class RiskFactors:
    """Fattori di rischio calcolati per un errata"""
    errata_id: str
    affects_kernel: bool = False
    requires_reboot: bool = False
    modifies_config: bool = False
    dependency_count: int = 0
    package_count: int = 1
    total_size_kb: int = 0
    times_tested: int = 0
    times_failed: int = 0

    @property
    def failure_rate(self) -> float:
        """Calcola failure rate (0.0 - 1.0)"""
        if self.times_tested == 0:
            return 0.0
        return self.times_failed / self.times_tested

    def to_dict(self) -> Dict[str, Any]:
        """Converte in dizionario"""
        return {
            'errata_id': self.errata_id,
            'affects_kernel': self.affects_kernel,
            'requires_reboot': self.requires_reboot,
            'modifies_config': self.modifies_config,
            'dependency_count': self.dependency_count,
            'package_count': self.package_count,
            'total_size_kb': self.total_size_kb,
            'times_tested': self.times_tested,
            'times_failed': self.times_failed,
            'failure_rate': round(self.failure_rate, 4),
        }


@dataclass
class ScoreResult:
    """Risultato calcolo Success Score"""
    errata_id: str
    success_score: int
    breakdown: Dict[str, int]
    factors: Dict[str, Any]
    history: Dict[str, Any]
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Converte in dizionario"""
        return {
            'errata_id': self.errata_id,
            'success_score': self.success_score,
            'breakdown': self.breakdown,
            'factors': self.factors,
            'history': self.history,
            'recommendation': self.recommendation,
        }


# ============================================================
# CALCULATOR
# ============================================================

class SuccessScoreCalculator:
    """Calcola Success Score per errata"""

    def __init__(self, config: Optional[ScoreConfig] = None):
        self.config = config or ScoreConfig()
        self._compiled_patterns = {
            'kernel': [re.compile(p, re.IGNORECASE) for p in KERNEL_PATTERNS],
            'reboot': [re.compile(p, re.IGNORECASE) for p in REBOOT_PATTERNS],
            'config': [re.compile(p, re.IGNORECASE) for p in CONFIG_PATTERNS],
        }

    def _matches_patterns(self, pkg_name: str, pattern_type: str) -> bool:
        """Verifica se nome pacchetto matcha pattern"""
        patterns = self._compiled_patterns.get(pattern_type, [])
        return any(p.match(pkg_name) for p in patterns)

    def analyze_packages(self, packages: List[Dict[str, Any]], errata_id: str = "") -> RiskFactors:
        """Analizza lista pacchetti e determina fattori di rischio"""
        factors = RiskFactors(errata_id=errata_id)
        factors.package_count = len(packages)

        seen_deps = set()

        for pkg in packages:
            pkg_name = pkg.get("name", "").lower()
            pkg_size = pkg.get("size_kb", 0) or 0
            pkg_deps = pkg.get("dependencies", []) or []

            factors.total_size_kb += pkg_size

            # Conta dipendenze uniche
            for dep in pkg_deps:
                dep_name = dep if isinstance(dep, str) else dep.get('name', '')
                if dep_name and dep_name not in seen_deps:
                    seen_deps.add(dep_name)
                    factors.dependency_count += 1

            # Check kernel
            if self._matches_patterns(pkg_name, 'kernel'):
                factors.affects_kernel = True

            # Check reboot
            if self._matches_patterns(pkg_name, 'reboot'):
                factors.requires_reboot = True

            # Check config
            if self._matches_patterns(pkg_name, 'config'):
                factors.modifies_config = True

        return factors

    def calculate_score(self, factors: RiskFactors) -> ScoreResult:
        """Calcola Success Score con breakdown dettagliato"""

        cfg = self.config
        breakdown = {
            "base_score": 100,
            "kernel_penalty": 0,
            "reboot_penalty": 0,
            "config_penalty": 0,
            "dependency_penalty": 0,
            "size_penalty": 0,
            "history_penalty": 0,
            "bonuses": 0,
        }

        # Penalità kernel
        if factors.affects_kernel:
            breakdown["kernel_penalty"] = cfg.KERNEL_PENALTY

        # Penalità reboot
        if factors.requires_reboot:
            breakdown["reboot_penalty"] = cfg.REBOOT_PENALTY

        # Penalità config
        if factors.modifies_config:
            breakdown["config_penalty"] = cfg.CONFIG_PENALTY

        # Penalità dipendenze (scalare con cap)
        dep_penalty = factors.dependency_count * cfg.DEPENDENCY_PENALTY_PER
        breakdown["dependency_penalty"] = min(dep_penalty, cfg.DEPENDENCY_PENALTY_MAX)

        # Penalità dimensione (scalare con cap)
        size_mb = factors.total_size_kb / 1024
        size_penalty = int(size_mb * cfg.SIZE_PENALTY_PER_MB)
        breakdown["size_penalty"] = min(size_penalty, cfg.SIZE_PENALTY_MAX)

        # Penalità storico (solo se abbastanza test)
        if factors.times_tested >= cfg.MIN_TESTS_FOR_HISTORY:
            history_penalty = int(factors.failure_rate * cfg.HISTORY_PENALTY_MAX)
            breakdown["history_penalty"] = history_penalty

        # Bonus per patch piccole
        if factors.total_size_kb < cfg.SMALL_PATCH_THRESHOLD_KB and factors.total_size_kb > 0:
            breakdown["bonuses"] = cfg.SMALL_PATCH_BONUS

        # Calcolo finale
        total_penalty = (
            breakdown["kernel_penalty"] +
            breakdown["reboot_penalty"] +
            breakdown["config_penalty"] +
            breakdown["dependency_penalty"] +
            breakdown["size_penalty"] +
            breakdown["history_penalty"]
        )

        final_score = breakdown["base_score"] - total_penalty + breakdown["bonuses"]
        final_score = max(0, min(100, final_score))  # Clamp 0-100

        # Recommendation
        if final_score >= 80:
            recommendation = "Low risk - safe to test early"
        elif final_score >= 60:
            recommendation = "Medium risk - standard testing"
        elif final_score >= 40:
            recommendation = "High risk - careful monitoring required"
        else:
            recommendation = "Very high risk - consider manual review first"

        return ScoreResult(
            errata_id=factors.errata_id,
            success_score=final_score,
            breakdown=breakdown,
            factors=factors.to_dict(),
            history={
                "times_tested": factors.times_tested,
                "times_failed": factors.times_failed,
                "failure_rate": round(factors.failure_rate, 4),
            },
            recommendation=recommendation,
        )

    def calculate_for_errata(self, errata_id: str, db_connection) -> ScoreResult:
        """Calcola score per un errata specifico dal database"""

        cursor = db_connection.cursor()

        # Query pacchetti associati all'errata
        cursor.execute("""
            SELECT p.name, p.version, p.size_kb
            FROM errata_packages ep
            JOIN packages p ON ep.package_id = p.id
            WHERE ep.errata_id = %s
        """, (errata_id,))

        packages = [
            {
                "name": row[0],
                "version": row[1],
                "size_kb": row[2] or 0,
                "dependencies": []  # TODO: se disponibile nel DB
            }
            for row in cursor.fetchall()
        ]

        # Query storico test
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN result = 'failed' THEN 1 ELSE 0 END) as failed
            FROM patch_tests
            WHERE errata_id = %s AND result IS NOT NULL
        """, (errata_id,))

        history = cursor.fetchone()
        times_tested = history[0] or 0 if history else 0
        times_failed = history[1] or 0 if history else 0

        # Analizza e calcola
        factors = self.analyze_packages(packages, errata_id)
        factors.times_tested = times_tested
        factors.times_failed = times_failed

        return self.calculate_score(factors)

    def bulk_calculate(
        self,
        db_connection,
        errata_ids: Optional[List[str]] = None,
        save_to_db: bool = True
    ) -> List[ScoreResult]:
        """Calcola score per multipli errata"""

        cursor = db_connection.cursor()

        # Ottieni lista errata da calcolare
        if errata_ids:
            cursor.execute("""
                SELECT DISTINCT errata_id FROM errata
                WHERE errata_id = ANY(%s)
            """, (errata_ids,))
        else:
            cursor.execute("SELECT errata_id FROM errata")

        results = []
        errors = []

        for (errata_id,) in cursor.fetchall():
            try:
                score_result = self.calculate_for_errata(errata_id, db_connection)
                results.append(score_result)

                if save_to_db:
                    self._save_to_db(cursor, score_result)

            except Exception as e:
                logger.error(f"Error calculating score for {errata_id}: {e}")
                errors.append({
                    "errata_id": errata_id,
                    "error": str(e)
                })

        if save_to_db:
            db_connection.commit()

        # Ordina per score decrescente
        results.sort(key=lambda x: x.success_score, reverse=True)

        return results

    def _save_to_db(self, cursor, result: ScoreResult):
        """Salva risultato in database"""
        factors = result.factors

        cursor.execute("""
            INSERT INTO patch_risk_profile
                (errata_id, affects_kernel, requires_reboot, modifies_config,
                 dependency_count, package_count, total_size_kb,
                 times_tested, times_failed, success_score, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (errata_id) DO UPDATE SET
                affects_kernel = EXCLUDED.affects_kernel,
                requires_reboot = EXCLUDED.requires_reboot,
                modifies_config = EXCLUDED.modifies_config,
                dependency_count = EXCLUDED.dependency_count,
                package_count = EXCLUDED.package_count,
                total_size_kb = EXCLUDED.total_size_kb,
                times_tested = EXCLUDED.times_tested,
                times_failed = EXCLUDED.times_failed,
                success_score = EXCLUDED.success_score,
                updated_at = NOW()
        """, (
            result.errata_id,
            factors.get('affects_kernel', False),
            factors.get('requires_reboot', False),
            factors.get('modifies_config', False),
            factors.get('dependency_count', 0),
            factors.get('package_count', 1),
            factors.get('total_size_kb', 0),
            result.history.get('times_tested', 0),
            result.history.get('times_failed', 0),
            result.success_score,
        ))


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_score_for_sorting(score_result: ScoreResult) -> int:
    """Restituisce valore per ordinamento (usato in sorted())"""
    return score_result.success_score


def format_score_summary(result: ScoreResult) -> str:
    """Formatta risultato per logging/display"""
    return (
        f"{result.errata_id}: Score={result.success_score} "
        f"[kernel={result.factors.get('affects_kernel')}, "
        f"reboot={result.factors.get('requires_reboot')}, "
        f"tested={result.history.get('times_tested')}] "
        f"- {result.recommendation}"
    )


# ============================================================
# EXAMPLE USAGE
# ============================================================

if __name__ == "__main__":
    # Test con dati mock
    logging.basicConfig(level=logging.INFO)

    calculator = SuccessScoreCalculator()

    # Test 1: Patch OpenSSL (basso rischio)
    openssl_packages = [
        {"name": "openssl", "version": "3.0.2-0ubuntu1.14", "size_kb": 850},
        {"name": "libssl3", "version": "3.0.2-0ubuntu1.14", "size_kb": 400},
    ]

    factors = calculator.analyze_packages(openssl_packages, "USN-7234-1")
    factors.times_tested = 5
    factors.times_failed = 0

    result = calculator.calculate_score(factors)
    print(f"\n1. OpenSSL patch:")
    print(f"   {format_score_summary(result)}")
    print(f"   Breakdown: {json.dumps(result.breakdown, indent=2)}")

    # Test 2: Patch Kernel (alto rischio)
    kernel_packages = [
        {"name": "linux-image-5.15.0-100-generic", "version": "5.15.0-100", "size_kb": 45000},
        {"name": "linux-headers-5.15.0-100-generic", "version": "5.15.0-100", "size_kb": 12000},
        {"name": "linux-modules-5.15.0-100-generic", "version": "5.15.0-100", "size_kb": 28000},
    ]

    factors = calculator.analyze_packages(kernel_packages, "USN-7240-1")
    factors.times_tested = 3
    factors.times_failed = 1

    result = calculator.calculate_score(factors)
    print(f"\n2. Kernel patch:")
    print(f"   {format_score_summary(result)}")
    print(f"   Breakdown: {json.dumps(result.breakdown, indent=2)}")

    # Test 3: Patch PostgreSQL (medio rischio)
    pg_packages = [
        {"name": "postgresql-14", "version": "14.10-0ubuntu0.22.04.1", "size_kb": 5200},
        {"name": "postgresql-client-14", "version": "14.10-0ubuntu0.22.04.1", "size_kb": 1800},
    ]

    factors = calculator.analyze_packages(pg_packages, "USN-7245-1")
    factors.times_tested = 0
    factors.times_failed = 0

    result = calculator.calculate_score(factors)
    print(f"\n3. PostgreSQL patch:")
    print(f"   {format_score_summary(result)}")
    print(f"   Breakdown: {json.dumps(result.breakdown, indent=2)}")

    # Test 4: Patch piccola curl (basso rischio + bonus)
    curl_packages = [
        {"name": "curl", "version": "7.81.0-1ubuntu1.15", "size_kb": 80},
    ]

    factors = calculator.analyze_packages(curl_packages, "USN-7250-1")
    result = calculator.calculate_score(factors)
    print(f"\n4. Curl patch (small):")
    print(f"   {format_score_summary(result)}")
    print(f"   Breakdown: {json.dumps(result.breakdown, indent=2)}")

    print("\n--- Ordinamento per priorità test ---")
    all_results = [
        calculator.calculate_score(calculator.analyze_packages(openssl_packages, "USN-7234-1")),
        calculator.calculate_score(calculator.analyze_packages(kernel_packages, "USN-7240-1")),
        calculator.calculate_score(calculator.analyze_packages(pg_packages, "USN-7245-1")),
        calculator.calculate_score(calculator.analyze_packages(curl_packages, "USN-7250-1")),
    ]

    sorted_results = sorted(all_results, key=get_score_for_sorting, reverse=True)

    print("\nOrdine test (prima i più sicuri):")
    for i, r in enumerate(sorted_results, 1):
        print(f"   {i}. {r.errata_id} (Score: {r.success_score})")
