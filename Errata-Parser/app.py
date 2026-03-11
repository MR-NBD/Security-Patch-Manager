#!/usr/bin/env python3
"""
UYUNI Errata Manager - v3.5

Sincronizza errata Ubuntu USN e/o Debian DSA verso UYUNI Server.
Le distribuzioni vengono rilevate automaticamente dai canali UYUNI attivi.
NVD arricchisce la severity CVSS reale dopo ogni sync.
Gli errata RHEL nativi UYUNI (importati da Red Hat CDN) vengono arricchiti
con CVE IDs e severity NVD tramite la pipeline /api/sync/rhel-nvd.

Endpoints:
  POST /api/sync/auto           — pipeline completa auto-detect
  POST /api/sync/usn            — solo Ubuntu USN
  POST /api/sync/dsa            — solo Debian DSA
  POST /api/sync/nvd            — solo NVD enrichment
  POST /api/sync/rhel-nvd       — pipeline RHEL: import CVEs da UYUNI + NVD enrichment + aggiorna severity
  POST /api/uyuni/sync-packages — aggiorna cache pacchetti
  POST /api/uyuni/push          — push errata pendenti a UYUNI
  GET  /api/uyuni/channels      — canali con distribuzione mappata
  GET  /api/sync/status         — log ultimi 20 sync
  GET  /api/health              — stato API, DB, UYUNI (no auth)
  GET  /api/health/detailed     — stato dettagliato con metriche e alert (no auth)

Auth: header X-API-Key richiesto su tutti gli endpoint tranne /api/health*.
      Se SPM_API_KEY non è impostata tutti gli endpoint autenticati ritornano 503.

Changelog v3.5:
  - NVD enrichment per errata RHEL nativi UYUNI (importati da Red Hat CDN)
  - Nuovo endpoint POST /api/sync/rhel-nvd: pipeline RHEL CVE import + NVD + setDetails
  - map_channel_to_rhel(): rileva canali RHEL da label UYUNI, skippa CLM/lifecycle/client-tools
  - _parse_rhel_severity(): estrae severity da prefisso advisory_synopsis (Critical/Important/Moderate/Low)
  - _sync_rhel_cves(): importa RHSA da UYUNI, estrae CVE IDs, inserisce nel DB per NVD enrichment
  - _update_rhel_severity(): aggiorna severity RHEL in UYUNI via errata.setDetails post-NVD
  - _propagate_nvd_severity(): resetta sync_status='pending' per errata RHEL quando NVD migliora severity
  - _get_active_distributions(): estesa per rilevare canali RHEL (rhel-9, rhel-8, ecc.)
  - route_sync_auto(): integra pipeline RHEL (sync CVEs + aggiorna severity) nella pipeline completa
  - Scheduler: job rhel_pipeline alle 05:00 (dopo NVD delle 04:00)
  - Migration 002: constraint chk_errata_source e chk_log_type estesi per 'rhel', 'rhel_push'

Changelog v3.4:
  - Fix _sanitize_error(): logger.debug → logger.error — errori non più persi in produzione
  - Fix _sync_packages(): aggiunta registrazione in sync_logs (coerente con usn/dsa/nvd)
  - Fix route_sync_dsa(): rileva distribuzioni UYUNI attive prima di chiamare _sync_dsa,
    evita processing di release Debian non presenti in UYUNI (coerente con /api/sync/auto)
  - Bump dipendenze: requests 2.32.3, psycopg2-binary 2.9.10, packaging 24.2

Changelog v3.3:
  - _check_api_key(): 503 se SPM_API_KEY non impostata (no silent bypass); audit log
  - version_ge(): fallback conservativo → False (non include pkg non confrontabili)
  - _sanitize_error(): sempre "Internal error" — no leak di dettagli interni
  - _get_active_distributions(): cache in-memory (TTL 1h) per resilienza UYUNI
  - _sync_packages(): skip DELETE se listAllPackages ritorna lista vuota (no cache wipe)
  - CVE ID validation: regex CVE-YYYY-NNNNN in USN e DSA sync
  - Scheduler: _job_status traccia last_run/status/error per ogni job
  - scheduler_jobs(): espone _job_status nell'endpoint (visibilità fallimenti)

Changelog v3.2:
  - version_ge(): supporto epoch Debian/Ubuntu (fix push sempre skippato)
  - _push_errata(): fixed_ver_map multi-release + errata.publish() dopo create
  - _uyuni(): transport con timeout per-connessione (thread-safe, no socket global)
  - _sync_usn(): whitelist release Ubuntu estesa (bionic, oracular, plucky)
"""

import contextlib
import os
import re
import ssl
import sys
import time
import xmlrpc.client
from datetime import datetime
from itertools import zip_longest

from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import requests
from packaging import version as pkg_version

import logging

# ============================================================
# LOGGING
# ============================================================
_LOG_FILE = os.environ.get('LOG_FILE', '/var/log/errata-manager.log')

_handlers = [logging.StreamHandler(sys.stdout)]
try:
    _handlers.append(logging.FileHandler(_LOG_FILE))
except OSError as _e:
    print(f'WARNING: cannot open log file {_LOG_FILE}: {_e}', file=sys.stderr)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=_handlers,
)
logger = logging.getLogger('errata-manager')

# ============================================================
# CONFIG — validazione fail-fast al startup
# ============================================================
DATABASE_URL     = os.environ.get('DATABASE_URL')
UYUNI_URL        = os.environ.get('UYUNI_URL', '')
UYUNI_USER       = os.environ.get('UYUNI_USER', '')
UYUNI_PASSWORD   = os.environ.get('UYUNI_PASSWORD', '')
UYUNI_VERIFY_SSL = os.environ.get('UYUNI_VERIFY_SSL', 'false').lower() == 'true'
NVD_API_KEY      = os.environ.get('NVD_API_KEY', '')
NVD_API_BASE     = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
SPM_API_KEY      = os.environ.get('SPM_API_KEY', '')
_UYUNI_TIMEOUT   = int(os.environ.get('UYUNI_TIMEOUT', '30'))

if not DATABASE_URL:
    logger.critical('DATABASE_URL env var is required — exiting')
    sys.exit(1)
if not UYUNI_URL:
    logger.warning('UYUNI_URL not set — push/packages endpoints will fail')
if not SPM_API_KEY:
    logger.warning('SPM_API_KEY not set — API authentication disabled')

# ============================================================
# FLASK APP
# ============================================================
app = Flask(__name__)

_CORS_ORIGIN = os.environ.get('CORS_ORIGIN', '')
if _CORS_ORIGIN:
    CORS(app, resources={r'/api/*': {'origins': _CORS_ORIGIN}})

# ============================================================
# CONSTANTS
# ============================================================
_APP_VERSION    = '3.5'
_REQUEST_HEADERS = {'User-Agent': f'UYUNI-Errata-Manager/{_APP_VERSION}'}

# severity interna → (label UYUNI, keywords per errata.create)
SEVERITY_TO_UYUNI = {
    'critical': ('Critical',  ['critical', 'security']),
    'high':     ('Important', ['important', 'security']),
    'medium':   ('Moderate',  ['moderate',  'security']),
    'low':      ('Low',       ['low',       'security']),
}

# Mappature severity sorgente
_USN_PRIORITY_MAP = {
    'critical': 'critical', 'high': 'high',
    'medium': 'medium', 'low': 'low', 'negligible': 'low',
}
_DSA_URGENCY_MAP = {
    'critical': 'critical', 'emergency': 'critical',
    'high': 'high', 'medium': 'medium',
    'low': 'low', 'unimportant': 'low', 'not yet assigned': 'medium',
}

# Release Ubuntu supportate (USN) — nomi presenti in release_packages
_UBUNTU_RELEASES = frozenset({
    'noble',    # 24.04 LTS
    'jammy',    # 22.04 LTS
    'focal',    # 20.04 LTS
    'bionic',   # 18.04 LTS (ESM)
    'oracular', # 24.10
    'plucky',   # 25.04
    'mantic',   # 23.10
    'lunar',    # 23.04
})

# Release Debian supportate
_DEBIAN_RELEASE_MAP = {
    'debian-bookworm': 'bookworm',
    'debian-bullseye': 'bullseye',
    'debian-trixie':   'trixie',
}

# Advisory lock keys PostgreSQL
_LOCK_KEYS = {'usn': 1001, 'dsa': 1002, 'nvd': 1003, 'packages': 1004, 'push': 1005, 'rhel': 1006, 'rhel_push': 1007}

