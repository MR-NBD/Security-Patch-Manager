"""
SPM Orchestrator - Flask Application Entry Point

Avvio: python -m app.main
       oppure via systemd (spm-orchestrator.service)
"""

import logging
from flask import Flask, jsonify
from flask_cors import CORS

from app.config import Config
from app.utils.logger import setup_logging
from app.services.db import init_db, close_db
from app.api.health import health_bp

# Setup logging prima di tutto
setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Factory function per creare l'app Flask.
    Pattern usato per facilitare i test.
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY

    # CORS - permette accesso da Streamlit dashboard
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Registra blueprints
    app.register_blueprint(health_bp)

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

    # Connessione database
    logger.info("Connecting to database...")
    if not init_db():
        logger.error("Failed to connect to database - check DB_HOST, DB_NAME, DB_USER, DB_PASSWORD in .env")
        raise SystemExit(1)

    logger.info("Database connected successfully")

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
