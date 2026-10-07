import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.routes import (assumptions, deployment, factory, genie, governance, ingestion, mart,
                           orchestration, overview, projection, stochastic)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

app = FastAPI(title="Life & Pension Actuarial Workbench", version="1.0.0")
for r in (overview, ingestion, mart, assumptions, factory, deployment, projection, stochastic, governance,
          orchestration, genie):
    app.include_router(r.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = FRONTEND_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