# Regex per validazione CVE ID (es. CVE-2024-12345)
_RE_CVE = re.compile(r'^CVE-\d{4}-\d{4,}$')

# Cache distribuzioni UYUNI attive (TTL 1h) — resilienza se UYUNI non raggiungibile
_dist_cache: dict = {'dists': set(), 'ts': 0.0}
_DIST_CACHE_TTL  = 3600  # secondi

# Limiti input API
_MAX_BATCH_SIZE = 500
_MAX_PUSH_LIMIT = 200

# Endpoint che non richiedono autenticazione
_AUTH_EXEMPT = {'health', 'health_detailed'}

# Regex per estrarre versione RHEL dal label canale (es. 'rhel9-baseos-cdn' → 9)
_RE_RHEL_VERSION = re.compile(r'rhel(\d+)', re.IGNORECASE)

# Canali RHEL da skippare (CLM copies, client tools — errata duplicati o non rilevanti)
_RHEL_CHANNEL_SKIP = frozenset({'clm', 'lifecycle', 'uyuni-client'})

# Mapping prefisso synopsis RHEL → severity interna
_RHEL_SYNOPSIS_SEVERITY = {
    'critical':  'critical',
    'important': 'high',
    'moderate':  'medium',
    'low':       'low',
}


# ============================================================
# AUTENTICAZIONE
# ============================================================
@app.before_request
def _check_api_key():
    if request.endpoint in _AUTH_EXEMPT:
        return
    if not SPM_API_KEY:
        # Non bypassare silenziosamente: se la chiave non è impostata il servizio
        # è mal configurato — rifiuta tutte le richieste autenticate.
        logger.error('SPM_API_KEY not set — rejecting request (503)')
        return jsonify({'error': 'Service misconfigured — SPM_API_KEY not set'}), 503
    key = request.headers.get('X-API-Key', '')
    if key != SPM_API_KEY:
        logger.warning(
            f'API auth failed: method={request.method} path={request.path} '
            f'ip={request.remote_addr}'
        )
        return jsonify({'error': 'Unauthorized'}), 401
    logger.info(
        f'API call: {request.method} {request.path} ip={request.remote_addr}'
    )


# ============================================================
# CONTEXT MANAGERS
# ============================================================
@contextlib.contextmanager
def _db():
    """Connessione DB con chiusura garantita."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


class _TimeoutTransport(xmlrpc.client.SafeTransport):
    """Transport XML-RPC con timeout per-connessione (thread-safe)."""

    def __init__(self, timeout, context=None):
        super().__init__(context=context)
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        # http.client.HTTPSConnection espone .timeout
        if hasattr(conn, 'timeout'):
            conn.timeout = self._timeout
        return conn


@contextlib.contextmanager
def _uyuni():
    """
    Sessione UYUNI XML-RPC con logout garantito.
    Usa transport con timeout per-connessione invece del socket globale
    (thread-safe con gunicorn multi-thread).
    """
    if not UYUNI_URL:
        raise RuntimeError('UYUNI_URL not configured')

    ctx = ssl.create_default_context()
    ctx.check_hostname = UYUNI_VERIFY_SSL
    ctx.verify_mode    = ssl.CERT_REQUIRED if UYUNI_VERIFY_SSL else ssl.CERT_NONE

    transport = _TimeoutTransport(timeout=_UYUNI_TIMEOUT, context=ctx)
    client    = xmlrpc.client.ServerProxy(f'{UYUNI_URL}/rpc/api', transport=transport)

    session = client.auth.login(UYUNI_USER, UYUNI_PASSWORD)
    try:
        yield client, session
    finally:
        try:
            client.auth.logout(session)
        except Exception:
            pass


# ============================================================
# ADVISORY LOCK HELPERS
# ============================================================
def _try_lock(conn, name):
    key = _LOCK_KEYS.get(name)
    if key is None:
        return True
    with conn.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_lock(%s)', (key,))
        return cur.fetchone()['pg_try_advisory_lock']


def _unlock(conn, name):
    key = _LOCK_KEYS.get(name)
    if key is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_unlock(%s)', (key,))
    except Exception:
        pass


# ============================================================
# HELPERS
# ============================================================
def map_channel_to_distribution(label):
    """Mappa label canale UYUNI → distribuzione (ubuntu, debian-bookworm, ecc.)."""
    label_lower = label.lower()
    if 'ubuntu' in label_lower:
        return 'ubuntu'
    if 'debian' in label_lower:
        if 'bookworm' in label_lower or 'debian-12' in label_lower:
            return 'debian-bookworm'
        if 'bullseye' in label_lower or 'debian-11' in label_lower:
            return 'debian-bullseye'
        if 'trixie' in label_lower or 'debian-13' in label_lower:
            return 'debian-trixie'
    return None


def map_channel_to_rhel(label):
    """
    Mappa label canale UYUNI → versione RHEL (es. 'rhel-9'), None se non RHEL.
    Skippa canali CLM/lifecycle/client-tools (duplicati o non contenenti errata security).
    """
    label_lower = label.lower()
    if 'rhel' not in label_lower:
        return None
    if any(skip in label_lower for skip in _RHEL_CHANNEL_SKIP):
        return None
    m = _RE_RHEL_VERSION.search(label_lower)
    return f'rhel-{m.group(1)}' if m else None


def _parse_rhel_severity(synopsis):
    """
    Estrae severity interna dal prefisso advisory_synopsis RHEL.
    Es. 'Moderate: samba security update' → 'medium'
        'Important: kernel security update' → 'high'
    Fallback: 'medium' se non riconoscibile.
    """
    if not synopsis:
        return 'medium'
    prefix = synopsis.split(':')[0].strip().lower()
    return _RHEL_SYNOPSIS_SEVERITY.get(prefix, 'medium')


_RE_EPOCH = re.compile(r'^(\d+):(.+)$')


def _split_epoch(v):
    """
    Separa epoch da versione Debian/Ubuntu.
    '1:2.3-4+deb12u1' → (1, '2.3-4+deb12u1')
    '2.3-4'           → (0, '2.3-4')
    """
    m = _RE_EPOCH.match(v)
    if m:
        return int(m.group(1)), m.group(2)
    return 0, v


def _dpkg_char_order(c):
    """
    Ordine carattere per confronto non-numerico algoritmo dpkg.
    ~ < fine-stringa < cifra < lettera < altro
    """
    if c == '~':    return -1
    if not c:       return 0
    if c.isdigit(): return 1
    if c.isalpha(): return 2
    return 3


def _compare_dpkg_str(a, b):
    """Confronta due segmenti non-numerici secondo l'ordine Debian."""
    for ca, cb in zip_longest(a, b, fillvalue=''):
        oa, ob = _dpkg_char_order(ca), _dpkg_char_order(cb)
        if oa != ob:
            return oa - ob
        if ca != cb:
            return -1 if ca < cb else 1
    return 0


def _compare_version_string(v1, v2):
    """
    Confronta due version string secondo l'algoritmo dpkg.
    Alterna tra segmenti non-numerici e numerici.
    Ritorna negativo se v1 < v2, 0 se v1 == v2, positivo se v1 > v2.
    """
    i1, i2 = 0, 0
    while i1 < len(v1) or i2 < len(v2):
        # Segmento non-numerico
        s1, s2 = i1, i2
        while i1 < len(v1) and not v1[i1].isdigit():
            i1 += 1
        while i2 < len(v2) and not v2[i2].isdigit():
            i2 += 1
        r = _compare_dpkg_str(v1[s1:i1], v2[s2:i2])
        if r != 0:
            return r
        # Segmento numerico
        s1, s2 = i1, i2
        while i1 < len(v1) and v1[i1].isdigit():
            i1 += 1
        while i2 < len(v2) and v2[i2].isdigit():
            i2 += 1
        n1 = int(v1[s1:i1]) if s1 < i1 else 0
        n2 = int(v2[s2:i2]) if s2 < i2 else 0
        if n1 != n2:
            return n1 - n2
    return 0


