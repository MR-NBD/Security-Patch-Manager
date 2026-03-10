#!/usr/bin/env python3
"""
UYUNI Errata Manager - v3.1

Sincronizza errata Ubuntu USN e/o Debian DSA verso UYUNI Server.
Le distribuzioni vengono rilevate automaticamente dai canali UYUNI attivi.
NVD arricchisce la severity CVSS reale dopo ogni sync.

Endpoints:
  POST /api/sync/auto           — pipeline completa auto-detect
  POST /api/sync/usn            — solo Ubuntu USN
  POST /api/sync/dsa            — solo Debian DSA
  POST /api/sync/nvd            — solo NVD enrichment
  POST /api/uyuni/sync-packages — aggiorna cache pacchetti
  POST /api/uyuni/push          — push errata pendenti a UYUNI
  GET  /api/uyuni/channels      — canali con distribuzione mappata
  GET  /api/sync/status         — log ultimi 20 sync
  GET  /api/health              — stato API, DB, UYUNI (no auth)
  GET  /api/health/detailed     — stato dettagliato con metriche e alert (no auth)

Auth: header X-API-Key richiesto su tutti gli endpoint tranne /api/health*.
      Disabilitato se SPM_API_KEY non è impostata.
"""

import contextlib
import os
import ssl
import sys
import time
import xmlrpc.client
from datetime import datetime

from flask import Flask, g, jsonify, request
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
DATABASE_URL    = os.environ.get('DATABASE_URL')
UYUNI_URL       = os.environ.get('UYUNI_URL', '')
UYUNI_USER      = os.environ.get('UYUNI_USER', '')
UYUNI_PASSWORD  = os.environ.get('UYUNI_PASSWORD', '')
UYUNI_VERIFY_SSL = os.environ.get('UYUNI_VERIFY_SSL', 'false').lower() == 'true'
NVD_API_KEY     = os.environ.get('NVD_API_KEY', '')
NVD_API_BASE    = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
SPM_API_KEY     = os.environ.get('SPM_API_KEY', '')

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
_REQUEST_HEADERS = {'User-Agent': 'UYUNI-Errata-Manager/3.1'}

# severity interna → (label UYUNI, keywords per errata.create)
SEVERITY_TO_UYUNI = {
    'critical': ('Critical',  ['critical', 'security']),
    'high':     ('Important', ['important', 'security']),
    'medium':   ('Moderate',  ['moderate',  'security']),
    'low':      ('Low',       ['low',       'security']),
}

# Mappature severity sorgente (costanti di modulo, non ricostruite nel loop)
_USN_PRIORITY_MAP = {
    'critical': 'critical', 'high': 'high',
    'medium': 'medium', 'low': 'low', 'negligible': 'low',
}
_DSA_URGENCY_MAP = {
    'critical': 'critical', 'emergency': 'critical',
    'high': 'high', 'medium': 'medium',
    'low': 'low', 'unimportant': 'low', 'not yet assigned': 'medium',
}

# advisory lock keys PostgreSQL — interi unici per tipo di operazione
_LOCK_KEYS = {'usn': 1001, 'dsa': 1002, 'nvd': 1003, 'packages': 1004, 'push': 1005}

# Limiti input API
_MAX_BATCH_SIZE = 500
_MAX_PUSH_LIMIT = 200

# Endpoint che non richiedono autenticazione
_AUTH_EXEMPT = {'health', 'health_detailed'}

# Release Debian supportate
_DEBIAN_RELEASE_MAP = {
    'debian-bookworm': 'bookworm',
    'debian-bullseye': 'bullseye',
    'debian-trixie':   'trixie',
}


# ============================================================
# AUTENTICAZIONE
# ============================================================
@app.before_request
def _check_api_key():
    if request.endpoint in _AUTH_EXEMPT:
        return
    if not SPM_API_KEY:
        return  # auth disabilitata
    key = request.headers.get('X-API-Key', '')
    if key != SPM_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401


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


