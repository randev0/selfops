from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from schemas import AnalysisRequest, AnalysisResponse
from react_agent import run_investigation

log = structlog.get_logger()

app = FastAPI(
    title="SelfOps Analysis Service",
    description="Agentic incident investigation via LangChain ReAct + OpenRouter",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "selfops-analysis", "mode": "react-agent"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    log.info("analyze request received", incident_id=request.incident_id)
    return await run_investigation(request)