def version_ge(v1, v2):
    """
    Ritorna True se v1 >= v2.

    Strategia a tre livelli:
    1. PEP 440 puro (versioni numeriche semplici, es. '1.2.3')
    2. Algoritmo dpkg completo: epoch + upstream version + debian revision.
       Gestisce versioni Ubuntu/Debian come '8.9p1-3ubuntu0.10', '7.81.0-1ubuntu1.15'.
    3. Fallback conservativo → False: non include il pacchetto se non confrontabile.
    """
    if not v1 or not v2:
        return True

    # Tentativo 1: PEP 440 diretto
    try:
        return pkg_version.parse(v1) >= pkg_version.parse(v2)
    except Exception:
        pass

    # Tentativo 2: algoritmo dpkg con epoch + upstream/revision separati
    try:
        epoch1, rest1 = _split_epoch(v1)
        epoch2, rest2 = _split_epoch(v2)
        if epoch1 != epoch2:
            return epoch1 > epoch2
        # Separa upstream version da debian revision sull'ULTIMO trattino
        up1, rev1 = rest1.rsplit('-', 1) if '-' in rest1 else (rest1, '0')
        up2, rev2 = rest2.rsplit('-', 1) if '-' in rest2 else (rest2, '0')
        r = _compare_version_string(up1, up2)
        if r != 0:
            return r > 0
        return _compare_version_string(rev1, rev2) >= 0
    except Exception:
        pass

    # Fallback conservativo: escludiamo il pacchetto se non sappiamo confrontare.
    # Preferibile perdere un match a versione non-standard piuttosto che includere
    # pacchetti potenzialmente incompatibili.
    logger.warning(f'version_ge: cannot compare {v1!r} >= {v2!r} → False (conservative skip)')
    return False


def cvss_to_severity(score):
    if score is None:
        return None
    if score >= 9.0: return 'CRITICAL'
    if score >= 7.0: return 'HIGH'
    if score >= 4.0: return 'MEDIUM'
    return 'LOW'


def _clamp(value, default, min_val, max_val):
    if value is None:
        return default
    return max(min_val, min(max_val, value))


def _sanitize_error(exc):
    """
    Ritorna sempre una stringa generica per API response.
    I dettagli dell'errore vengono loggati al livello ERROR (visibili in produzione).
    """
    logger.error(f'Internal error detail: {exc}')
    return 'Internal error — see application logs'


def _get_active_distributions():
    """
    Ritorna le distribuzioni mappate dai canali UYUNI attivi.
    In caso di errore usa la cache in-memory (TTL 1h) per resilienza.
    """
    global _dist_cache
    try:
        with _uyuni() as (client, session):
            channels = client.channel.listAllChannels(session)
            dists = set()
            for _ch in channels:
                _d = map_channel_to_distribution(_ch['label'])
                if _d:
                    dists.add(_d)
                _r = map_channel_to_rhel(_ch['label'])
                if _r:
                    dists.add(_r)
            _dist_cache = {'dists': dists, 'ts': time.time()}
            return dists
    except Exception as e:
        logger.error(f'Cannot read UYUNI channels: {e}')
        cached = _dist_cache['dists']
        if cached:
            age_min = round((time.time() - _dist_cache['ts']) / 60, 1)
            logger.warning(
                f'Using cached distributions (age={age_min}min): {cached}'
            )
            return cached
        return set()


# ============================================================
# SYNC LOG HELPERS
# ============================================================
def _log_start(conn, sync_type):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sync_logs (sync_type, status, started_at) VALUES (%s, 'running', NOW()) RETURNING id",
            (sync_type,),
        )
        log_id = cur.fetchone()['id']
    conn.commit()
    return log_id


def _log_done(conn, log_id, count, errors=None):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sync_logs SET status='completed', completed_at=NOW(), "
                "items_processed=%s, error_message=%s WHERE id=%s",
                (count, ('; '.join(errors[:5]) if errors else None), log_id),
            )
        conn.commit()
    except Exception:
        pass


def _log_error(conn, log_id, exc):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sync_logs SET status='error', completed_at=NOW(), error_message=%s WHERE id=%s",
                (str(exc)[:500], log_id),
            )
        conn.commit()
    except Exception:
        pass


# ============================================================
# NVD SEVERITY PROPAGATION
# ============================================================
def _propagate_nvd_severity(conn):
    """
    Aggiorna errata.severity dove il rank NVD (CVSS) supera il valore attuale.
    Ritorna il numero di righe aggiornate.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH nvd_best AS (
                SELECT
                    ec.errata_id,
                    (ARRAY_AGG(
                        LOWER(cd.severity)
                        ORDER BY
                            CASE LOWER(cd.severity)
                                WHEN 'critical' THEN 4
                                WHEN 'high'     THEN 3
                                WHEN 'medium'   THEN 2
                                WHEN 'low'      THEN 1
                                ELSE 0
                            END DESC
                    ))[1] AS best_severity,
                    MAX(
                        CASE LOWER(cd.severity)
                            WHEN 'critical' THEN 4
                            WHEN 'high'     THEN 3
                            WHEN 'medium'   THEN 2
                            WHEN 'low'      THEN 1
                            ELSE 0
                        END
                    ) AS best_rank
                FROM errata_cves ec
                JOIN cves c         ON ec.cve_id  = c.id
                JOIN cve_details cd ON c.cve_id   = cd.cve_id
                WHERE cd.severity IS NOT NULL
                GROUP BY ec.errata_id
            )
            UPDATE errata e
            SET
                severity    = nb.best_severity,
                sync_status = CASE
                                  WHEN e.source = 'rhel' THEN 'pending'
                                  ELSE e.sync_status
                              END
            FROM   nvd_best nb
            WHERE  e.id = nb.errata_id
              AND  nb.best_rank > COALESCE(
                       CASE LOWER(e.severity)
                           WHEN 'critical' THEN 4
                           WHEN 'high'     THEN 3
                           WHEN 'medium'   THEN 2
                           WHEN 'low'      THEN 1
                           ELSE 0
                       END, 0
                   )
        """)
        return cur.rowcount