@contextlib.contextmanager
def _uyuni():
    """Sessione UYUNI XML-RPC con logout garantito."""
    if not UYUNI_URL:
        raise RuntimeError('UYUNI_URL not configured')
    ctx = ssl.create_default_context()
    ctx.check_hostname = UYUNI_VERIFY_SSL
    ctx.verify_mode    = ssl.CERT_REQUIRED if UYUNI_VERIFY_SSL else ssl.CERT_NONE
    client  = xmlrpc.client.ServerProxy(f'{UYUNI_URL}/rpc/api', context=ctx)
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
    """Acquisisce un advisory lock PostgreSQL (non bloccante). Ritorna True se acquisito."""
    key = _LOCK_KEYS.get(name)
    if key is None:
        return True
    with conn.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_lock(%s)', (key,))
        return cur.fetchone()[0]


def _unlock(conn, name):
    key = _LOCK_KEYS.get(name)
    if key is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_unlock(%s)', (key,))
    except Exception:
        pass  # connessione già chiusa rilascia i lock automaticamente


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


def version_compare(v1, v2):
    """True se v1 >= v2. Usa packaging.version; fallback conservativo su errore."""
    try:
        return pkg_version.parse(v1) >= pkg_version.parse(v2)
    except Exception:
        # Non possiamo confrontare → non includiamo il pacchetto (sicuro per default)
        return False


def cvss_to_severity(score):
    if score is None:
        return None
    if score >= 9.0: return 'CRITICAL'
    if score >= 7.0: return 'HIGH'
    if score >= 4.0: return 'MEDIUM'
    return 'LOW'


def _clamp(value, default, min_val, max_val):
    """Ritorna value forzato nell'intervallo [min_val, max_val]."""
    if value is None:
        return default
    return max(min_val, min(max_val, value))


def _sanitize_error(exc):
    """Ritorna stringa di errore sicura per API response (no credenziali)."""
    msg = str(exc)
    # Oscura pattern di connection string
    for kw in ('password', 'passwd', 'secret', 'user=', 'host=', 'dbname='):
        if kw.lower() in msg.lower():
            return 'Internal error — see application logs'
    return msg[:200]


