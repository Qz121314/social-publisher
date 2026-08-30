from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from app.api.routes import router
from app.database import init_db
from app.services.scheduler import publish_scheduler
from app.services.worker import worker_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    worker_manager.recover_runtime_state()
    publish_scheduler.start()
    yield
    publish_scheduler.shutdown(wait=True)
    worker_manager.shutdown(wait=False)


app = FastAPI(
    title="Social Publisher",
    version="0.9.0",
    description="Local V1 social publishing control plane.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "app": "Social Publisher",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