# ============================================================
# SYNC: USN
# ============================================================
def _sync_usn(conn):
    """
    Sync incrementale Ubuntu Security Notices.
    Processa e inserisce ogni pagina immediatamente (no accumulo RAM).
    """
    if not _try_lock(conn, 'usn'):
        logger.warning('USN sync already running — skipped')
        return {'source': 'usn', 'skipped': 'already_running'}

    log_id = _log_start(conn, 'usn')
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT advisory_id, issued_date FROM errata WHERE source='usn' "
                "ORDER BY issued_date DESC LIMIT 1"
            )
            last = cur.fetchone()

        last_usn  = last['advisory_id'] if last else None
        last_date = last['issued_date']  if last else datetime(2020, 1, 1)
        if getattr(last_date, 'tzinfo', None):
            last_date = last_date.replace(tzinfo=None)

        logger.info(f'USN sync: last known={last_usn}')

        total_processed = total_packages = 0
        offset = 0
        done   = False

        while not done and offset < 1000:
            try:
                resp = requests.get(
                    f'https://ubuntu.com/security/notices.json?limit=20&offset={offset}',
                    headers=_REQUEST_HEADERS, timeout=30,
                )
                resp.raise_for_status()
                notices = resp.json().get('notices', [])
            except Exception as e:
                logger.error(f'USN fetch error at offset {offset}: {e}')
                break

            if not notices:
                break

            page_processed = page_packages = 0

            for n in notices:
                nid = n.get('id', '')

                if nid == last_usn:
                    done = True
                    break

                nd_str = n.get('published')
                if nd_str:
                    try:
                        nd = datetime.fromisoformat(nd_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        if nd < last_date:
                            done = True
                            break
                    except Exception:
                        pass

                severity = _USN_PRIORITY_MAP.get((n.get('priority') or 'medium').lower(), 'medium')

                cves = n.get('cves', [])
                cve_ids = [
                    raw_id
                    for c in (cves if isinstance(cves, list) else [])
                    if c
                    for raw_id in [c if isinstance(c, str) else c.get('id', '')]
                    if _RE_CVE.match(raw_id)
                ]

                packages = [
                    {'name': p['name'], 'version': p.get('version', ''), 'release': rel.lower()}
                    for rel, pkgs in n.get('release_packages', {}).items()
                    if rel.lower() in _UBUNTU_RELEASES
                    for p in (pkgs if isinstance(pkgs, list) else [])
                    if isinstance(p, dict) and p.get('name')
                ]

                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO errata
                                (advisory_id, title, description, severity, source, distribution, issued_date)
                            VALUES (%s, %s, %s, %s, 'usn', 'ubuntu', %s)
                            ON CONFLICT (advisory_id) DO NOTHING
                            RETURNING id
                        """, (
                            nid,
                            (n.get('title') or '')[:500],
                            (n.get('description') or '')[:4000],
                            severity,
                            nd_str,
                        ))
                        row = cur.fetchone()
                        if not row:
                            continue

                        errata_id = row['id']
                        page_processed += 1

                        for cve_id in cve_ids:
                            # cve_ids già filtrati da _RE_CVE nella list comprehension sopra
                            cur.execute(
                                "INSERT INTO cves (cve_id) VALUES (%s) "
                                "ON CONFLICT (cve_id) DO UPDATE SET cve_id=EXCLUDED.cve_id RETURNING id",
                                (cve_id,),
                            )
                            cve_row = cur.fetchone()
                            cur.execute(
                                "INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) "
                                "ON CONFLICT DO NOTHING",
                                (errata_id, cve_row['id']),
                            )

                        if packages:
                            execute_values(cur, """
                                INSERT INTO errata_packages
                                    (errata_id, package_name, fixed_version, release_name)
                                VALUES %s
                                ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                            """, [(errata_id, p['name'], p['version'], p['release']) for p in packages])
                            page_packages += len(packages)

                except Exception as ex:
                    conn.rollback()
                    logger.error(f'USN insert error {nid}: {ex}')
                    continue

            conn.commit()
            total_processed += page_processed
            total_packages  += page_packages
            offset += 20
            time.sleep(0.5)

    except Exception as ex:
        _log_error(conn, log_id, ex)
        _unlock(conn, 'usn')
        raise

    _log_done(conn, log_id, total_processed)
    _unlock(conn, 'usn')
    logger.info(f'USN done: {total_processed} new errata, {total_packages} packages')
    return {'source': 'usn', 'processed': total_processed, 'packages_saved': total_packages, 'last_known': last_usn}


# ============================================================
# SYNC: DSA
# ============================================================
def _sync_dsa(conn, active_dists=None):
    """
    Sync completo Debian DSA da security-tracker.debian.org.
    Sincronizza solo i release Debian presenti nei canali UYUNI attivi.
    """
    target_releases = (
        [_DEBIAN_RELEASE_MAP[d] for d in (active_dists or []) if d in _DEBIAN_RELEASE_MAP]
        or list(_DEBIAN_RELEASE_MAP.values())
    )

    if not _try_lock(conn, 'dsa'):
        logger.warning('DSA sync already running — skipped')
        return {'source': 'dsa', 'skipped': 'already_running'}

    log_id = _log_start(conn, 'dsa')
    logger.info(f'DSA sync: releases={target_releases}')
    logger.info('DSA sync: downloading Debian security tracker (~63 MB)...')

    try:
        resp = requests.get(
            'https://security-tracker.debian.org/tracker/data/json',
            headers=_REQUEST_HEADERS, timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        _log_error(conn, log_id, e)
        _unlock(conn, 'dsa')
        raise

    total_errata = total_packages = 0
    batch_count  = 0

    try:
        with conn.cursor() as cur:
            for pkg_name, pkg_data in data.items():
                if not isinstance(pkg_data, dict):
                    continue

                for cve_id, cve_data in pkg_data.items():
                    if not _RE_CVE.match(cve_id) or not isinstance(cve_data, dict):
                        continue

                    urgency     = (cve_data.get('urgency') or 'medium').lower()
                    severity    = _DSA_URGENCY_MAP.get(urgency, 'medium')
                    description = (cve_data.get('description') or '')[:4000]

                    for rel in target_releases:
                        rel_data = cve_data.get('releases', {}).get(rel)
                        if not isinstance(rel_data, dict):
                            continue
                        if rel_data.get('status') != 'resolved' or not rel_data.get('fixed_version'):
                            continue

                        advisory_id = f'DEB-{cve_id}-{rel}'

                        cur.execute('SAVEPOINT dsa_sp')
                        try:
                            cur.execute("""
                                INSERT INTO errata
                                    (advisory_id, title, description, severity, source, distribution, issued_date)
                                VALUES (%s, %s, %s, %s, 'dsa', %s, NOW())
                                ON CONFLICT (advisory_id) DO NOTHING
                                RETURNING id
                            """, (
                                advisory_id,
                                f'{pkg_name}: {cve_id}'[:500],
                                description,
                                severity,
                                f'debian-{rel}',
                            ))
                            row = cur.fetchone()
                            if not row:
                                cur.execute('RELEASE SAVEPOINT dsa_sp')
                                continue

                            errata_id = row['id']

                            cur.execute(
                                "INSERT INTO cves (cve_id) VALUES (%s) "
                                "ON CONFLICT (cve_id) DO UPDATE SET cve_id=EXCLUDED.cve_id RETURNING id",
                                (cve_id,),
                            )
                            cve_row = cur.fetchone()
                            cur.execute(
                                "INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) "
                                "ON CONFLICT DO NOTHING",
                                (errata_id, cve_row['id']),
                            )
                            cur.execute("""
                                INSERT INTO errata_packages
                                    (errata_id, package_name, fixed_version, release_name)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                            """, (errata_id, pkg_name, rel_data['fixed_version'], rel))

                            cur.execute('RELEASE SAVEPOINT dsa_sp')
                            total_errata   += 1
                            total_packages += 1

                        except Exception as ex:
                            cur.execute('ROLLBACK TO SAVEPOINT dsa_sp')
                            logger.debug(f'DSA skip {advisory_id}: {ex}')
                            continue

                batch_count += 1
                if batch_count % 500 == 0:
                    conn.commit()
                    logger.info(f'DSA progress: {total_errata} errata (batch {batch_count})')

            conn.commit()

    except Exception as ex:
        _log_error(conn, log_id, ex)
        _unlock(conn, 'dsa')
        raise

    _log_done(conn, log_id, total_errata)
    _unlock(conn, 'dsa')
    logger.info(f'DSA done: {total_errata} errata, {total_packages} packages')
    return {
        'source':         'dsa',
        'total_errata':   total_errata,
        'total_packages': total_packages,
        'releases':       target_releases,
    }


# ============================================================
# SYNC: RHEL CVEs da UYUNI
# ============================================================
def _sync_rhel_cves(conn):
    """
    Importa Security Advisory RHEL (RHSA-*) dai canali UYUNI e inserisce
    i CVE associati nel DB locale per NVD enrichment.
    NON crea nuovi errata in UYUNI: gli RHSA esistono già (importati da Red Hat CDN).
    La severity iniziale viene estratta dal prefisso advisory_synopsis (es. 'Moderate: ...').
    L'enrichment NVD (_sync_nvd + _propagate_nvd_severity) può in seguito migliorarla.
    """
    if not _try_lock(conn, 'rhel'):
        logger.warning('RHEL CVE sync already running — skipped')
        return {'skipped': 'already_running'}

    log_id       = _log_start(conn, 'rhel')
    total_errata = total_cves = 0
    errors       = []

    try:
        with _uyuni() as (client, session):
            all_channels  = client.channel.listAllChannels(session)
            rhel_channels = [
                (ch['label'], map_channel_to_rhel(ch['label']))
                for ch in all_channels
                if map_channel_to_rhel(ch['label'])
            ]

            if not rhel_channels:
                _log_done(conn, log_id, 0)
                _unlock(conn, 'rhel')
                logger.info('RHEL CVE sync: no RHEL channels found in UYUNI')
                return {'source': 'rhel', 'total_errata': 0, 'total_cves': 0,
                        'message': 'No RHEL channels found'}

            logger.info(f'RHEL CVE sync: {len(rhel_channels)} canali — '
                        f'{[lbl for lbl, _ in rhel_channels]}')

            seen = set()  # dedup advisory_name across channels (stesso RHSA in più canali)

            for label, rhel_version in rhel_channels:
                try:
                    all_errata = client.channel.software.listErrata(session, label)
                except Exception as ex:
                    logger.error(f'RHEL listErrata error for {label}: {ex}')
                    errors.append(f'{label}: {str(ex)[:80]}')
                    continue

                security = [
                    e for e in all_errata
                    if e['advisory_type'] == 'Security Advisory'
                    and e.get('advisory_status', 'final') in ('final', 'stable')
                ]
                logger.info(f'RHEL CVE sync: {label} → {len(security)} RHSA')

                for e in security:
                    adv_name = e['advisory_name']
                    if adv_name in seen:
                        continue
                    seen.add(adv_name)

                    severity   = _parse_rhel_severity(e.get('advisory_synopsis', ''))
                    vendor_url = f'https://access.redhat.com/errata/{adv_name}'

                    try:
                        cves = [
                            cve for cve in client.errata.listCves(session, adv_name)
                            if _RE_CVE.match(cve)
                        ]
                    except Exception as ex:
                        cves = []
                        logger.warning(f'RHEL listCves error {adv_name}: {ex}')

                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO errata
                                    (advisory_id, title, description, severity,
                                     source, distribution, issued_date)
                                VALUES (%s, %s, %s, %s, 'rhel', %s, %s)
                                ON CONFLICT (advisory_id) DO NOTHING
                                RETURNING id
                            """, (
                                adv_name,
                                (e.get('advisory_synopsis') or adv_name)[:500],
                                vendor_url,
                                severity,
                                rhel_version,
                                e.get('issue_date'),
                            ))
                            row = cur.fetchone()
                            if not row:
                                continue  # già presente

                            errata_id = row['id']

                            for cve_id in cves:
                                cur.execute(
                                    "INSERT INTO cves (cve_id) VALUES (%s) "
                                    "ON CONFLICT (cve_id) DO UPDATE SET cve_id=EXCLUDED.cve_id RETURNING id",
                                    (cve_id,),
                                )
                                cve_row = cur.fetchone()
                                cur.execute(
                                    "INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) "
                                    "ON CONFLICT DO NOTHING",
                                    (errata_id, cve_row['id']),
                                )

                            total_errata += 1
                            total_cves   += len(cves)

                    except Exception as ex:
                        conn.rollback()
                        errors.append(f'{adv_name}: {str(ex)[:80]}')
                        logger.error(f'RHEL insert error {adv_name}: {ex}')
                        continue

                    if total_errata % 50 == 0:
                        conn.commit()
                        logger.info(f'RHEL CVE sync progress: {total_errata} errata, {total_cves} CVEs')

                conn.commit()

        _log_done(conn, log_id, total_errata, errors if errors else None)

    except Exception as ex:
        _log_error(conn, log_id, ex)
        _unlock(conn, 'rhel')
        raise

    _unlock(conn, 'rhel')
    logger.info(f'RHEL CVE sync done: {total_errata} new errata, {total_cves} CVEs, '
                f'{len(rhel_channels)} channels')
    return {
        'source':             'rhel',
        'total_errata':       total_errata,
        'total_cves':         total_cves,
        'channels_processed': len(rhel_channels),
        'errors':             len(errors),
    }