def _get_active_distributions():
    """Ritorna le distribuzioni mappate dai canali UYUNI attivi."""
    try:
        with _uyuni() as (client, session):
            channels = client.channel.listAllChannels(session)
            return {d for ch in channels if (d := map_channel_to_distribution(ch['label']))}
    except Exception as e:
        logger.error(f'Cannot read UYUNI channels: {e}')
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
            SET    severity = nb.best_severity
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
                    c if isinstance(c, str) else c.get('id', '')
                    for c in (cves if isinstance(cves, list) else [])
                    if c
                ]

                packages = [
                    {'name': p['name'], 'version': p.get('version', ''), 'release': rel.lower()}
                    for rel, pkgs in n.get('release_packages', {}).items()
                    if any(r in rel.lower() for r in ('noble', 'jammy', 'focal', 'mantic', 'lunar'))
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
                            if cve_id.startswith('CVE-'):
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
    # Determina release da sincronizzare — inizializzazione esplicita
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
                    if not cve_id.startswith('CVE-') or not isinstance(cve_data, dict):
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

                        # Savepoint per isolamento: un record bad non abortisce il batch
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

            conn.commit()  # commit residui finali

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
                    cvss_data      = metrics['cvssMetricV31'][0]['cvssData']
                    cvss_v3_score  = cvss_data['baseScore']
                    cvss_v3_vector = cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()
                elif 'cvssMetricV30' in metrics:
                    cvss_data      = metrics['cvssMetricV30'][0]['cvssData']
                    cvss_v3_score  = cvss_data['baseScore']
                    cvss_v3_vector = cvss_data['vectorString']
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
    Usa execute_values per bulk insert (un round-trip per canale, non uno per pacchetto).
    """
    if not _try_lock(conn, 'packages'):
        logger.warning('Package sync already running — skipped')
        return {'skipped': 'already_running'}

    total_synced    = 0
    channel_results = {}

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
                    with conn.cursor() as cur:
                        cur.execute('DELETE FROM uyuni_package_cache WHERE channel_label=%s', (label,))
                        if pkgs:
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
                    logger.error(f'Package sync error for channel {label}: {e}')

    finally:
        _unlock(conn, 'packages')

    logger.info(f'Package cache done: {total_synced} packages across {len(channel_results)} channels')
    return {'total_packages_synced': total_synced, 'channels': channel_results}


# ============================================================
# PUSH ERRATA → UYUNI
# ============================================================
def _push_errata(conn, limit=10):
    """
    Push errata pendenti verso UYUNI con severity corretta e version matching.
    Package lookup: una singola query IN per errata (non N×M query individuali).
    """
    if not _try_lock(conn, 'push'):
        logger.warning('Push already running — skipped')
        return {'skipped': 'already_running'}

    pending       = []
    pushed        = 0
    skipped_ver   = 0
    errors        = []

    try:
        with _uyuni() as (client, session):
            all_channels = client.channel.listAllChannels(session)
            channel_map  = {}
            for ch in all_channels:
                dist = map_channel_to_distribution(ch['label'])
                if dist:
                    channel_map.setdefault(dist, []).append(ch['label'])

            if not channel_map:
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
                pending = cur.fetchall()

            for errata in pending:
                try:
                    dist            = errata['distribution']
                    target_channels = channel_map.get(dist, [])
                    if not target_channels:
                        continue

                    # Recupera pacchetti dell'errata
                    with conn.cursor() as cur:
                        cur.execute(
                            'SELECT package_name, fixed_version FROM errata_packages WHERE errata_id=%s',
                            (errata['id'],),
                        )
                        errata_pkgs = cur.fetchall()

                    if not errata_pkgs:
                        # Errata senza pacchetti associati — push diretto senza package IDs
                        package_ids = []
                    else:
                        # Un'unica query per tutti i package × tutti i canali target
                        pkg_names = list({ep['package_name'] for ep in errata_pkgs})
                        fixed_ver_map = {ep['package_name']: ep['fixed_version'] for ep in errata_pkgs}

                        with conn.cursor() as cur:
                            cur.execute("""
                                SELECT package_name, package_id, package_version
                                FROM uyuni_package_cache
                                WHERE channel_label = ANY(%s)
                                  AND package_name  = ANY(%s)
                            """, (target_channels, pkg_names))
                            cached = cur.fetchall()

                        package_ids = list({
                            c['package_id']
                            for c in cached
                            if (
                                not fixed_ver_map.get(c['package_name'])
                                or not c['package_version']
                                or version_compare(c['package_version'], fixed_ver_map[c['package_name']])
                            )
                        })

                        if not package_ids:
                            # Versioni nel cache non ancora aggiornate — riprova al prossimo sync
                            skipped_ver += 1
                            logger.debug(f'Push skipped {errata["advisory_id"]}: version mismatch, will retry')
                            continue

                    severity        = (errata.get('severity') or 'medium').lower()
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
                        'notes':            f'Imported by UYUNI Errata Manager v3.1 from {errata["source"].upper()}',
                    }

                    logger.info(
                        f'Pushing {errata["advisory_id"]} [{sev_label}] '
                        f'— {len(package_ids)} packages, channels={target_channels}'
                    )
                    client.errata.create(session, errata_info, [], keywords, package_ids, target_channels)

                    with conn.cursor() as cur:
                        cur.execute("UPDATE errata SET sync_status='synced' WHERE id=%s", (errata['id'],))
                    conn.commit()
                    pushed += 1

                except Exception as e:
                    msg = str(e)
                    if 'already exists' in msg.lower():
                        with conn.cursor() as cur:
                            cur.execute("UPDATE errata SET sync_status='synced' WHERE id=%s", (errata['id'],))
                        conn.commit()
                        pushed += 1
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
# FLASK ROUTES
# ============================================================

@app.route('/api/health', methods=['GET'])
def health():
    status = {'api': 'ok', 'database': 'unknown', 'uyuni': 'unknown', 'version': '3.1'}
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
        'version':    '3.1',
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
                        ts = row['completed_at'].replace(tzinfo=None)
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
                result['cache']['last_update'] = last_upd.isoformat() if last_upd else None
                result['cache']['age_hours'] = (
                    round((datetime.utcnow() - last_upd.replace(tzinfo=None)).total_seconds() / 3600, 1)
                    if last_upd else None
                )

                cur.execute("""
                    SELECT COUNT(*) AS cnt FROM sync_logs
                    WHERE status='error' AND started_at >= NOW() - INTERVAL '24 hours'
                """)
                result['alerts']['failed_syncs_24h'] = cur.fetchone()['cnt']
                result['alerts']['stale_cache'] = (
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
    try:
        with _db() as conn:
            result = _sync_dsa(conn)
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
    1. Rileva distribuzioni dai canali UYUNI
    2. Sync USN se ci sono canali Ubuntu
    3. Sync DSA se ci sono canali Debian (solo release attivi)
    4. NVD enrichment → propaga severity reale
    5. Aggiorna cache pacchetti
    6. Push errata pendenti
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
            'message': 'No Ubuntu/Debian channels found in UYUNI',
            **results,
        })

    try:
        with _db() as conn:
            if 'ubuntu' in active_dists:
                results['usn'] = _sync_usn(conn)

            if any(d.startswith('debian') for d in active_dists):
                results['dsa'] = _sync_dsa(conn, active_dists=active_dists)

            results['nvd'] = _sync_nvd(conn, batch_size=nvd_batch)

        with _db() as conn:
            results['packages'] = _sync_packages(conn)

        with _db() as conn:
            results['push'] = _push_errata(conn, limit=push_limit)

    except Exception as e:
        logger.error(f'Auto sync pipeline error: {e}')
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
# Sostituisce le Azure Logic Apps. Ogni job usa advisory lock
# già integrato nelle funzioni _sync_*, quindi esecuzioni
# parallele (es. 2 worker gunicorn) vengono gestite in modo
# sicuro: il secondo worker riceve 'skipped — already_running'.
# ============================================================
_SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false').lower() == 'true'

if _SCHEDULER_ENABLED:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    def _job(name, fn, **kwargs):
        """Wrapper generico: crea connessione DB e chiama la funzione sync."""
        logger.info(f'[Scheduler] START {name}')
        try:
            with _db() as conn:
                result = fn(conn, **kwargs)
            logger.info(f'[Scheduler] DONE  {name}: {result}')
        except Exception as e:
            logger.error(f'[Scheduler] FAIL  {name}: {e}')

    _scheduler = BackgroundScheduler(timezone='UTC')

    # USN — 3 volte al giorno (06:00, 12:00, 18:00 UTC)
    _scheduler.add_job(
        lambda: _job('usn', _sync_usn),
        CronTrigger(hour='6,12,18', minute=0), id='usn', replace_existing=True,
    )
    # DSA — ogni giorno alle 03:00 UTC
    _scheduler.add_job(
        lambda: _job('dsa', _sync_dsa),
        CronTrigger(hour=3, minute=0), id='dsa', replace_existing=True,
    )
    # NVD enrichment — ogni giorno alle 04:00 UTC
    _scheduler.add_job(
        lambda: _job('nvd', _sync_nvd, batch_size=200),
        CronTrigger(hour=4, minute=0), id='nvd', replace_existing=True,
    )
    # Package cache — ogni giorno alle 01:00 UTC
    _scheduler.add_job(
        lambda: _job('packages', _sync_packages),
        CronTrigger(hour=1, minute=0), id='packages', replace_existing=True,
    )
    # Push → UYUNI — 4 volte al giorno (00:30, 06:30, 12:30, 18:30 UTC)
    _scheduler.add_job(
        lambda: _job('push', lambda conn: _push_errata(conn, limit=50)),
        CronTrigger(hour='0,6,12,18', minute=30), id='push', replace_existing=True,
    )

    _scheduler.start()
    logger.info('[Scheduler] APScheduler avviato — usn(6,12,18h) dsa(3h) nvd(4h) packages(1h) push(0:30,6:30,12:30,18:30)')


@app.route('/api/scheduler/jobs', methods=['GET'])
def scheduler_jobs():
    """Stato jobs scheduler (solo se SCHEDULER_ENABLED=true)."""
    if not _SCHEDULER_ENABLED:
        return jsonify({'enabled': False, 'message': 'Scheduler non attivo — set SCHEDULER_ENABLED=true'})
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            'id':       job.id,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return jsonify({'enabled': True, 'jobs': jobs})


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == '__main__':
    logger.info('Starting UYUNI Errata Manager v3.1 (development mode)')
    # In produzione usare gunicorn: gunicorn --bind 0.0.0.0:5000 app:app
    app.run(host='127.0.0.1', port=5000, debug=False)
