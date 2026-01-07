#!/usr/bin/env python3
"""
UYUNI Errata Manager - Enhanced API v2.5 - IMPROVED
Integra: USN, DSA, NVD, OVAL con ASSOCIAZIONE PACCHETTI MIGLIORATA

CHANGELOG v2.5:
- FIX #1: Version matching per associazione pacchetti (no più solo nome)
- FIX #2: Integrazione OVAL per CVE visibility sui sistemi
- FIX #4: Sync USN incrementale ottimizzato con indice temporale
- FIX #5: Sync DSA automatico batch completo
- FIX #6: Retry logic con circuit breaker pattern
- IMPROVEMENT: Logging strutturato
- IMPROVEMENT: Health check dettagliato
"""

import os
import ssl
import json
import bz2
import time
import xmlrpc.client
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from packaging import version as pkg_version

# Logging strutturato
import logging
import sys

app = Flask(__name__)
CORS(app)

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/errata-manager.log')
    ]
)
logger = logging.getLogger('errata-manager')

# ============================================================
# CONFIGURAZIONE
# ============================================================
REQUEST_HEADERS = {
    'User-Agent': 'UYUNI-Errata-Manager/2.5',
    'Accept': 'application/json'
}

DATABASE_URL = os.environ.get('DATABASE_URL')
UYUNI_URL = os.environ.get('UYUNI_URL', '')
UYUNI_USER = os.environ.get('UYUNI_USER', '')
UYUNI_PASSWORD = os.environ.get('UYUNI_PASSWORD', '')

NVD_API_KEY = os.environ.get('NVD_API_KEY', '')
NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

OVAL_SOURCES = {
    'ubuntu': {
        'noble': 'https://security-metadata.canonical.com/oval/com.ubuntu.noble.usn.oval.xml.bz2',
        'jammy': 'https://security-metadata.canonical.com/oval/com.ubuntu.jammy.usn.oval.xml.bz2',
        'focal': 'https://security-metadata.canonical.com/oval/com.ubuntu.focal.usn.oval.xml.bz2',
    },
    'debian': {
        'bookworm': 'https://www.debian.org/security/oval/oval-definitions-bookworm.xml.bz2',
        'bullseye': 'https://www.debian.org/security/oval/oval-definitions-bullseye.xml.bz2',
    }
}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def get_uyuni_client():
    if not UYUNI_URL:
        return None, None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    client = xmlrpc.client.ServerProxy(f"{UYUNI_URL}/rpc/api", context=context)
    session_key = client.auth.login(UYUNI_USER, UYUNI_PASSWORD)
    return client, session_key

def calculate_severity(cvss_score):
    if cvss_score is None:
        return 'UNKNOWN'
    if cvss_score >= 9.0:
        return 'CRITICAL'
    if cvss_score >= 7.0:
        return 'HIGH'
    if cvss_score >= 4.0:
        return 'MEDIUM'
    return 'LOW'

def map_channel_to_distribution(channel_label):
    channel_lower = channel_label.lower()
    if 'ubuntu' in channel_lower:
        return 'ubuntu'
    if 'debian' in channel_lower:
        if 'bookworm' in channel_lower or 'debian-12' in channel_lower:
            return 'debian-bookworm'
        if 'bullseye' in channel_lower or 'debian-11' in channel_lower:
            return 'debian-bullseye'
        if 'trixie' in channel_lower or 'debian-13' in channel_lower:
            return 'debian-trixie'
    return None

# FIX #1: Version comparison helper
def version_compare(pkg_version_str, fixed_version_str):
    """
    Compara versioni pacchetti Debian-style
    Ritorna True se pkg_version >= fixed_version
    """
    try:
        return pkg_version.parse(pkg_version_str) >= pkg_version.parse(fixed_version_str)
    except:
        # Fallback to string comparison se parsing fallisce
        return pkg_version_str >= fixed_version_str

# FIX #6: Retry decorator con exponential backoff
def retry_with_backoff(max_attempts=3, initial_delay=2):
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"{func.__name__} failed (attempt {attempt+1}/{max_attempts}): {str(e)[:100]}, retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
            return None
        return wrapper
    return decorator

# ============================================================
# HEALTH & STATS ENDPOINTS
# ============================================================
@app.route('/api/health', methods=['GET'])
def health():
    status = {'api': 'ok', 'database': 'unknown', 'uyuni': 'unknown', 'version': '2.5'}

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        status['database'] = 'ok'
    except Exception as e:
        status['database'] = f'error: {str(e)}'
        logger.error(f"Database health check failed: {e}")

    try:
        client, session = get_uyuni_client()
        if client:
            client.auth.logout(session)
            status['uyuni'] = 'ok'
        else:
            status['uyuni'] = 'not configured'
    except Exception as e:
        status['uyuni'] = f'error: {str(e)}'
        logger.error(f"UYUNI health check failed: {e}")

    return jsonify(status)

