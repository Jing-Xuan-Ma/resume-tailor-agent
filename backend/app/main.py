"""
Resume Tailor Agent — FastAPI Entry Point
"""

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.modules.application_engine.router import router as application_engine_router
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.cold_outreach.router import router as cold_outreach_router
from app.modules.growth_advisor.router import router as growth_advisor_router
from app.modules.job_discovery.router import router as job_discovery_router
from app.modules.profile.router import router as profile_router
from app.modules.resume_tailor.router import router as resume_tailor_router
from app.modules.resume_workspace.router import router as resume_workspace_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting up Resume Tailor Agent...", env=settings.APP_ENV)
    db.init_db()
    yield
    logger.info("Shutting down Resume Tailor Agent...")


app = FastAPI(
    title="Resume Tailor Agent API",
    description="AI-powered resume customization without fabrication.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "version": "0.1.0", "env": settings.APP_ENV}

# Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(profile_router, prefix="/api/v1/profile", tags=["Profile"])
app.include_router(resume_tailor_router, prefix="/api/v1/resume-tailor", tags=["Resume Tailor"])
app.include_router(job_discovery_router, prefix="/api/v1/jobs", tags=["Job Discovery"])
app.include_router(application_engine_router, prefix="/api/v1/applications", tags=["Application Engine"])
app.include_router(cold_outreach_router, prefix="/api/v1/outreach", tags=["Cold Outreach"])
app.include_router(growth_advisor_router, prefix="/api/v1/growth", tags=["Growth Advisor"])
app.include_router(resume_workspace_router, prefix="/api/v1/resume-workspace", tags=["Resume Workspace"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
