"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.report import router as report_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Analytics API",
        description=(
            "Transaction analytics service providing aggregated metrics "
            "over a PostgreSQL-backed dataset of users and transactions."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(report_router)

    @app.get("/healthz", tags=["Health"])
    async def healthcheck() -> dict:
        """Liveness probe endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
