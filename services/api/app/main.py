from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import alerts, incidents, actions, audit, health
import structlog

log = structlog.get_logger()

app = FastAPI(
    title="SelfOps API",
    description="AI-powered self-healing infrastructure platform API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(actions.router, prefix="/api/incidents", tags=["actions"])
app.include_router(audit.router, prefix="/api/incidents", tags=["audit"])


@app.on_event("startup")
async def startup():
    log.info("SelfOps API starting up")
