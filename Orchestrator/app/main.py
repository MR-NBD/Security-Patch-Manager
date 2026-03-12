"""
SPM Orchestrator - Flask Application Entry Point

Avvio: python -m app.main
       oppure via systemd (spm-orchestrator.service)
"""

import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from app.config import Config
from app.utils.logger import setup_logging
from app.services.db import init_db, close_db
from app.services.poller import init_scheduler
from app.services.test_engine import init_test_scheduler
from app.services.approval_manager import process_snoozed
from app.services.queue_manager import reset_stale_testing
from app.api.health import health_bp
from app.api.sync import sync_bp
from app.api.queue import queue_bp
from app.api.tests import tests_bp
from app.api.approvals import approvals_bp
from app.api.groups import groups_bp
from app.api.prometheus_sd import prometheus_sd_bp

# Setup logging prima di tutto
setup_logging()
logger = logging.getLogger(__name__)


# Endpoint esenti dall'autenticazione API key (monitoring)
_AUTH_EXEMPT = (
    "/api/v1/health",
    "/api/v1/prometheus/targets",
)


def create_app() -> Flask:
    """
    Factory function per creare l'app Flask.
    Pattern usato per facilitare i test.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # CORS - permette accesso da Streamlit dashboard
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    @app.before_request
    def require_api_key():
        """
        Valida X-SPM-Key su tutti gli endpoint /api/*.
        Esenti: /api/v1/health* e /api/v1/prometheus/targets (monitoring).
        Se SPM_API_KEY non è impostata nel .env, la verifica è disabilitata.
        """
        if not Config.API_KEY:
            return
        if any(request.path.startswith(p) for p in _AUTH_EXEMPT):
            return
        if request.headers.get("X-SPM-Key", "") != Config.API_KEY:
            return jsonify({"error": "unauthorized", "message": "Invalid or missing X-SPM-Key"}), 401

    # Registra blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(tests_bp)
    app.register_blueprint(approvals_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(prometheus_sd_bp)

    # Handler errori globali
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "error": "not_found",
            "message": "Endpoint not found",
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "error": "method_not_allowed",
            "message": "HTTP method not allowed for this endpoint",
        }), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({
            "error": "internal_error",
            "message": "An internal error occurred",
        }), 500

    return app


def main():
    """Entry point principale"""
    logger.info(
        f"Starting {Config.APP_NAME} v{Config.APP_VERSION} "
        f"on {Config.HOST}:{Config.PORT} [{Config.ENV}]"
    )
    if not Config.API_KEY:
        logger.warning(
            "SPM_API_KEY not set — Flask API is UNPROTECTED. "
            "Set SPM_API_KEY in .env to enforce X-SPM-Key authentication."
        )

    if Config.SECRET_KEY == "dev-key-change-in-production" and Config.ENV != "development":
        logger.warning(
            "SECRET_KEY is set to the insecure default value. "
            "Generate a secure key with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # Connessione database
    logger.info("Connecting to database...")
    if not init_db():
        logger.error("Failed to connect to database - check DB_HOST, DB_NAME, DB_USER, DB_PASSWORD in .env")
        raise SystemExit(1)

    logger.info("Database connected successfully")

    # Reset patch bloccate in 'testing' (succede se Flask crasha durante un test)
    stale = reset_stale_testing()
    if stale:
        logger.warning(f"Reset {stale} patch bloccate in stato 'testing' → 'queued'")

    # Avvia scheduler UYUNI poller + Test Engine + snooze processor
    scheduler = init_scheduler()
    init_test_scheduler(scheduler)
    scheduler.add_job(
        func=process_snoozed,
        trigger="interval",
        minutes=15,
        id="approval_snooze_check",
        name="Approval Snooze Check",
        replace_existing=True,
        max_instances=1,
    )

    # Crea e avvia app
    app = create_app()

    try:
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG,
            use_reloader=False,
        )
    finally:
        close_db()
        logger.info("Application stopped")


if __name__ == "__main__":
    main()
