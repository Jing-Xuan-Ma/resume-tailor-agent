"""
Resume Tailor Agent — FastAPI Entry Point
"""

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.modules.chat.router import router as chat_router
from app.modules.resume_tailor.router import router as resume_tailor_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting up Resume Tailor Agent...", env=settings.APP_ENV)
    # TODO: Initialize database connections, vector store collections
    yield
    logger.info("Shutting down Resume Tailor Agent...")
    # TODO: Close connections


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
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(resume_tailor_router, prefix="/api/v1/resume-tailor", tags=["Resume Tailor"])

# Placeholder routers for future modules (to maintain API contract)
# from app.modules.job_discovery.router import router as job_discovery_router
# app.include_router(job_discovery_router, prefix="/api/v1/jobs", tags=["Job Discovery"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
