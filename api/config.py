"""
Application configuration with startup validation.
Fails fast when required secrets are missing in production.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Environment mode ──────────────────────────────────────────────────────────
APP_ENV = os.getenv("APP_ENV", "dev")
IS_PROD = APP_ENV == "prod"
IS_DEV = APP_ENV == "dev"

# ── Critical secrets ──────────────────────────────────────────────────────────
INSECURE_JWT_DEFAULT = "insecure-default-change-in-production"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", INSECURE_JWT_DEFAULT)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


def validate_config() -> None:
    """
    Validate critical configuration on startup.
    In prod: raises RuntimeError for missing/insecure secrets.
    In dev: logs warnings but continues.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if JWT_SECRET_KEY == INSECURE_JWT_DEFAULT:
        msg = (
            "JWT_SECRET_KEY is using the insecure default. "
            "Generate a secure key with: openssl rand -hex 32"
        )
        if IS_PROD:
            errors.append(msg)
        else:
            warnings.append(msg)

    if not INTERNAL_API_KEY:
        msg = "INTERNAL_API_KEY is not set. Cache invalidation endpoint is unprotected."
        if IS_PROD:
            errors.append(msg)
        else:
            warnings.append(msg)

    if not OPENAI_API_KEY:
        warnings.append(
            "OPENAI_API_KEY is not set. "
            "RAG pipeline and embeddings will fail."
        )

    if not OPENROUTER_API_KEY:
        warnings.append(
            "OPENROUTER_API_KEY is not set. "
            "LLM classification will fail."
        )

    for warning in warnings:
        logger.warning("[CONFIG] %s", warning)

    if errors:
        error_msg = "\n".join(f"  - {error}" for error in errors)
        raise RuntimeError(
            f"Critical configuration errors (APP_ENV={APP_ENV}):\n{error_msg}"
        )

    if not errors and not warnings:
        logger.info("[CONFIG] All configuration validated OK (APP_ENV=%s)", APP_ENV)
    else:
        logger.info(
            "[CONFIG] Configuration validated with %s warnings (APP_ENV=%s)",
            len(warnings),
            APP_ENV,
        )
