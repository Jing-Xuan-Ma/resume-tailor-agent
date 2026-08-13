"""
Resume Tailor Agent — FastAPI Entry Point
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.modules.application_engine.router import router as application_engine_router
from app.modules.application_queue.router import router as application_queue_router
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.cold_outreach.router import router as cold_outreach_router
from app.modules.commercial.boundaries import router as commercial_router
from app.modules.job_discovery.router import router as job_discovery_router
from app.modules.llm.router import router as llm_router
from app.modules.profile.router import router as profile_router
from app.modules.resume_workspace.router import router as resume_workspace_router
from app.modules.shopping_cart.router import router as shopping_cart_router
from app.modules.intern_list_scraper.router import router as intern_list_router
from app.modules.intern_list_viewer.mount import mount_intern_list_viewer

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting up Resume Tailor Agent...", env=settings.APP_ENV)
    db.init_db()
    from app.modules.job_discovery.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    yield
    await stop_scheduler()
    logger.info("Shutting down Resume Tailor Agent...")


app = FastAPI(
    title="Resume Tailor Agent API",
    description="AI-powered resume customization without fabrication.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
_cors_kwargs: dict = {
    "allow_origins": settings.CORS_ORIGINS_LIST,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.CORS_ORIGIN_REGEX_VALUE:
    _cors_kwargs["allow_origin_regex"] = settings.CORS_ORIGIN_REGEX_VALUE
app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Health check
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "version": "0.1.0",
        "env": settings.APP_ENV,
        "storage_backend": getattr(settings, "STORAGE_BACKEND", "sqlite"),
    }

# Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(profile_router, prefix="/api/v1/profile", tags=["Profile"])
app.include_router(job_discovery_router, prefix="/api/v1/jobs", tags=["Job Discovery"])
app.include_router(application_engine_router, prefix="/api/v1/applications", tags=["Application Engine"])
app.include_router(application_queue_router, prefix="/api/v1/queue", tags=["Application Queue"])
app.include_router(shopping_cart_router, prefix="/api/v1/shopping-cart", tags=["Shopping Cart"])
app.include_router(cold_outreach_router, prefix="/api/v1/outreach", tags=["Cold Outreach"])
app.include_router(commercial_router, prefix="/api/v1/commercial", tags=["Commercial"])
app.include_router(resume_workspace_router, prefix="/api/v1/resume-workspace", tags=["Resume Workspace"])
app.include_router(llm_router, prefix="/api/v1/llm", tags=["LLM"])
app.include_router(intern_list_router, prefix="/api/v1/intern-list", tags=["Intern List"])

# Embed former :8101 intern-list acceptance UI (no separate process required).
mount_intern_list_viewer(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
