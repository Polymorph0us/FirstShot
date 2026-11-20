from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    booking_router,
    events_router,
    monitoring_router,
    preferences_router,
    session_router,
)
from app.core.config import settings
from app.database.session import init_db
from app.services.scheduler import monitoring_engine, ws_manager

STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    await init_db()
    # Start monitoring engine
    monitoring_engine.start()
    yield
    # Shutdown monitoring engine & close browser sessions
    monitoring_engine.shutdown()
    await monitoring_engine.provider.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="FirstShot - Personal Booking Automation Platform with Saveetha College Portal Integration",
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(events_router)
app.include_router(preferences_router)
app.include_router(monitoring_router)
app.include_router(session_router)
app.include_router(booking_router)

# Mount static & frontend build assets
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "application": "FirstShot",
        "provider": "Saveetha",
        "timezone": settings.TIMEZONE
    }

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    # Canonical frontend is built React app in frontend/dist
    react_index = FRONTEND_DIST / "index.html"
    if react_index.exists():
        return FileResponse(react_index)
    static_index = STATIC_DIR / "index.html"
    if static_index.exists():
        return FileResponse(static_index)
    return HTMLResponse("<h1>FirstShot API Running</h1><p>Frontend build not found.</p>")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open, receive any client heartbeats
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
