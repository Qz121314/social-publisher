from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Social Publisher",
    version="0.1.0",
    description="Local multi-account social publishing control plane.",
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