# ============================================================
# SYNC: NVD
# ============================================================
def _sync_nvd(conn, batch_size=50, force=False):
    """
    Arricchisce severity CVE tramite NVD API.
    Prioritizza CVE legati a errata critical/high non ancora processati.
    Propaga severity su errata.severity al termine.
    """
    if not _try_lock(conn, 'nvd'):
        logger.warning('NVD sync already running — skipped')
        return {'skipped': 'already_running'}

    with conn.cursor() as cur:
        if force:
            cur.execute(
                'SELECT DISTINCT cve_id FROM cves ORDER BY cve_id DESC LIMIT %s',
                (batch_size,),
            )
        else:
            cur.execute("""
                SELECT DISTINCT c.cve_id
                FROM cves c
                LEFT JOIN cve_details cd ON c.cve_id  = cd.cve_id
                JOIN errata_cves ec      ON c.id      = ec.cve_id
                JOIN errata e            ON ec.errata_id = e.id
                WHERE cd.cve_id IS NULL
                ORDER BY
                    CASE e.severity
                        WHEN 'critical' THEN 1
                        WHEN 'high'     THEN 2
                        WHEN 'medium'   THEN 3
                        ELSE 4
                    END,
                    c.cve_id DESC
                LIMIT %s
            """, (batch_size,))
        pending = [r['cve_id'] for r in cur.fetchall()]

    if not pending:
        _unlock(conn, 'nvd')
        logger.info('NVD sync: no CVEs to process')
        return {'processed': 0, 'pending_total': 0, 'errata_severity_updated': 0}

    log_id = _log_start(conn, 'nvd')
    logger.info(f'NVD sync: {len(pending)} CVEs to process')

    http = requests.Session()
    http.headers.update(_REQUEST_HEADERS)
    if NVD_API_KEY:
        http.headers['apiKey'] = NVD_API_KEY

    processed      = 0
    errors         = []
    updated_errata = 0

    try:
        for cve_id in pending:
            try:
                resp = http.get(f'{NVD_API_BASE}?cveId={cve_id}', timeout=30)
                resp.raise_for_status()
                vulns = resp.json().get('vulnerabilities', [])
                if not vulns:
                    time.sleep(0.6 if NVD_API_KEY else 6)
                    continue

                vuln    = vulns[0]['cve']
                metrics = vuln.get('metrics', {})

                cvss_v3_score = cvss_v3_vector = cvss_v3_severity = cvss_v2_score = None

                if 'cvssMetricV31' in metrics:
                    cvss_data        = metrics['cvssMetricV31'][0]['cvssData']
                    cvss_v3_score    = cvss_data['baseScore']
                    cvss_v3_vector   = cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()
                elif 'cvssMetricV30' in metrics:
                    cvss_data        = metrics['cvssMetricV30'][0]['cvssData']
                    cvss_v3_score    = cvss_data['baseScore']
                    cvss_v3_vector   = cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()

                if 'cvssMetricV2' in metrics:
                    cvss_v2_score = metrics['cvssMetricV2'][0]['cvssData']['baseScore']

                severity = cvss_v3_severity or cvss_to_severity(cvss_v3_score or cvss_v2_score) or 'MEDIUM'

                descs = vuln.get('descriptions', [])
                description = next(
                    (item['value'] for item in descs if item.get('lang') == 'en'),
                    descs[0]['value'] if descs else None,
                )
                cwes = [
                    item['value']
                    for w in vuln.get('weaknesses', [])
                    for item in w.get('description', [])
                    if item.get('value', '').startswith('CWE-')
                ]

                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO cve_details
                            (cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity,
                             cvss_v2_score, severity, description,
                             published_date, last_modified, cwe_ids, nvd_last_sync)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (cve_id) DO UPDATE SET
                            cvss_v3_score    = EXCLUDED.cvss_v3_score,
                            cvss_v3_vector   = EXCLUDED.cvss_v3_vector,
                            cvss_v3_severity = EXCLUDED.cvss_v3_severity,
                            cvss_v2_score    = EXCLUDED.cvss_v2_score,
                            severity         = EXCLUDED.severity,
                            cwe_ids          = EXCLUDED.cwe_ids,
                            nvd_last_sync    = NOW()
                    """, (
                        cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity,
                        cvss_v2_score, severity,
                        description[:4000] if description else None,
                        vuln.get('published'), vuln.get('lastModified'),
                        cwes or None,
                    ))
                conn.commit()
                processed += 1

            except Exception as e:
                errors.append(f'{cve_id}: {str(e)[:80]}')
                logger.warning(f'NVD error {cve_id}: {e}')

            time.sleep(0.6 if NVD_API_KEY else 6)

        updated_errata = _propagate_nvd_severity(conn)
        conn.commit()

    except Exception as ex:
        _log_error(conn, log_id, ex)
        _unlock(conn, 'nvd')
        raise

    _log_done(conn, log_id, processed, errors)
    _unlock(conn, 'nvd')
    logger.info(f'NVD done: {processed}/{len(pending)} CVEs, {updated_errata} errata updated')
    return {
        'processed':               processed,
        'pending_total':           len(pending),
        'errata_severity_updated': updated_errata,
        'errors':                  len(errors),
    }


# ============================================================
# SYNC: PACKAGE CACHE
# ============================================================
def _sync_packages(conn, channel_label=None):
    """
    Aggiorna la cache pacchetti UYUNI.
    Usa execute_values per bulk insert (un round-trip per canale).
    """
    if not _try_lock(conn, 'packages'):
        logger.warning('Package sync already running — skipped')
        return {'skipped': 'already_running'}

    log_id          = _log_start(conn, 'packages')
    total_synced    = 0
    channel_results = {}
    channel_errors  = []

    try:
        with _uyuni() as (client, session):
            channels = (
                [{'label': channel_label}]
                if channel_label
                else [ch for ch in client.channel.listAllChannels(session)
                      if map_channel_to_distribution(ch['label'])]
            )

            for ch in channels:
                label = ch['label']
                try:
                    pkgs = client.channel.software.listAllPackages(session, label)
                    if not pkgs:
                        # Lista vuota: il canale esiste ma non ha pacchetti (o UYUNI ha
                        # restituito risposta vuota). Non svuotiamo la cache esistente —
                        # meglio avere dati vecchi che perdere il matching.
                        channel_results[label] = 0
                        logger.debug(f'Package cache: channel {label} returned empty list — cache preserved')
                        continue
                    with conn.cursor() as cur:
                        cur.execute('DELETE FROM uyuni_package_cache WHERE channel_label=%s', (label,))
                        execute_values(cur, """
                            INSERT INTO uyuni_package_cache
                                (channel_label, package_id, package_name,
                                 package_version, package_release, package_arch)
                            VALUES %s
                            ON CONFLICT (channel_label, package_id) DO UPDATE SET
                                package_name = EXCLUDED.package_name,
                                last_sync    = NOW()
                        """, [
                            (label, p['id'], p['name'],
                             p.get('version', ''), p.get('release', ''), p.get('arch_label', ''))
                            for p in pkgs
                        ])
                    conn.commit()
                    channel_results[label] = len(pkgs)
                    total_synced += len(pkgs)
                    logger.debug(f'Package cache: {len(pkgs)} packages for {label}')

                except Exception as e:
                    conn.rollback()
                    channel_results[label] = f'error: {str(e)[:80]}'
                    channel_errors.append(f'{label}: {str(e)[:80]}')
                    logger.error(f'Package sync error for channel {label}: {e}')

        _log_done(conn, log_id, total_synced, channel_errors if channel_errors else None)

    except Exception as ex:
        _log_error(conn, log_id, ex)
        _unlock(conn, 'packages')
        raise

    _unlock(conn, 'packages')
    logger.info(f'Package cache done: {total_synced} packages across {len(channel_results)} channels')
    return {'total_packages_synced': total_synced, 'channels': channel_results}


# ============================================================
# PUSH ERRATA → UYUNI
# ============================================================
def _build_package_ids(errata_pkgs, cached_pkgs):
    """
    Ritorna il set di package_id UYUNI da associare all'errata.

    Gestisce correttamente il caso multi-release: un pacchetto può avere
    versioni fisse diverse per release diversi (es. jammy vs noble).
    Per ogni nome pacchetto raccoglie TUTTE le fixed_version e include
    il package se la versione in cache è >= ad almeno una di esse.

    Args:
        errata_pkgs: righe da errata_packages (package_name, fixed_version, release_name)
        cached_pkgs: righe da uyuni_package_cache (package_name, package_id, package_version)

    Returns:
        set di int (package_id)
    """
    # Costruisce {package_name → set(fixed_versions)} per gestire multi-release
    fixed_versions: dict[str, set] = {}
    for ep in errata_pkgs:
        name = ep['package_name']
        fv   = ep['fixed_version'] or ''
        fixed_versions.setdefault(name, set()).add(fv)

    package_ids = set()
    for c in cached_pkgs:
        name     = c['package_name']
        cache_v  = c['package_version'] or ''
        fixed_vs = fixed_versions.get(name, set())

        if not fixed_vs:
            # Pacchetto in cache ma non in errata_packages → non associare
            continue

        # Includi il package se la versione in cache è >= ad almeno una fixed_version
        # (la versione fissa è disponibile nel canale UYUNI)
        # Se tutte le fixed_version sono vuote → include comunque (no version info)
        if all(not fv for fv in fixed_vs):
            package_ids.add(c['package_id'])
        elif any(version_ge(cache_v, fv) for fv in fixed_vs if fv):
            package_ids.add(c['package_id'])

    return package_ids


def _push_single_errata(client, session, errata, package_ids, target_channels):
    """
    Chiama errata.create e poi errata.publish su UYUNI.

    errata.create ritorna la struttura dell'errata creata.
    errata.publish rende l'errata visibile ai sistemi nei canali specificati.
    Alcune versioni UYUNI auto-pubblicano alla create, in quel caso publish
    ritorna errore che viene ignorato silenziosamente.
    """
    dist      = errata['distribution']
    severity  = (errata.get('severity') or 'medium').lower()
    sev_label, keywords = SEVERITY_TO_UYUNI.get(severity, SEVERITY_TO_UYUNI['medium'])

    errata_info = {
        'synopsis':         (errata['title'] or errata['advisory_id'])[:200],
        'advisory_name':    errata['advisory_id'],
        'advisory_type':    'Security Advisory',
        'advisory_release': 1,
        'severity':         sev_label,
        'product':          dist.replace('-', ' ').title(),
        'topic':            (errata['title'] or '')[:500],
        'description':      (errata['description'] or '')[:2000],
        'solution':         'Apply the updated packages.',
        'references':       '',
        'notes':            f'Imported by UYUNI Errata Manager v{_APP_VERSION} from {errata["source"].upper()}',
    }

    logger.info(
        f'Pushing {errata["advisory_id"]} [{sev_label}] '
        f'— {len(package_ids)} packages, channels={target_channels}'
    )
    client.errata.create(session, errata_info, [], keywords, list(package_ids), target_channels)

    # Pubblica esplicitamente l'errata (alcune versioni UYUNI creano in draft)
    try:
        client.errata.publish(session, errata['advisory_id'], target_channels)
    except Exception as pub_err:
        # Già pubblicata o versione UYUNI che auto-pubblica → non bloccante
        logger.debug(f'errata.publish {errata["advisory_id"]}: {pub_err} (ignored)')


def _push_errata(conn, limit=10):
    """
    Push errata pendenti verso UYUNI con severity corretta e version matching.

    Fix v3.2:
    - fixed_ver_map multi-release: raccoglie tutte le versioni per nome pacchetto
    - version_ge() gestisce epoch Debian/Ubuntu
    - errata.publish() chiamato dopo create per garantire visibilità
    """
    if not _try_lock(conn, 'push'):
        logger.warning('Push already running — skipped')
        return {'skipped': 'already_running'}

    pushed      = 0
    skipped_ver = 0
    errors      = []
    pending     = []

    try:
        with _uyuni() as (client, session):
            all_channels = client.channel.listAllChannels(session)
            channel_map  = {}
            for ch in all_channels:
                dist = map_channel_to_distribution(ch['label'])
                if dist:
                    channel_map.setdefault(dist, []).append(ch['label'])

            if not channel_map:
                logger.warning('Push: no Ubuntu/Debian channels found in UYUNI')
                return {'pushed': 0, 'message': 'No Ubuntu/Debian channels found in UYUNI'}

            active_dists = list(channel_map.keys())

            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM errata
                    WHERE sync_status = 'pending'
                      AND distribution = ANY(%s)
                    ORDER BY
                        CASE severity
                            WHEN 'critical' THEN 1
                            WHEN 'high'     THEN 2
                            WHEN 'medium'   THEN 3
                            ELSE 4
                        END,
                        issued_date DESC
                    LIMIT %s
                """, (active_dists, limit))
                pending = list(cur.fetchall())

            for errata in pending:
                try:
                    dist            = errata['distribution']
                    target_channels = channel_map.get(dist, [])
                    if not target_channels:
                        continue

                    with conn.cursor() as cur:
                        cur.execute(
                            'SELECT package_name, fixed_version, release_name '
                            'FROM errata_packages WHERE errata_id=%s',
                            (errata['id'],),
                        )
                        errata_pkgs = cur.fetchall()

                    if not errata_pkgs:
                        # Errata senza pacchetti — push diretto (errata informativi)
                        package_ids = set()
                    else:
                        pkg_names = list({ep['package_name'] for ep in errata_pkgs})

                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT package_name, package_id, package_version
                                FROM uyuni_package_cache
                                WHERE channel_label = ANY(%s)
                                  AND package_name  = ANY(%s)
                            """, (target_channels, pkg_names))
                            cached_pkgs = cur.fetchall()

                        package_ids = _build_package_ids(errata_pkgs, cached_pkgs)

                        if not package_ids:
                            skipped_ver += 1
                            logger.debug(
                                f'Push skipped {errata["advisory_id"]}: '
                                f'no matching packages in UYUNI cache (version mismatch or not yet synced)'
                            )
                            continue

                    _push_single_errata(client, session, errata, package_ids, target_channels)

                    with conn.cursor() as cur:
                        cur.execute("UPDATE errata SET sync_status='synced' WHERE id=%s", (errata['id'],))
                    conn.commit()
                    pushed += 1

                except Exception as e:
                    msg = str(e)
                    if 'already exists' in msg.lower():
                        # Errata già presente su UYUNI → marca come synced
                        with conn.cursor() as cur:
                            cur.execute("UPDATE errata SET sync_status='synced' WHERE id=%s", (errata['id'],))
                        conn.commit()
                        pushed += 1
                        logger.debug(f'Errata {errata["advisory_id"]} already exists on UYUNI — marked synced')
                    else:
                        errors.append(f'{errata["advisory_id"]}: {msg[:80]}')
                        logger.error(f'Push error {errata["advisory_id"]}: {msg[:150]}')

    finally:
        _unlock(conn, 'push')

    logger.info(f'Push done: {pushed} pushed, {skipped_ver} skipped (version), {len(errors)} errors')
    return {
        'pushed':                   pushed,
        'skipped_version_mismatch': skipped_ver,
        'pending_processed':        len(pending),
        'errors':                   errors[:5] if errors else None,
    }


# ============================================================
# RHEL: aggiorna severity in UYUNI post-NVD
# ============================================================
def _update_rhel_severity(conn, limit=200):
    """
    Aggiorna la severity degli errata RHEL in UYUNI con il dato NVD arricchito.
    Usa errata.setDetails() — testato funzionante anche su errata vendor/CDN.
    Prioritizza critical → high → medium → low.
    Gli errata vengono marcati 'synced' dopo aggiornamento.
    _propagate_nvd_severity() li rimette 'pending' se NVD migliora ulteriormente.
    """
    if not _try_lock(conn, 'rhel_push'):
        logger.warning('RHEL severity update already running — skipped')
        return {'skipped': 'already_running'}

    with conn.cursor() as cur:
        cur.execute("""
            SELECT advisory_id, severity FROM errata
            WHERE source = 'rhel' AND sync_status = 'pending'
              AND severity IS NOT NULL
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high'     THEN 2
                    WHEN 'medium'   THEN 3
                    ELSE 4
                END,
                issued_date DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        pending = list(cur.fetchall())

    if not pending:
        _unlock(conn, 'rhel_push')
        logger.info('RHEL severity update: nothing pending')
        return {'updated': 0, 'pending': 0}

    updated = 0
    errors  = []

    try:
        with _uyuni() as (client, session):
            for e in pending:
                adv_name  = e['advisory_id']
                severity  = (e['severity'] or 'medium').lower()
                sev_label, _ = SEVERITY_TO_UYUNI.get(severity, SEVERITY_TO_UYUNI['medium'])

                try:
                    client.errata.setDetails(session, adv_name, {'severity': sev_label})
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE errata SET sync_status='synced' WHERE advisory_id=%s",
                            (adv_name,),
                        )
                    conn.commit()
                    updated += 1
                except Exception as ex:
                    msg = str(ex)
                    errors.append(f'{adv_name}: {msg[:80]}')
                    logger.error(f'RHEL setDetails failed {adv_name}: {msg[:150]}')

    finally:
        _unlock(conn, 'rhel_push')

    logger.info(f'RHEL severity update done: {updated}/{len(pending)} updated, '
                f'{len(errors)} errors')
    return {
        'updated':           updated,
        'pending_processed': len(pending),
        'errors':            errors[:5] if errors else None,
    }


