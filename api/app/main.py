import os
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers import auth, invoices, ingest, masters, reconcile, risk
from app.graph.client import get_db

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="WhatsApp-first GST invoice, reconciliation and vendor-risk agent for Indian CA firms and SMEs, built on FalkorDB.",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include All Routers under /api/v1
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(invoices.router, prefix=settings.API_V1_STR)
app.include_router(ingest.router, prefix=settings.API_V1_STR)
app.include_router(masters.router, prefix=settings.API_V1_STR)
app.include_router(reconcile.router, prefix=settings.API_V1_STR)
app.include_router(risk.router, prefix=settings.API_V1_STR)

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