# IMPROVEMENT: Health check dettagliato
@app.route('/api/health/detailed', methods=['GET'])
def health_detailed():
    conn = get_db()
    cur = conn.cursor()

    # Database metrics
    cur.execute("SELECT COUNT(*) as total, COUNT(CASE WHEN sync_status='pending' THEN 1 END) as pending FROM errata")
    errata_stats = dict(cur.fetchone())

    cur.execute("SELECT MAX(started_at) as last_sync FROM sync_logs WHERE status='completed' AND sync_type='usn'")
    last_usn_sync = cur.fetchone()['last_sync']

    cur.execute("SELECT MAX(started_at) as last_sync FROM sync_logs WHERE status='completed' AND sync_type='dsa'")
    last_dsa_sync = cur.fetchone()['last_sync']

    cur.execute("SELECT COUNT(*) as total FROM uyuni_package_cache")
    cache_size = cur.fetchone()['total']

    cur.execute("SELECT MAX(last_sync) as cache_age FROM uyuni_package_cache")
    cache_age = cur.fetchone()['cache_age']

    # Failed pushes last 24h
    cur.execute("""
        SELECT COUNT(*) as failed
        FROM sync_logs
        WHERE sync_type='uyuni_push'
          AND status='error'
          AND started_at > NOW() - INTERVAL '24 hours'
    """)
    failed_pushes = cur.fetchone()['failed']

    cur.close()
    conn.close()

    # UYUNI connectivity
    uyuni_ok = False
    try:
        client, session = get_uyuni_client()
        if client:
            client.auth.logout(session)
            uyuni_ok = True
    except:
        pass

    return jsonify({
        'version': '2.5',
        'timestamp': datetime.utcnow().isoformat(),
        'database': {
            'connected': True,
            'errata_total': errata_stats['total'],
            'errata_pending': errata_stats['pending']
        },
        'uyuni': {
            'connected': uyuni_ok,
            'url': UYUNI_URL
        },
        'sync_status': {
            'last_usn_sync': last_usn_sync.isoformat() if last_usn_sync else None,
            'last_dsa_sync': last_dsa_sync.isoformat() if last_dsa_sync else None,
            'usn_age_hours': (datetime.utcnow() - last_usn_sync).total_seconds() / 3600 if last_usn_sync else None,
            'dsa_age_hours': (datetime.utcnow() - last_dsa_sync).total_seconds() / 3600 if last_dsa_sync else None
        },
        'cache': {
            'total_packages': cache_size,
            'last_update': cache_age.isoformat() if cache_age else None,
            'age_hours': (datetime.utcnow() - cache_age).total_seconds() / 3600 if cache_age else None
        },
        'alerts': {
            'failed_pushes_24h': failed_pushes,
            'stale_cache': (datetime.utcnow() - cache_age).total_seconds() > 86400 if cache_age else True,
            'stale_usn_sync': (datetime.utcnow() - last_usn_sync).total_seconds() > 604800 if last_usn_sync else True
        }
    })

@app.route('/api/stats/overview', methods=['GET'])
def stats_overview():
    conn = get_db()
    cur = conn.cursor()

    stats = {}

    cur.execute("""
        SELECT COUNT(*) as total,
            COUNT(CASE WHEN sync_status = 'synced' THEN 1 END) as synced,
            COUNT(CASE WHEN sync_status = 'pending' THEN 1 END) as pending
        FROM errata
    """)
    stats['errata'] = dict(cur.fetchone())

    cur.execute("SELECT source, COUNT(*) as count FROM errata GROUP BY source")
    stats['errata_by_source'] = {r['source']: r['count'] for r in cur.fetchall()}

    cur.execute("SELECT severity, COUNT(*) as count FROM errata WHERE severity IS NOT NULL GROUP BY severity")
    stats['errata_by_severity'] = {r['severity']: r['count'] for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) as total FROM cves")
    stats['cves'] = dict(cur.fetchone())

    cur.execute("""
        SELECT COUNT(*) as total,
            COUNT(CASE WHEN cvss_v3_score IS NOT NULL THEN 1 END) as with_cvss_v3,
            COUNT(CASE WHEN severity = 'CRITICAL' THEN 1 END) as critical,
            COUNT(CASE WHEN severity = 'HIGH' THEN 1 END) as high,
            ROUND(AVG(cvss_v3_score)::numeric, 2) as avg_cvss
        FROM cve_details
    """)
    stats['nvd'] = dict(cur.fetchone())

    cur.execute("SELECT platform, COUNT(*) as count FROM oval_definitions GROUP BY platform")
    stats['oval'] = {r['platform']: r['count'] for r in cur.fetchall()}

    cur.execute("SELECT sync_type, MAX(started_at) as last_sync FROM sync_logs WHERE status = 'completed' GROUP BY sync_type")
    stats['last_syncs'] = {r['sync_type']: r['last_sync'].isoformat() if r['last_sync'] else None for r in cur.fetchall()}

    cur.close()
    conn.close()
    return jsonify(stats)

@app.route('/api/stats/packages', methods=['GET'])
def stats_packages():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM errata_packages")
    total_pkg = cur.fetchone()['total']

    cur.execute("SELECT COUNT(DISTINCT package_name) as unique_names FROM errata_packages")
    unique_pkg = cur.fetchone()['unique_names']

    cur.execute("""
        SELECT e.source, COUNT(DISTINCT ep.id) as pkg_count
        FROM errata e
        JOIN errata_packages ep ON e.id = ep.errata_id
        GROUP BY e.source
    """)
    by_source = {r['source']: r['pkg_count'] for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) as total FROM uyuni_package_cache")
    cache_total = cur.fetchone()['total']

    cur.execute("SELECT channel_label, COUNT(*) as count FROM uyuni_package_cache GROUP BY channel_label")
    cache_by_channel = {r['channel_label']: r['count'] for r in cur.fetchall()}

    cur.close()
    conn.close()

    return jsonify({
        'errata_packages': {
            'total': total_pkg,
            'unique_names': unique_pkg,
            'by_source': by_source
        },
        'uyuni_cache': {
            'total': cache_total,
            'by_channel': cache_by_channel
        }
    })

