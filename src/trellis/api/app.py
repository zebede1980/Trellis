from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from trellis import config, db, jobs, traits
from trellis.auth import Throttle
from trellis.api import auth as auth_api, boards as boards_api, entries as entries_api
from trellis.api.deps import get_conn, require_xhr


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    conn = db.connect(settings.db_path)
    db.migrate(conn)
    traits.load_seed(conn)
    conn.close()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker = None
        if settings.start_worker:
            worker = jobs.Worker(settings)
            worker.start()
        yield
        if worker:
            worker.stop()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
                  dependencies=[Depends(require_xhr)])
    app.state.settings = settings
    app.state.throttle = Throttle()
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax",
                       max_age=60 * 60 * 24 * 60, https_only=settings.secure_cookies, session_cookie="trellis")

    for r in (auth_api.router, boards_api.router, entries_api.router):
        app.include_router(r)

    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        return {"ok": True, "version": config.VERSION, "schema": db.schema_version(conn)}

    _mount_frontend(app, settings.web_dir)
    return app


def _mount_frontend(app: FastAPI, web_dir: Path) -> None:
    """Serve the built SPA. Real files are served as-is; any other non-API path gets index.html so the
    client-side router can handle it."""
    root = web_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404)
        if path:
            target = (root / path).resolve()
            if target.is_relative_to(root) and target.is_file():
                return FileResponse(target)
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(404, "frontend not built")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
