import asyncpg
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create asyncpg pool + Redis connection. Shutdown: close both."""
    # Startup
    logger.info("Starting DevPulse API...")

    # asyncpg connection pool
    app.state.db_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "developer_intelligence"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        min_size=2,
        max_size=10,
    )
    logger.info("Database pool created")

    # Redis connection
    from api.cache.redis_client import init_redis, close_redis
    await init_redis(app)
    logger.info("Redis connected")

    yield

    # Shutdown
    await app.state.db_pool.close()
    await close_redis(app)
    logger.info("DevPulse API shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DevPulse API",
    description="Real-time developer sentiment intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from api.auth.router import router as auth_router
from api.routes.health import router as health_router
from api.routes.cache import router as cache_router

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(health_router)
app.include_router(cache_router)

# Implemented on Day 9:
# from api.routes.posts import router as posts_router
# from api.routes.trends import router as trends_router
# from api.routes.tools import router as tools_router
# from api.routes.community import router as community_router
# from api.routes.alerts import router as alerts_router

@app.get("/ping")
@limiter.limit("60/minute")
async def ping(request: Request):
    """Basic liveness check — no auth required."""
    return {"status": "ok", "service": "devpulse-api"}