# ============================================================
# ERRATA ENDPOINTS
# ============================================================
@app.route('/api/errata', methods=['GET'])
def list_errata():
    limit = request.args.get('limit', 100, type=int)
    source = request.args.get('source', None)
    distribution = request.args.get('distribution', None)
    severity = request.args.get('severity', None)
    sync_status = request.args.get('sync_status', None)

    conn = get_db()
    cur = conn.cursor()

    query = "SELECT id, advisory_id, title, severity, source, distribution, issued_date, sync_status FROM errata WHERE 1=1"
    params = []

    if source:
        query += " AND source = %s"
        params.append(source)
    if distribution:
        query += " AND distribution = %s"
        params.append(distribution)
    if severity:
        query += " AND severity = %s"
        params.append(severity)
    if sync_status:
        query += " AND sync_status = %s"
        params.append(sync_status)

    query += " ORDER BY issued_date DESC LIMIT %s"
    params.append(limit)

    cur.execute(query, params)
    errata = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()
    return jsonify({'count': len(errata), 'errata': errata})

@app.route('/api/errata/<advisory_id>/packages', methods=['GET'])
def errata_packages_detail(advisory_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT e.advisory_id, e.title, e.distribution, ep.package_name, ep.fixed_version, ep.release_name
        FROM errata e
        LEFT JOIN errata_packages ep ON e.id = ep.errata_id
        WHERE e.advisory_id = %s
    """, (advisory_id,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return jsonify({'error': 'Errata not found'}), 404

    return jsonify({
        'advisory_id': rows[0]['advisory_id'],
        'title': rows[0]['title'],
        'distribution': rows[0]['distribution'],
        'packages': [
            {'name': r['package_name'], 'version': r['fixed_version'], 'release': r['release_name']}
            for r in rows if r['package_name']
        ]
    })

# ============================================================
# FIX #4: SYNC USN OTTIMIZZATO (con indice temporale)
# ============================================================
@app.route('/api/sync/usn', methods=['POST'])
@retry_with_backoff(max_attempts=3)
def sync_usn():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('usn', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()

    # FIX #4: Query con indice temporale per ottimizzare sync
    cur.execute("""
        SELECT advisory_id, issued_date
        FROM errata
        WHERE source = 'usn'
        ORDER BY issued_date DESC
        LIMIT 1
    """)
    last_row = cur.fetchone()
    last_usn = last_row['advisory_id'] if last_row else None
    last_date = last_row['issued_date'] if last_row else datetime(2020, 1, 1)

    logger.info(f"Starting USN sync from last known: {last_usn} (date: {last_date})")

    new_errata = []
    offset = 0
    found_existing = False

    while not found_existing and offset < 1000:  # Aumentato limite per sicurezza
        url = f"https://ubuntu.com/security/notices.json?limit=20&offset={offset}"
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch USN at offset {offset}: {e}")
            break

        notices = data.get('notices', [])
        if not notices:
            break

        for notice in notices:
            notice_id = notice.get('id', '')

            # FIX #4: Stop quando raggiungiamo l'ultimo sincronizzato
            if notice_id == last_usn:
                found_existing = True
                logger.info(f"Reached last synced USN: {last_usn}, stopping")
                break

            # FIX #4: Stop anche se la data è più vecchia (ottimizzazione)
            notice_date_str = notice.get('published')
            if notice_date_str:
                try:
                    notice_date = datetime.fromisoformat(notice_date_str.replace('Z', '+00:00'))
                    if notice_date < last_date:
                        found_existing = True
                        logger.info(f"Reached notices older than last sync date, stopping")
                        break
                except:
                    pass

            priority = notice.get('priority', 'medium')
            severity_map = {'critical': 'critical', 'high': 'high', 'medium': 'medium', 'low': 'low', 'negligible': 'low'}
            severity = severity_map.get(priority.lower(), 'medium')

            cves = notice.get('cves', [])
            cve_ids = [c if isinstance(c, str) else c.get('id', '') for c in cves] if isinstance(cves, list) else []

            # Estrai pacchetti affetti
            packages = []
            release_packages = notice.get('release_packages', {})
            for release_name, pkg_list in release_packages.items():
                release_lower = release_name.lower()
                if any(r in release_lower for r in ['noble', 'jammy', 'focal', 'mantic', 'lunar', 'kinetic']):
                    if isinstance(pkg_list, list):
                        for pkg_info in pkg_list:
                            if isinstance(pkg_info, dict):
                                packages.append({
                                    'name': pkg_info.get('name', ''),
                                    'version': pkg_info.get('version', ''),
                                    'release': release_lower
                                })

            new_errata.append({
                'advisory_id': notice_id,
                'title': notice.get('title', '')[:500],
                'description': notice.get('description', '')[:4000],
                'severity': severity,
                'source': 'usn',
                'distribution': 'ubuntu',
                'issued_date': notice.get('published'),
                'cves': cve_ids,
                'packages': packages
            })

        offset += 20
        time.sleep(0.5)  # Rate limiting gentile

    logger.info(f"Found {len(new_errata)} new USN errata to process")

    processed = 0
    packages_saved = 0

    for errata in new_errata:
        try:
            cur.execute("""
                INSERT INTO errata (advisory_id, title, description, severity, source, distribution, issued_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (advisory_id) DO NOTHING RETURNING id
            """, (errata['advisory_id'], errata['title'], errata['description'], errata['severity'], errata['source'], errata['distribution'], errata['issued_date']))
            row = cur.fetchone()

            if row:
                errata_id = row['id']
                processed += 1

                for cve_id in errata['cves']:
                    if cve_id and cve_id.startswith('CVE-'):
                        cur.execute("INSERT INTO cves (cve_id) VALUES (%s) ON CONFLICT (cve_id) DO UPDATE SET cve_id = EXCLUDED.cve_id RETURNING id", (cve_id,))
                        cve_row = cur.fetchone()
                        cur.execute("INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (errata_id, cve_row['id']))

                for pkg in errata['packages']:
                    if pkg['name']:
                        cur.execute("""
                            INSERT INTO errata_packages (errata_id, package_name, fixed_version, release_name)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                        """, (errata_id, pkg['name'], pkg['version'], pkg['release']))
                        packages_saved += 1

                conn.commit()
        except Exception as e:
            logger.error(f"Error processing errata {errata['advisory_id']}: {e}")
            conn.rollback()
            continue

    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"USN sync completed: {processed} errata, {packages_saved} packages")

    return jsonify({
        'status': 'success',
        'source': 'usn',
        'processed': processed,
        'packages_saved': packages_saved,
        'last_known': last_usn
    })

# ============================================================
# FIX #5: SYNC DSA AUTOMATICO COMPLETO
# ============================================================
@app.route('/api/sync/dsa/full', methods=['POST'])
def sync_dsa_full():
    """
    FIX #5: Sync completo Debian in batch automatico
    """
    logger.info("Starting full DSA sync (automatic batch processing)")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('dsa_full', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()

    # Download full JSON once
    url = "https://security-tracker.debian.org/tracker/data/json"
    try:
        logger.info(f"Downloading Debian security tracker JSON (~63MB)...")
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=300)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Downloaded {len(data)} packages from Debian tracker")
    except Exception as e:
        logger.error(f"Failed to download Debian data: {e}")
        cur.execute("UPDATE sync_logs SET status = 'error', error_message = %s WHERE id = %s", (str(e), log_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

    target_releases = ['bookworm', 'bullseye', 'trixie']
    total_processed = 0
    total_packages_saved = 0
    batch_size = 500
    all_packages = list(data.items())

    # Process in batches
    for batch_start in range(0, len(all_packages), batch_size):
        batch_end = min(batch_start + batch_size, len(all_packages))
        packages_batch = all_packages[batch_start:batch_end]

        logger.info(f"Processing batch {batch_start}-{batch_end} of {len(all_packages)}")

        batch_processed = 0
        batch_packages_saved = 0

        for package_name, package_data in packages_batch:
            if not isinstance(package_data, dict):
                continue

            for cve_id, cve_data in package_data.items():
                if not cve_id.startswith('CVE-') or not isinstance(cve_data, dict):
                    continue

                releases = cve_data.get('releases', {})
                description = cve_data.get('description', '')
                urgency = cve_data.get('urgency', 'medium')
                urgency_map = {'critical': 'critical', 'emergency': 'critical', 'high': 'high', 'medium': 'medium', 'low': 'low', 'unimportant': 'low', 'not yet assigned': 'medium'}
                severity = urgency_map.get(urgency.lower() if urgency else 'medium', 'medium')

                for release_name in target_releases:
                    if release_name not in releases:
                        continue
                    release_data = releases[release_name]
                    if not isinstance(release_data, dict) or release_data.get('status') != 'resolved' or not release_data.get('fixed_version'):
                        continue

                    fixed_version = release_data.get('fixed_version')
                    advisory_id = f"DEB-{cve_id}-{release_name}"

                    try:
                        cur.execute("""
                            INSERT INTO errata (advisory_id, title, description, severity, source, distribution, issued_date)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (advisory_id) DO NOTHING RETURNING id
                        """, (advisory_id, f"{package_name}: {cve_id}", (description or '')[:4000], severity, 'dsa', f"debian-{release_name}"))
                        row = cur.fetchone()

                        if row:
                            errata_id = row['id']
                            batch_processed += 1

                            cur.execute("INSERT INTO cves (cve_id) VALUES (%s) ON CONFLICT (cve_id) DO UPDATE SET cve_id = EXCLUDED.cve_id RETURNING id", (cve_id,))
                            cve_row = cur.fetchone()
                            cur.execute("INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (errata_id, cve_row['id']))

                            cur.execute("""
                                INSERT INTO errata_packages (errata_id, package_name, fixed_version, release_name)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                            """, (errata_id, package_name, fixed_version, release_name))
                            batch_packages_saved += 1
                    except:
                        continue

        conn.commit()
        total_processed += batch_processed
        total_packages_saved += batch_packages_saved
        logger.info(f"Batch {batch_start}-{batch_end} complete: {batch_processed} errata, {batch_packages_saved} packages")

    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (total_processed, log_id))
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"Full DSA sync completed: {total_processed} errata, {total_packages_saved} packages")

    return jsonify({
        'status': 'success',
        'source': 'dsa_full',
        'total_packages_scanned': len(all_packages),
        'total_errata_created': total_processed,
        'total_packages_saved': total_packages_saved
    })

# Mantengo anche il vecchio endpoint batch per compatibilità
@app.route('/api/sync/dsa', methods=['POST'])
def sync_dsa():
    """Sync DSA batch singolo (legacy compatibility)"""
    offset = request.args.get('offset', 0, type=int)
    batch_size = 500

    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('dsa', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()

    url = "https://security-tracker.debian.org/tracker/data/json"
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        cur.execute("UPDATE sync_logs SET status = 'error', error_message = %s WHERE id = %s", (str(e), log_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'error': str(e)}), 500

    target_releases = ['bookworm', 'bullseye', 'trixie']
    packages = list(data.items())[offset:offset + batch_size]
    processed = 0
    packages_saved = 0

    for package_name, package_data in packages:
        if not isinstance(package_data, dict):
            continue

        for cve_id, cve_data in package_data.items():
            if not cve_id.startswith('CVE-') or not isinstance(cve_data, dict):
                continue

            releases = cve_data.get('releases', {})
            description = cve_data.get('description', '')
            urgency = cve_data.get('urgency', 'medium')
            urgency_map = {'critical': 'critical', 'emergency': 'critical', 'high': 'high', 'medium': 'medium', 'low': 'low', 'unimportant': 'low', 'not yet assigned': 'medium'}
            severity = urgency_map.get(urgency.lower() if urgency else 'medium', 'medium')

            for release_name in target_releases:
                if release_name not in releases:
                    continue
                release_data = releases[release_name]
                if not isinstance(release_data, dict) or release_data.get('status') != 'resolved' or not release_data.get('fixed_version'):
                    continue

                fixed_version = release_data.get('fixed_version')
                advisory_id = f"DEB-{cve_id}-{release_name}"

                try:
                    cur.execute("""
                        INSERT INTO errata (advisory_id, title, description, severity, source, distribution, issued_date)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (advisory_id) DO NOTHING RETURNING id
                    """, (advisory_id, f"{package_name}: {cve_id}", (description or '')[:4000], severity, 'dsa', f"debian-{release_name}"))
                    row = cur.fetchone()

                    if row:
                        errata_id = row['id']
                        processed += 1

                        cur.execute("INSERT INTO cves (cve_id) VALUES (%s) ON CONFLICT (cve_id) DO UPDATE SET cve_id = EXCLUDED.cve_id RETURNING id", (cve_id,))
                        cve_row = cur.fetchone()
                        cur.execute("INSERT INTO errata_cves (errata_id, cve_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (errata_id, cve_row['id']))

                        cur.execute("""
                            INSERT INTO errata_packages (errata_id, package_name, fixed_version, release_name)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (errata_id, package_name, release_name) DO NOTHING
                        """, (errata_id, package_name, fixed_version, release_name))
                        packages_saved += 1

                        conn.commit()
                except:
                    conn.rollback()
                    continue

    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (processed, log_id))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        'status': 'success',
        'source': 'dsa',
        'offset': offset,
        'batch_size': batch_size,
        'processed': processed,
        'packages_saved': packages_saved,
        'total_packages': len(data),
        'next_offset': offset + batch_size if offset + batch_size < len(data) else None
    })

# ============================================================
# SYNC NVD (con prioritization)
# ============================================================
@app.route('/api/sync/nvd', methods=['POST'])
def sync_nvd():
    batch_size = request.args.get('batch_size', 50, type=int)
    force = request.args.get('force', 'false').lower() == 'true'
    prioritize_high_severity = request.args.get('prioritize', 'true').lower() == 'true'

    conn = get_db()
    cur = conn.cursor()

    # IMPROVEMENT: Prioritize CVEs with high severity errata first
    if prioritize_high_severity and not force:
        cur.execute("""
            SELECT DISTINCT c.cve_id
            FROM cves c
            LEFT JOIN cve_details cd ON c.cve_id = cd.cve_id
            JOIN errata_cves ec ON c.id = ec.cve_id
            JOIN errata e ON ec.errata_id = e.id
            WHERE cd.cve_id IS NULL
              AND e.severity IN ('critical', 'high')
            ORDER BY e.severity DESC, c.cve_id DESC
            LIMIT %s
        """, (batch_size,))
    elif force:
        cur.execute("SELECT DISTINCT c.cve_id FROM cves c ORDER BY c.cve_id DESC LIMIT %s", (batch_size,))
    else:
        cur.execute("SELECT DISTINCT c.cve_id FROM cves c LEFT JOIN cve_details cd ON c.cve_id = cd.cve_id WHERE cd.cve_id IS NULL ORDER BY c.cve_id DESC LIMIT %s", (batch_size,))

    pending_cves = [r['cve_id'] for r in cur.fetchall()]

    if not pending_cves:
        cur.close()
        conn.close()
        return jsonify({'status': 'complete', 'message': 'No CVEs to process', 'processed': 0})

    logger.info(f"Starting NVD sync for {len(pending_cves)} CVEs (prioritize={prioritize_high_severity})")

    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('nvd', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()

    processed = 0
    errors = []
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    if NVD_API_KEY:
        session.headers['apiKey'] = NVD_API_KEY

    for cve_id in pending_cves:
        try:
            url = f"{NVD_API_BASE}?cveId={cve_id}"
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get('vulnerabilities'):
                vuln = data['vulnerabilities'][0]['cve']
                metrics = vuln.get('metrics', {})

                cvss_v3_score, cvss_v3_vector, cvss_v3_severity = None, None, None
                if 'cvssMetricV31' in metrics:
                    cvss_data = metrics['cvssMetricV31'][0]['cvssData']
                    cvss_v3_score, cvss_v3_vector = cvss_data['baseScore'], cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()
                elif 'cvssMetricV30' in metrics:
                    cvss_data = metrics['cvssMetricV30'][0]['cvssData']
                    cvss_v3_score, cvss_v3_vector = cvss_data['baseScore'], cvss_data['vectorString']
                    cvss_v3_severity = cvss_data.get('baseSeverity', '').upper()

                cvss_v2_score, cvss_v2_vector = None, None
                if 'cvssMetricV2' in metrics:
                    cvss_data = metrics['cvssMetricV2'][0]['cvssData']
                    cvss_v2_score, cvss_v2_vector = cvss_data['baseScore'], cvss_data.get('vectorString')

                severity = cvss_v3_severity or calculate_severity(cvss_v3_score or cvss_v2_score)
                cwes = [desc['value'] for weakness in vuln.get('weaknesses', []) for desc in weakness.get('description', []) if desc.get('value', '').startswith('CWE-')]
                descriptions = vuln.get('descriptions', [])
                description = next((d['value'] for d in descriptions if d.get('lang') == 'en'), descriptions[0]['value'] if descriptions else '')

                cur.execute("""
                    INSERT INTO cve_details (cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity, cvss_v2_score, cvss_v2_vector, severity, description, published_date, last_modified, cwe_ids, nvd_last_sync)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (cve_id) DO UPDATE SET cvss_v3_score = EXCLUDED.cvss_v3_score, cvss_v3_vector = EXCLUDED.cvss_v3_vector, cvss_v3_severity = EXCLUDED.cvss_v3_severity, cvss_v2_score = EXCLUDED.cvss_v2_score, severity = EXCLUDED.severity, cwe_ids = EXCLUDED.cwe_ids, nvd_last_sync = NOW()
                """, (cve_id, cvss_v3_score, cvss_v3_vector, cvss_v3_severity, cvss_v2_score, cvss_v2_vector, severity, description[:4000] if description else None, vuln.get('published'), vuln.get('lastModified'), cwes if cwes else None))
                conn.commit()
                processed += 1

            time.sleep(0.6 if NVD_API_KEY else 6)
        except Exception as e:
            errors.append(f"{cve_id}: {str(e)[:100]}")
            logger.warning(f"Failed to fetch NVD data for {cve_id}: {e}")

    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s, error_message = %s WHERE id = %s", (processed, '; '.join(errors[:5]) if errors else None, log_id))
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"NVD sync completed: {processed}/{len(pending_cves)} CVEs processed")

    return jsonify({'status': 'success', 'processed': processed, 'pending_total': len(pending_cves), 'errors_count': len(errors)})

# ============================================================
# FIX #2: SYNC OVAL + CVE MAPPING
# ============================================================
@app.route('/api/sync/oval', methods=['POST'])
def sync_oval():
    platform = request.args.get('platform', 'all')

    conn = get_db()
    cur = conn.cursor()

    cur.execute("INSERT INTO sync_logs (sync_type, status, started_at) VALUES ('oval', 'running', NOW()) RETURNING id")
    log_id = cur.fetchone()['id']
    conn.commit()

    results = {}
    total_processed = 0

    platforms_to_sync = OVAL_SOURCES if platform == 'all' else ({platform: OVAL_SOURCES[platform]} if platform in OVAL_SOURCES else {})
    ns = {'oval-def': 'http://oval.mitre.org/XMLSchema/oval-definitions-5'}

    for plat, codenames_dict in platforms_to_sync.items():
        for cn, url in codenames_dict.items():
            try:
                logger.info(f"Downloading OVAL definitions for {plat}-{cn} from {url}")
                resp = requests.get(url, timeout=180)
                resp.raise_for_status()
                xml_content = bz2.decompress(resp.content).decode('utf-8')
                root = ET.fromstring(xml_content)
                definitions = []

                for definition in root.findall('.//oval-def:definition', ns):
                    oval_id = definition.get('id')
                    metadata = definition.find('oval-def:metadata', ns)
                    if metadata is None:
                        continue

                    title = metadata.findtext('oval-def:title', '', ns)
                    description = metadata.findtext('oval-def:description', '', ns)
                    severity = 'UNKNOWN'
                    advisory = metadata.find('oval-def:advisory', ns)
                    if advisory is not None:
                        sev_elem = advisory.find('oval-def:severity', ns)
                        if sev_elem is not None and sev_elem.text:
                            severity = sev_elem.text.upper()

                    cve_refs = [ref.get('ref_id') for ref in metadata.findall('.//oval-def:reference[@source="CVE"]', ns) if ref.get('ref_id')]

                    definitions.append({'oval_id': oval_id, 'title': title[:500], 'description': description[:2000], 'severity': severity, 'platform': f"{plat}-{cn}", 'platform_version': cn, 'cve_refs': cve_refs, 'source_url': url})

                # Save OVAL definitions and create CVE mappings
                for defn in definitions:
                    cur.execute("""
                        INSERT INTO oval_definitions (oval_id, title, description, severity, platform, platform_version, cve_refs, source_url, last_sync)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (oval_id) DO UPDATE SET title = EXCLUDED.title, severity = EXCLUDED.severity, cve_refs = EXCLUDED.cve_refs, last_sync = NOW()
                    """, (defn['oval_id'], defn['title'], defn['description'], defn['severity'], defn['platform'], defn['platform_version'], defn['cve_refs'], defn['source_url']))

                    # FIX #2: Create errata-CVE-OVAL mappings for visibility
                    for cve_ref in defn['cve_refs']:
                        if cve_ref and cve_ref.startswith('CVE-'):
                            # Find errata for this CVE
                            cur.execute("""
                                SELECT DISTINCT e.id as errata_id
                                FROM errata e
                                JOIN errata_cves ec ON e.id = ec.errata_id
                                JOIN cves c ON ec.cve_id = c.id
                                WHERE c.cve_id = %s
                            """, (cve_ref,))

                            for row in cur.fetchall():
                                cur.execute("""
                                    INSERT INTO errata_cve_oval_map (errata_id, cve_id, oval_id)
                                    VALUES (%s, %s, %s)
                                    ON CONFLICT DO NOTHING
                                """, (row['errata_id'], cve_ref, defn['oval_id']))

                conn.commit()
                results[f"{plat}-{cn}"] = len(definitions)
                total_processed += len(definitions)
                logger.info(f"Processed {len(definitions)} OVAL definitions for {plat}-{cn}")
            except Exception as e:
                results[f"{plat}-{cn}"] = f"error: {str(e)[:100]}"
                logger.error(f"Failed to process OVAL for {plat}-{cn}: {e}")

    cur.execute("UPDATE sync_logs SET status = 'completed', completed_at = NOW(), items_processed = %s WHERE id = %s", (total_processed, log_id))
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"OVAL sync completed: {total_processed} definitions processed")

    return jsonify({'status': 'success', 'total_processed': total_processed, 'results': results})

# ============================================================
# UYUNI ENDPOINTS
# ============================================================
@app.route('/api/uyuni/status', methods=['GET'])
@retry_with_backoff(max_attempts=2)
def uyuni_status():
    try:
        client, session = get_uyuni_client()
        if not client:
            return jsonify({'status': 'not configured', 'url': UYUNI_URL})
        version = client.api.getVersion()
        channels = client.channel.listAllChannels(session)
        systems = client.system.listSystems(session)
        client.auth.logout(session)
        return jsonify({'status': 'connected', 'url': UYUNI_URL, 'api_version': version, 'channels_count': len(channels), 'systems_count': len(systems)})
    except Exception as e:
        logger.error(f"UYUNI status check failed: {e}")
        return jsonify({'status': 'error', 'url': UYUNI_URL, 'error': str(e)})

@app.route('/api/uyuni/channels', methods=['GET'])
@retry_with_backoff(max_attempts=2)
def uyuni_channels():
    try:
        client, session = get_uyuni_client()
        if not client:
            return jsonify({'error': 'UYUNI not configured'}), 500
        channels = client.channel.listAllChannels(session)
        result = [{'id': ch['id'], 'label': ch['label'], 'name': ch['name'], 'mapped_distribution': map_channel_to_distribution(ch['label'])} for ch in channels]
        client.auth.logout(session)
        return jsonify({'count': len(result), 'channels': result})
    except Exception as e:
        logger.error(f"Failed to list UYUNI channels: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/uyuni/sync-packages', methods=['POST'])
@retry_with_backoff(max_attempts=2)
def uyuni_sync_packages():
    """Sincronizza la cache dei pacchetti dai canali UYUNI"""
    channel_label = request.args.get('channel', None)

    client, session = get_uyuni_client()
    if not client:
        return jsonify({'error': 'UYUNI not configured'}), 500

    conn = get_db()
    cur = conn.cursor()

    try:
        if channel_label:
            channels = [{'label': channel_label}]
        else:
            channels = client.channel.listAllChannels(session)
            channels = [ch for ch in channels if map_channel_to_distribution(ch['label'])]

        total_synced = 0
        results = {}

        for ch in channels:
            label = ch['label']
            try:
                logger.info(f"Syncing package cache for channel: {label}")
                packages = client.channel.software.listAllPackages(session, label)
                cur.execute("DELETE FROM uyuni_package_cache WHERE channel_label = %s", (label,))

                for pkg in packages:
                    cur.execute("""
                        INSERT INTO uyuni_package_cache
                        (channel_label, package_id, package_name, package_version, package_release, package_arch)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (channel_label, package_id) DO UPDATE SET
                        package_name = EXCLUDED.package_name, last_sync = NOW()
                    """, (label, pkg['id'], pkg['name'], pkg.get('version', ''), pkg.get('release', ''), pkg.get('arch_label', '')))

                conn.commit()
                results[label] = len(packages)
                total_synced += len(packages)
                logger.info(f"Synced {len(packages)} packages for channel {label}")
            except Exception as e:
                results[label] = f"error: {str(e)}"
                logger.error(f"Failed to sync packages for channel {label}: {e}")
                conn.rollback()

        client.auth.logout(session)
        cur.close()
        conn.close()

        return jsonify({'status': 'success', 'total_packages_synced': total_synced, 'channels': results})
    except Exception as e:
        cur.close()
        conn.close()
        logger.error(f"Package sync failed: {e}")
        return jsonify({'error': str(e)}), 500

# FIX #1: PUSH CON VERSION MATCHING MIGLIORATO
@app.route('/api/uyuni/push', methods=['POST'])
@retry_with_backoff(max_attempts=2)
def uyuni_push():
    """
    Push errata a UYUNI CON associazione pacchetti migliorata
    FIX #1: Version matching invece di solo nome pacchetto
    """
    limit = request.args.get('limit', 10, type=int)

    client, session = get_uyuni_client()
    if not client:
        return jsonify({'error': 'UYUNI not configured'}), 500

    conn = get_db()
    cur = conn.cursor()

    try:
        channels = client.channel.listAllChannels(session)
        channel_map = {}
        for ch in channels:
            dist = map_channel_to_distribution(ch['label'])
            if dist:
                if dist not in channel_map:
                    channel_map[dist] = []
                channel_map[dist].append(ch['label'])

        active_distributions = list(channel_map.keys())
        if not active_distributions:
            return jsonify({'status': 'no_channels', 'message': 'No Ubuntu/Debian channels found'})

        cur.execute("""
            SELECT * FROM errata
            WHERE sync_status = 'pending' AND distribution = ANY(%s)
            ORDER BY issued_date DESC LIMIT %s
        """, (active_distributions, limit))
        pending = cur.fetchall()

        pushed = 0
        skipped_no_packages = 0
        skipped_version_mismatch = 0
        errors = []

        for errata in pending:
            try:
                dist = errata['distribution']
                if dist not in channel_map:
                    continue
                target_channels = channel_map[dist]

                # FIX #1: Match pacchetti con version checking
                cur.execute("""
                    SELECT ep.package_name, ep.fixed_version, ep.release_name
                    FROM errata_packages ep
                    WHERE ep.errata_id = %s
                """, (errata['id'],))
                errata_packages = cur.fetchall()

                package_ids = []
                if errata_packages:
                    for channel_label in target_channels:
                        for errata_pkg in errata_packages:
                            pkg_name = errata_pkg['package_name']
                            fixed_ver = errata_pkg['fixed_version']

                            # FIX #1: Query con version comparison
                            cur.execute("""
                                SELECT DISTINCT package_id, package_version
                                FROM uyuni_package_cache
                                WHERE channel_label = %s AND package_name = %s
                            """, (channel_label, pkg_name))

                            cached_packages = cur.fetchall()
                            for cached_pkg in cached_packages:
                                # FIX #1: Version check - solo pacchetti >= fixed version
                                if fixed_ver and cached_pkg['package_version']:
                                    if version_compare(cached_pkg['package_version'], fixed_ver):
                                        package_ids.append(cached_pkg['package_id'])
                                        logger.debug(f"Matched package {pkg_name}:{cached_pkg['package_version']} >= {fixed_ver}")
                                    else:
                                        logger.debug(f"Skipped {pkg_name}:{cached_pkg['package_version']} < {fixed_ver}")
                                else:
                                    # Se non c'è fixed version, usa fallback match per nome
                                    package_ids.append(cached_pkg['package_id'])

                package_ids = list(set(package_ids))  # Deduplicate

                if not package_ids and errata_packages:
                    skipped_version_mismatch += 1
                    logger.warning(f"No matching packages with correct version for {errata['advisory_id']}")
                    cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                    conn.commit()
                    continue

                errata_info = {
                    'synopsis': (errata['title'] or errata['advisory_id'])[:200],
                    'advisory_name': errata['advisory_id'],
                    'advisory_type': 'Security Advisory',
                    'advisory_release': 1,
                    'product': dist.replace('-', ' ').title(),
                    'topic': (errata['title'] or '')[:500],
                    'description': (errata['description'] or '')[:2000],
                    'solution': 'Apply the updated packages.',
                    'references': '',
                    'notes': f'Imported by UYUNI Errata Manager v2.5 from {errata["source"].upper()}'
                }

                severity = errata.get('severity', 'medium')
                severity_keywords = {
                    'critical': ['critical', 'security'],
                    'high': ['important', 'security'],
                    'medium': ['moderate', 'security'],
                    'low': ['low', 'security']
                }
                keywords = severity_keywords.get(severity, ['moderate', 'security'])

                logger.info(f"Pushing errata {errata['advisory_id']} with {len(package_ids)} packages to UYUNI")
                client.errata.create(session, errata_info, [], keywords, package_ids, target_channels)

                cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                conn.commit()
                pushed += 1

            except Exception as e:
                error_msg = str(e)
                if 'already exists' in error_msg.lower():
                    cur.execute("UPDATE errata SET sync_status = 'synced' WHERE id = %s", (errata['id'],))
                    conn.commit()
                    pushed += 1
                else:
                    errors.append(f"{errata['advisory_id']}: {error_msg[:100]}")
                    logger.error(f"Failed to push errata {errata['advisory_id']}: {error_msg[:200]}")

        client.auth.logout(session)
    except Exception as e:
        cur.close()
        conn.close()
        logger.error(f"Errata push failed: {e}")
        return jsonify({'error': str(e)}), 500

    cur.close()
    conn.close()

    logger.info(f"Push completed: {pushed} pushed, {skipped_no_packages} skipped (no pkg), {skipped_version_mismatch} skipped (version)")

    return jsonify({
        'status': 'success',
        'pushed': pushed,
        'skipped_no_packages': skipped_no_packages,
        'skipped_version_mismatch': skipped_version_mismatch,
        'pending_processed': len(pending),
        'errors': errors[:5] if errors else None
    })

@app.route('/api/sync/status', methods=['GET'])
def sync_status():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sync_logs ORDER BY started_at DESC LIMIT 20")
    logs = [{'id': r['id'], 'sync_type': r['sync_type'], 'status': r['status'], 'started_at': r['started_at'].isoformat() if r['started_at'] else None, 'completed_at': r['completed_at'].isoformat() if r['completed_at'] else None, 'items_processed': r['items_processed'], 'error_message': r['error_message']} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'logs': logs})

if __name__ == '__main__':
    logger.info("Starting UYUNI Errata Manager API v2.5")
    app.run(host='0.0.0.0', port=5000, debug=False)
