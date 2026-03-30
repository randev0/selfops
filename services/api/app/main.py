from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import alerts, incidents, actions, audit, health, timeline
import structlog

log = structlog.get_logger()

app = FastAPI(
    title="SelfOps API",
    description="AI-powered self-healing infrastructure platform API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    # Prevent FastAPI from issuing 307 trailing-slash redirects.
    # Behind a TLS-terminating proxy the redirect Location is HTTP, which
    # causes browsers to block the cross-origin HTTP→HTTPS downgrade.
    redirect_slashes=False,
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
app.include_router(timeline.router, prefix="/api/incidents", tags=["timeline"])


@app.on_event("startup")
async def startup():
    log.info("SelfOps API starting up")