# ============================================================
# FLASK ROUTES
# ============================================================

@app.route('/api/health', methods=['GET'])
def health():
    status = {'api': 'ok', 'database': 'unknown', 'uyuni': 'unknown', 'version': _APP_VERSION}
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {_sanitize_error(e)}'

    try:
        with _uyuni() as (client, session):
            client.api.getVersion()
        status['uyuni'] = 'ok'
    except RuntimeError:
        status['uyuni'] = 'not configured'
    except Exception as e:
        status['uyuni'] = f'error: {_sanitize_error(e)}'

    return jsonify(status)


@app.route('/api/health/detailed', methods=['GET'])
def health_detailed():
    result = {
        'version':    _APP_VERSION,
        'timestamp':  datetime.utcnow().isoformat(),
        'database':   {'connected': False},
        'uyuni':      {'connected': False, 'url': UYUNI_URL or 'not configured'},
        'sync_status': {},
        'cache':      {},
        'alerts':     {},
    }

    try:
        with _db() as conn:
            result['database']['connected'] = True
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM errata")
                result['database']['errata_total'] = cur.fetchone()['total']

                cur.execute("SELECT COUNT(*) AS pending FROM errata WHERE sync_status='pending'")
                result['database']['errata_pending'] = cur.fetchone()['pending']

                for sync_type in ('usn', 'dsa', 'nvd'):
                    cur.execute("""
                        SELECT completed_at FROM sync_logs
                        WHERE sync_type=%s AND status='completed'
                        ORDER BY completed_at DESC LIMIT 1
                    """, (sync_type,))
                    row = cur.fetchone()
                    if row and row['completed_at']:
                        ts    = row['completed_at'].replace(tzinfo=None)
                        age_h = round((datetime.utcnow() - ts).total_seconds() / 3600, 1)
                        result['sync_status'][f'last_{sync_type}_sync'] = ts.isoformat()
                        result['sync_status'][f'{sync_type}_age_hours'] = age_h
                    else:
                        result['sync_status'][f'last_{sync_type}_sync'] = None
                        result['sync_status'][f'{sync_type}_age_hours'] = None

                cur.execute(
                    "SELECT COUNT(*) AS total, MAX(last_sync) AS last_update FROM uyuni_package_cache"
                )
                row = cur.fetchone()
                last_upd = row['last_update']
                result['cache']['total_packages'] = row['total']
                result['cache']['last_update']    = last_upd.isoformat() if last_upd else None
                result['cache']['age_hours']       = (
                    round((datetime.utcnow() - last_upd.replace(tzinfo=None)).total_seconds() / 3600, 1)
                    if last_upd else None
                )

                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM sync_logs
                    WHERE status='error' AND started_at >= NOW() - INTERVAL '24 hours'
                """)
                result['alerts']['failed_syncs_24h'] = cur.fetchone()['cnt']
                result['alerts']['stale_cache']      = (
                    result['cache']['age_hours'] is None or result['cache']['age_hours'] > 48
                )
                usn_age = result['sync_status'].get('usn_age_hours')
                dsa_age = result['sync_status'].get('dsa_age_hours')
                result['alerts']['stale_usn_sync'] = usn_age is None or usn_age > 168
                result['alerts']['stale_dsa_sync'] = dsa_age is None or dsa_age > 168

    except Exception as e:
        result['database']['error'] = _sanitize_error(e)

    try:
        with _uyuni() as (client, session):
            client.api.getVersion()
        result['uyuni']['connected'] = True
    except RuntimeError:
        result['uyuni']['error'] = 'not configured'
    except Exception as e:
        result['uyuni']['error'] = _sanitize_error(e)

    return jsonify(result)


@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    try:
        with _db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sync_type, status, started_at, completed_at,
                           items_processed,
                           CASE
                               WHEN error_message IS NULL THEN NULL
                               ELSE LEFT(error_message, 100)
                           END AS error_summary
                    FROM sync_logs
                    ORDER BY started_at DESC
                    LIMIT 20
                """)
                logs = [dict(r) for r in cur.fetchall()]
        for r in logs:
            for k in ('started_at', 'completed_at'):
                if r[k]:
                    r[k] = r[k].isoformat()
        return jsonify({'logs': logs})
    except Exception as e:
        logger.error(f'sync_status error: {e}')
        return jsonify({'error': 'Internal error'}), 500


