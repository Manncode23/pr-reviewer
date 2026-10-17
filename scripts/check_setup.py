"""Sanity check for Stage 0.

Run from the project root:
    python -m scripts.check_setup
"""

import psycopg

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging


def mask(secret) -> str:
    value = secret.get_secret_value()
    return f"{value[:4]}...{value[-2:]}" if len(value) > 8 else "***"


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = get_logger("check_setup")

    logger.info("Config loaded for app: %s", settings.app_name)
    logger.info("Gemini model: %s", settings.gemini_model)
    logger.info("Gemini key: %s", mask(settings.google_api_key))
    logger.info("GitHub token: %s", mask(settings.github_token))

    try:
        with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
            version = conn.execute("SELECT version();").fetchone()[0]
        logger.info("Postgres OK: %s", version.split(",")[0])
    except Exception as exc:
        logger.error("Postgres connection failed: %s", exc)
        return

    logger.info("Stage 0 setup looks good.")


if __name__ == "__main__":
    main()