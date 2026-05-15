import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.basic_test_record_manager import ensure_basic_test_record_table
from app.auth import cleanup_expired_captchas, cleanup_expired_tokens, ensure_auth_tables
from app.device_basic_info_manager import ensure_device_basic_info_table
from app.issue_statistics_manager import ensure_issue_statistics_table
from app.module_data_manager import ensure_module_data_tables
from app.ops_manager import ensure_ops_tables
from app.task_manager import ensure_task_tables, terminate_running_handles
from app.routers.auth import router as auth_router
from app.routers.basic_test_record import router as basic_test_record_router
from app.routers.device_basic_info import router as device_basic_info_router
from app.routers.issue_statistics import router as issue_statistics_router
from app.routers.module_data import router as module_data_router
from app.routers.ops import router as ops_router
from app.routers.reports import router as reports_router
from app.routers.tasks import router as tasks_router

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FRONTEND_INDEX_PATH = os.path.join(BASE_DIR, "frontend", "index.html")
FRONTEND_ASSETS_PATH = os.path.join(BASE_DIR, "frontend", "assets")


def _get_allowed_origins() -> list[str]:
    raw = (os.getenv("MST_ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return ["http://127.0.0.1:8080", "http://localhost:8080", "http://127.0.0.1:18081", "http://localhost:18081"]
    return [item.strip() for item in raw.split(",") if item.strip()]

app = FastAPI(title="My Security Toolbox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(reports_router)
app.include_router(ops_router)
app.include_router(device_basic_info_router)
app.include_router(basic_test_record_router)
app.include_router(issue_statistics_router)
app.include_router(module_data_router)
app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS_PATH), name="assets")


@app.on_event("startup")
def startup_event():
    ensure_auth_tables()
    ensure_task_tables()
    ensure_ops_tables()
    ensure_device_basic_info_table()
    ensure_basic_test_record_table()
    ensure_issue_statistics_table()
    ensure_module_data_tables()
    cleanup_expired_tokens()
    cleanup_expired_captchas()


@app.on_event("shutdown")
def shutdown_event():
    terminate_running_handles()


@app.get("/")
def frontend_index():
    return FileResponse(FRONTEND_INDEX_PATH, media_type="text/html; charset=utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