@app.route('/api/uyuni/channels', methods=['GET'])
def uyuni_channels():
    try:
        with _uyuni() as (client, session):
            channels = client.channel.listAllChannels(session)
            result = [
                {'label': ch['label'], 'name': ch['name'],
                 'distribution': map_channel_to_distribution(ch['label'])}
                for ch in channels
            ]
        return jsonify({'count': len(result), 'channels': result})
    except RuntimeError:
        return jsonify({'error': 'UYUNI not configured'}), 503
    except Exception as e:
        logger.error(f'uyuni_channels error: {e}')
        return jsonify({'error': 'Cannot reach UYUNI'}), 502


@app.route('/api/sync/usn', methods=['POST'])
def route_sync_usn():
    try:
        with _db() as conn:
            result = _sync_usn(conn)
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f'USN sync failed: {e}')
        return jsonify({'status': 'error', 'error': 'Sync failed — see logs'}), 500


@app.route('/api/sync/dsa', methods=['POST'])
def route_sync_dsa():
    # Rileva distribuzioni attive dai canali UYUNI prima di chiamare _sync_dsa,
    # coerente con route_sync_auto: evita processare release Debian non presenti in UYUNI.
    # Se active_dists è vuoto (UYUNI irraggiungibile), _sync_dsa usa il fallback
    # su tutti i release (active_dists=None → list(_DEBIAN_RELEASE_MAP.values())).
    active_dists = _get_active_distributions() or None
    try:
        with _db() as conn:
            result = _sync_dsa(conn, active_dists=active_dists)
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f'DSA sync failed: {e}')
        return jsonify({'status': 'error', 'error': 'Sync failed — see logs'}), 500


