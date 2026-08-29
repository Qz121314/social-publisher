from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Social Publisher",
    version="0.2.0",
    description="Local multi-account social publishing control plane.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
