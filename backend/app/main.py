from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from app.api.asset_pool import router as asset_pool_router
from app.api.batch_tasks import router as batch_tasks_router
from app.api.resource_entries import router as resource_entries_router
from app.api.routes import router
from app.api.tasks import router as tasks_router
from app.database import init_db
from app.services.attempt_timeline import install_phase6_worker_hooks
from app.services.batch_tasks import batch_task_runner
from app.services.browser_sessions import browser_sessions
from app.services.scheduler import publish_scheduler
from app.services.worker import worker_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    install_phase6_worker_hooks()
    worker_manager.recover_runtime_state()
    batch_task_runner.recover_runtime_state()
    publish_scheduler.start()
    yield
    publish_scheduler.shutdown(wait=True)
    batch_task_runner.shutdown(wait=False)
    # Warm sessions are idle by definition. Close only those Worker-managed idle
    # sessions on backend shutdown so iX windows are not orphaned after the
    # process exits. Active workers keep the existing conservative recovery path.
    for session in browser_sessions.list_sessions():
        if session.get("managed_by_worker") and session.get("warm_until"):
            try:
                browser_sessions.close(int(session["profile_id"]), force=True)
            except Exception:
                pass
    worker_manager.shutdown(wait=False)


app = FastAPI(
    title="Social Publisher",
    version="0.14.0-rc1",
    description="Facebook V1 release candidate; Instagram Phase 8A remains experimental.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(batch_tasks_router, prefix="/api")
app.include_router(resource_entries_router, prefix="/api")
app.include_router(asset_pool_router, prefix="/api")


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
