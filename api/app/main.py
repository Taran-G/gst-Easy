import os
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import auth, invoices, ingest, masters, reconcile, risk, whatsapp
from app.graph.client import get_db

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="WhatsApp-first GST invoice, reconciliation and vendor-risk agent for Indian CA firms and SMEs, built on FalkorDB.",
    version="1.0.0"
)

import time
import logging
from fastapi.responses import JSONResponse
from starlette.requests import Request

logger = logging.getLogger("ledgergraph.api")

# Configure CORS
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response
    except Exception as exc:
        process_time = time.perf_counter() - start_time
        logger.exception("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal server error occurred.",
                "path": request.url.path,
                "error": str(exc)
            },
            headers={"X-Process-Time": f"{process_time:.4f}s"}
        )


# Include All Routers under /api/v1
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(invoices.router, prefix=settings.API_V1_STR)
app.include_router(ingest.router, prefix=settings.API_V1_STR)
app.include_router(masters.router, prefix=settings.API_V1_STR)
app.include_router(reconcile.router, prefix=settings.API_V1_STR)
app.include_router(risk.router, prefix=settings.API_V1_STR)
app.include_router(whatsapp.router, prefix=settings.API_V1_STR)

# Serve files locally for review drawer / preview
os.makedirs(settings.DATA_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.DATA_DIR), name="files")

@app.get("/health")
@app.get(f"{settings.API_V1_STR}/health")
def health():
    try:
        db = get_db()
        g = db.select_graph("health_check")
        g.query("RETURN 1")
    except Exception as e:
        return {"status": "degraded", "graph_error": str(e), "mode": settings.MODE}
    return {"status": "ok", "mode": settings.MODE, "version": "1.0.0"}

@app.get("/")
def root():
    return {
        "app": "LedgerGraph API",
        "docs": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }
