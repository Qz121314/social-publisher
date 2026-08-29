from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.database import init_db
from app.services.worker import worker_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    worker_manager.shutdown(wait=False)


app = FastAPI(
    title="Social Publisher",
    version="0.4.0",
    description="Local multi-account social publishing control plane.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