@app.route('/api/sync/nvd', methods=['POST'])
def route_sync_nvd():
    batch_size = _clamp(request.args.get('batch_size', 50, type=int), 50, 1, _MAX_BATCH_SIZE)
    force      = request.args.get('force', 'false').lower() == 'true'
    try:
        with _db() as conn:
            result = _sync_nvd(conn, batch_size=batch_size, force=force)
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f'NVD sync failed: {e}')
        return jsonify({'status': 'error', 'error': 'Sync failed — see logs'}), 500


@app.route('/api/sync/auto', methods=['POST'])
def route_sync_auto():
    """
    Pipeline completa:
    1. Rileva distribuzioni dai canali UYUNI (Ubuntu, Debian, RHEL)
    2. Sync USN se canali Ubuntu
    3. Sync DSA se canali Debian (solo release attivi)
    4. Sync RHEL CVEs da UYUNI se canali RHEL
    5. NVD enrichment → propaga severity reale (Ubuntu + Debian + RHEL)
    6. Aggiorna cache pacchetti
    7. Push errata pendenti (Ubuntu + Debian)
    8. Aggiorna severity RHEL in UYUNI via setDetails
    """
    nvd_batch  = _clamp(request.args.get('nvd_batch',  100, type=int), 100, 1, _MAX_BATCH_SIZE)
    push_limit = _clamp(request.args.get('push_limit',  50, type=int),  50, 1, _MAX_PUSH_LIMIT)

    results = {}

    active_dists = _get_active_distributions()
    results['active_distributions'] = sorted(active_dists)
    logger.info(f'Auto sync: active_distributions={active_dists}')

    if not active_dists:
        return jsonify({
            'status':  'warning',
            'message': 'No supported channels found in UYUNI',
            **results,
        })

    try:
        with _db() as conn:
            if 'ubuntu' in active_dists:
                results['usn'] = _sync_usn(conn)

            if any(d.startswith('debian') for d in active_dists):
                results['dsa'] = _sync_dsa(conn, active_dists=active_dists)

            if any(d.startswith('rhel') for d in active_dists):
                results['rhel'] = _sync_rhel_cves(conn)

            # NVD dopo tutte le sorgenti: arricchisce CVE Ubuntu + Debian + RHEL
            results['nvd'] = _sync_nvd(conn, batch_size=nvd_batch)

        with _db() as conn:
            results['packages'] = _sync_packages(conn)

        with _db() as conn:
            results['push'] = _push_errata(conn, limit=push_limit)

        # Dopo NVD: aggiorna severity RHEL in UYUNI
        if any(d.startswith('rhel') for d in active_dists):
            with _db() as conn:
                results['rhel_severity'] = _update_rhel_severity(conn)

    except Exception as e:
        logger.error(f'Auto sync pipeline error: {e}')
        results['error'] = 'Pipeline interrupted — see logs'
        return jsonify({'status': 'partial', **results}), 500

    return jsonify({'status': 'success', **results})


@app.route('/api/sync/rhel-nvd', methods=['POST'])
def route_sync_rhel_nvd():
    """
    Pipeline NVD enrichment per errata RHEL nativi UYUNI:
    1. Importa RHSA da UYUNI + estrae CVE IDs → DB locale
    2. Arricchisce CVE con CVSS NVD
    3. Aggiorna severity errata RHEL in UYUNI via setDetails
    """
    nvd_batch = _clamp(request.args.get('nvd_batch', 100, type=int), 100, 1, _MAX_BATCH_SIZE)
    results   = {}
    try:
        with _db() as conn:
            results['rhel'] = _sync_rhel_cves(conn)

        with _db() as conn:
            results['nvd'] = _sync_nvd(conn, batch_size=nvd_batch)

        with _db() as conn:
            results['rhel_severity'] = _update_rhel_severity(conn)

    except Exception as e:
        logger.error(f'RHEL NVD pipeline error: {e}')
        results['error'] = 'Pipeline interrupted — see logs'
        return jsonify({'status': 'partial', **results}), 500

    return jsonify({'status': 'success', **results})


@app.route('/api/uyuni/sync-packages', methods=['POST'])
def route_sync_packages():
    channel = request.args.get('channel')
    try:
        with _db() as conn:
            result = _sync_packages(conn, channel_label=channel)
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f'Package sync failed: {e}')
        return jsonify({'status': 'error', 'error': 'Sync failed — see logs'}), 500


@app.route('/api/uyuni/push', methods=['POST'])
def route_push():
    limit = _clamp(request.args.get('limit', 10, type=int), 10, 1, _MAX_PUSH_LIMIT)
    try:
        with _db() as conn:
            result = _push_errata(conn, limit=limit)
        return jsonify({'status': 'success', **result})
    except Exception as e:
        logger.error(f'Push failed: {e}')
        return jsonify({'status': 'error', 'error': 'Push failed — see logs'}), 500


# ============================================================
# SCHEDULER (opzionale — attivato con SCHEDULER_ENABLED=true)
# Ogni job usa advisory lock già integrato nelle funzioni _sync_*,
# quindi esecuzioni parallele (es. 2 worker gunicorn) vengono gestite
# in modo sicuro: il secondo worker riceve 'skipped — already_running'.
# ============================================================
_SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false').lower() == 'true'

if _SCHEDULER_ENABLED:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    # Traccia lo stato di ogni job (visibile in /api/scheduler/jobs)
    _job_status: dict = {}

    def _job(name, fn, **kwargs):
        logger.info(f'[Scheduler] START {name}')
        _job_status[name] = {
            'status':   'running',
            'last_run': datetime.utcnow().isoformat(),
        }
        try:
            with _db() as conn:
                result = fn(conn, **kwargs)
            logger.info(f'[Scheduler] DONE  {name}: {result}')
            _job_status[name] = {
                'status':   'ok',
                'last_run': datetime.utcnow().isoformat(),
                'result':   str(result)[:300],
            }
        except Exception as e:
            logger.error(f'[Scheduler] FAIL  {name}: {e}')
            _job_status[name] = {
                'status':   'error',
                'last_run': datetime.utcnow().isoformat(),
                'error':    str(e)[:300],
            }

    _scheduler = BackgroundScheduler(timezone='UTC')

    _scheduler.add_job(
        lambda: _job('usn', _sync_usn),
        CronTrigger(hour='6,12,18', minute=0), id='usn', replace_existing=True,
    )
    _scheduler.add_job(
        lambda: _job('dsa', _sync_dsa),
        CronTrigger(hour=3, minute=0), id='dsa', replace_existing=True,
    )
    _scheduler.add_job(
        lambda: _job('nvd', _sync_nvd, batch_size=200),
        CronTrigger(hour=4, minute=0), id='nvd', replace_existing=True,
    )
    _scheduler.add_job(
        lambda: _job('packages', _sync_packages),
        CronTrigger(hour=1, minute=0), id='packages', replace_existing=True,
    )
    _scheduler.add_job(
        lambda: _job('push', lambda conn: _push_errata(conn, limit=50)),
        CronTrigger(hour='0,6,12,18', minute=30), id='push', replace_existing=True,
    )

    def _rhel_pipeline(conn):
        """Pipeline RHEL scheduler: sync CVEs + aggiorna severity post-NVD."""
        r_sync = _sync_rhel_cves(conn)
        r_sev  = _update_rhel_severity(conn)
        return {'sync': r_sync, 'severity': r_sev}

    _scheduler.add_job(
        lambda: _job('rhel_pipeline', _rhel_pipeline),
        CronTrigger(hour=5, minute=0), id='rhel_pipeline', replace_existing=True,
    )

    _scheduler.start()
    logger.info('[Scheduler] APScheduler avviato — usn(6,12,18h) dsa(3h) nvd(4h) rhel(5h) packages(1h) push(0:30,6:30,12:30,18:30)')


@app.route('/api/scheduler/jobs', methods=['GET'])
def scheduler_jobs():
    if not _SCHEDULER_ENABLED:
        return jsonify({'enabled': False, 'message': 'Scheduler non attivo — set SCHEDULER_ENABLED=true'})
    jobs = [
        {
            'id':       job.id,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            **_job_status.get(job.id, {'status': 'never_run'}),
        }
        for job in _scheduler.get_jobs()
    ]
    failed = [j for j in jobs if j.get('status') == 'error']
    return jsonify({
        'enabled':      True,
        'jobs':         jobs,
        'failed_count': len(failed),
    })


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == '__main__':
    logger.info(f'Starting UYUNI Errata Manager v{_APP_VERSION} (development mode)')
    app.run(host='127.0.0.1', port=5000, debug=False)
